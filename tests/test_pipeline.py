import os
os.environ.setdefault("OTR_NO_PRESIDIO", "1")

from otr.pipeline import Pipeline
from otr.types import Segment
from otr.llm import MockLLM, classify_sensitivity, extract_json
from otr.cue_detector import detect
from otr.pii import redact_pii

_n = 0


def seg(text, t, speaker="A"):
    global _n
    _n += 1
    return Segment(id=f"s{_n}", speaker=speaker, text=text, t_start=t, t_end=t + 1)


def run(p, items):
    """items: [(text, t)] -> all events; ticks far in the future at the end and flushes."""
    ev = []
    for text, t in items:
        ev += p.push(seg(text, t), now=t)
    ev += p.tick(items[-1][1] + 1000)
    ev += p.flush()
    return ev


def note_text(p):
    return " | ".join(s.text for s in p.notes())


def kinds(ev):
    return [e.kind for e in ev]


def test_hold_delay_release():
    p = Pipeline(hold_seconds=30)
    s = seg("We ship the dashboard next sprint.", 0)
    assert kinds(p.push(s, now=0)) == ["held"]
    assert p.tick(29.9) == [] and p.notes() == []
    ev = p.tick(30.0)
    assert kinds(ev) == ["committed"] and ev[0].segment_id == s.id
    assert [x.id for x in p.notes()] == [s.id]


def test_explicit_start_and_end():
    p = Pipeline(hold_seconds=10)
    ev = run(p, [
        ("Let's review the roadmap.", 0),
        ("Off the record, the vendor deal is falling apart.", 5),
        ("Their CEO is very unhappy with the pricing.", 8),
        ("Okay, back on the record.", 12),
        ("Next we cover the launch checklist.", 15),
    ])
    out = note_text(p)
    assert "roadmap" in out and "launch checklist" in out
    assert "vendor" not in out and "CEO" not in out
    assert sum(e.kind == "redacted" for e in ev) >= 3
    assert [e.state for e in ev if e.kind == "state_change"] == ["OFF", "ON"]
    assert p.state == "ON"


def test_explicit_start_implicit_end():
    p = Pipeline(hold_seconds=10)
    run(p, [
        ("Don't write this down: the acquisition talks with Contoso start Monday.", 0),
        ("Contoso wants the acquisition closed before the audit.", 3),
        ("Anyway, let's move on to the hiring plan for the frontend team.", 6),
        ("We need two frontend engineers by March.", 9),
    ])
    out = note_text(p)
    assert "Contoso" not in out and "acquisition" not in out
    assert "hiring plan" in out and "frontend engineers" in out
    assert p.state == "ON"


def test_implicit_end_via_llm():
    llm = MockLLM(lambda pr: '{"topic_changed": true}' if "Has the conversation moved on" in pr else "{}")
    p = Pipeline(llm=llm, hold_seconds=10)
    run(p, [("Between us, the budget is overspent.", 0), ("What about the picnic menu then?", 2)])
    assert "picnic" in note_text(p) and "budget" not in note_text(p)


def test_retroactive_on_held_text():
    p = Pipeline(hold_seconds=30)
    ev = []
    ev += p.push(seg("Our new pricing tier launches in June.", 0), now=0)
    ev += p.push(seg("The rumor is Dana will leave for a competitor.", 5), now=5)
    ev += p.push(seg("Forget what I said about Dana leaving.", 8), now=8)
    ev += p.tick(100) + p.flush()
    assert any(e.kind == "redacted" and e.reason.startswith("retro:match") for e in ev)
    assert not any(e.kind == "retro_removed" for e in ev)
    assert "Dana" not in note_text(p) and "pricing" in note_text(p)


def test_retroactive_on_committed_text():
    p = Pipeline(hold_seconds=5)
    p.push(seg("The server migration is scheduled for Friday.", 0), now=0)
    p.push(seg("Honestly the Atlas project got cancelled quietly.", 1), now=1)
    p.tick(20)
    assert "Atlas" in note_text(p) and "migration" in note_text(p)
    ev = p.push(seg("Please scratch that, delete what I said about the Atlas project.", 30), now=30)
    removed = [e for e in ev if e.kind == "retro_removed"]
    assert len(removed) == 1 and "Atlas" in removed[0].text
    assert removed[0] in p.audit_log()
    assert "Atlas" not in note_text(p) and "migration" in note_text(p)


def test_retroactive_strike_that_previous_and_llm_ids():
    p = Pipeline(hold_seconds=30)
    a = seg("Totally unrelated agenda item.", 0)
    b = seg("The secret codename is Falcon.", 2)
    p.push(a, now=0)
    p.push(b, now=2)
    p.push(seg("Strike that.", 3), now=3)
    p.flush()
    assert [s.id for s in p.notes()] == [a.id]
    llm = MockLLM(lambda pr: '{"ids": ["x1"]}')
    p = Pipeline(llm=llm, hold_seconds=30)
    p.push(Segment("x0", "A", "Alpha beta gamma delta.", 0, 1), now=1)
    p.push(Segment("x1", "A", "Quarterly numbers look rough.", 1, 2), now=2)
    p.push(Segment("x2", "A", "Forget what I said about the numbers.", 2, 3), now=3)
    p.flush()
    assert [s.id for s in p.notes()] == ["x0"]


def test_implicit_pending_confirm_keep_out():
    p = Pipeline(hold_seconds=10)
    s = seg("My doctor says the diagnosis is serious, I start chemo soon.", 0)
    ev = p.push(s, now=0)
    assert kinds(ev) == ["held", "state_change", "pending_confirm"]
    assert p.state == "PENDING_CONFIRM"
    assert p.tick(500) == [] and p.notes() == []   # stays held
    ev = p.confirm(s.id, keep_out=True)
    assert "redacted" in kinds(ev) and p.state == "ON"
    p.flush()
    assert p.notes() == []


def test_implicit_pending_confirm_keep_in():
    p = Pipeline(hold_seconds=10)
    s = seg("The salary band for this role is 140k.", 0)
    ev = p.push(s, now=0)
    assert "pending_confirm" in kinds(ev)
    ev = p.confirm(s.id, keep_out=False)
    assert "committed" in kinds(ev) and p.state == "ON"
    assert [x.id for x in p.notes()] == [s.id]
    assert p.confirm(s.id, True) == []   # idempotent


def test_pending_blocks_later_segments_and_related_follower_redacted():
    p = Pipeline(hold_seconds=5)
    s1 = seg("There will be layoffs in the support org.", 0)
    s2 = seg("The layoffs will hit twenty people.", 1)
    s3 = seg("Lunch is at noon.", 2)
    for s in (s1, s2, s3):
        p.push(s, now=s.t_start)
    assert p.tick(100) == []
    p.confirm(s1.id, keep_out=True)
    p.tick(100)
    assert [x.id for x in p.notes()] == [s3.id]


def test_implicit_with_llm_and_mock():
    llm = MockLLM({"Utterance": '{"sensitive": true, "category": "hr"}'})
    p = Pipeline(llm=llm, hold_seconds=5)
    ev = p.push(seg("We should talk about Sam privately.", 0), now=0)
    assert any(e.kind == "pending_confirm" and e.reason == "llm:hr" for e in ev)
    assert classify_sensitivity(None, "The sprint review is on Tuesday.") == (False, "none")
    assert classify_sensitivity(MockLLM(default="garbage"), "her salary is high")[0] is True
    assert extract_json('sure! {"a": 1} ok') == {"a": 1}


def test_false_alarm_does_not_trigger():
    for text in [
        "Did you see the movie Off the Record last night?",
        'I loved the documentary "Off the Record" on Netflix.',
        "Off the Record is a great film honestly.",
        "That statement is not off the record, it's public.",
        "The difference between us and the competitor is price.",
    ]:
        assert detect(text).kind is None, text
    p = Pipeline(hold_seconds=5)
    run(p, [("Did you see the movie Off the Record last night?", 0),
            ("It was a great film about journalism.", 2)])
    assert "Off the Record" in note_text(p) and p.state == "ON"
    assert detect("Off the record, he's leaving").kind == "start"
    assert detect("that stays between us").kind == "start"
    assert detect("not for the notes please").kind == "start"


def test_pii_redacted():
    masked, labels = redact_pii(
        "Mail bob@example.com or call 415-555-0199, SSN 123-45-6789, card 4111 1111 1111 1111.", False)
    for raw in ("bob@example.com", "415-555-0199", "123-45-6789", "4111 1111 1111 1111"):
        assert raw not in masked
    assert set(labels) == {"EMAIL", "PHONE", "SSN", "CREDIT_CARD"}
    p = Pipeline(hold_seconds=1)
    run(p, [("Reach me at alice@corp.io about the release.", 0)])
    assert "alice@corp.io" not in note_text(p) and "[EMAIL]" in note_text(p)
    assert "release" in note_text(p)
    assert redact_pii("Nothing private here.", False) == ("Nothing private here.", [])
