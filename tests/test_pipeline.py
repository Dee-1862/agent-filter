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


def test_llm_topic_change_alone_does_not_end_scope():
    # Fail closed: a model verdict of "topic changed" may not end an off-the-record stretch by itself.
    llm = MockLLM(lambda pr: '{"topic_changed": true}' if "Has the conversation moved on" in pr else "{}")
    p = Pipeline(llm=llm, hold_seconds=10)
    run(p, [("Between us, the budget is overspent.", 0), ("What about the picnic menu then?", 2)])
    assert "budget" not in note_text(p) and "picnic" not in note_text(p)


def test_llm_topic_change_with_a_pivot_phrase_ends_scope():
    llm = MockLLM(lambda pr: '{"topic_changed": true}' if "Has the conversation moved on" in pr else "{}")
    p = Pipeline(llm=llm, hold_seconds=10)
    run(p, [("Between us, the budget is overspent.", 0), ("Okay, anyway, what about the picnic menu then?", 2),
            ("Anyway, the picnic menu needs a vegetarian option.", 4)])
    assert "budget" not in note_text(p)


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
    # s3 (unrelated) is undecided: the kept-out thread only ends on provable drift (3 off-topic lines)
    s4 = seg("The conference room booking starts at nine tomorrow.", 3)
    s5 = seg("Please bring the quarterly planning documents along.", 4)
    p.push(s4, now=104)
    p.push(s5, now=105)
    p.tick(200)
    assert [x.id for x in p.notes()] == [s3.id, s4.id, s5.id]
    assert s2.id not in [x.id for x in p.notes()]


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


# ------------------------------------------------------------------ I1: conservative scope end
def sg(i, text, t0, t1=None, speaker="A"):
    return Segment(id=i, speaker=speaker, text=text, t_start=t0, t_end=t1 if t1 is not None else t0 + 1.5)


def feed(p, segs):
    ev = []
    for s in segs:
        ev += p.push(s, now=s.t_end)
        ev += p.tick(s.t_end)
    return ev


def test_scope_stays_off_until_explicit_end_even_with_vocabulary_shift():
    p = Pipeline(hold_seconds=10)
    feed(p, [
        sg("a", "Okay, quarterly planning review is done.", 0),
        sg("b", "Can we go off the record for a minute?", 3),
        sg("c", "I heard the Northwind acquisition talks are at forty million.", 5),
        sg("d", "That would mean we freeze hiring until the deal closes.", 8),
        sg("e", "Right, and keep Elena's team in the dark until legal signs off.", 11),
        sg("f", "Okay, back on the record.", 14),
        sg("g", "For design we need two more weeks for onboarding.", 17),
    ])
    p.tick(500)
    p.flush()
    out = note_text(p)
    assert "Northwind" not in out and "freeze hiring" not in out and "legal signs off" not in out
    assert "quarterly planning" in out and "onboarding" in out


def test_implicit_end_on_pivot_phrase_with_no_overlap():
    p = Pipeline(hold_seconds=10)
    feed(p, [
        sg("a", "Off the record, Joel was fired for harassment at his last job.", 0),
        sg("b", "Then we should quietly reject him and keep the reason out of writing.", 3),
        sg("c", "Agreed, his references also mentioned a drinking problem.", 6),
        sg("d", "Anyway, for the data engineer role we need Spark experience.", 9),
        sg("e", "I will post the revised job description on Monday.", 12),
    ])
    p.tick(500)
    p.flush()
    out = note_text(p)
    assert "Joel" not in out and "drinking" not in out and "quietly reject" not in out
    assert "Spark experience" in out and "job description" in out


def test_implicit_end_on_sustained_drift_releases_the_drifted_lines():
    p = Pipeline(hold_seconds=10)
    feed(p, [
        sg("a", "Off the record, the vendor deal is falling apart badly.", 0),
        sg("b", "Their CEO is very unhappy with our pricing proposal.", 3),
        sg("c", "The conference room booking starts at nine tomorrow.", 6),
        sg("d", "Please bring the quarterly planning documents along.", 9),
        sg("e", "Lunch order closes before eleven so decide quickly.", 12),
        sg("f", "Parking passes are available at the front desk.", 15),
    ])
    p.tick(500)
    p.flush()
    out = note_text(p)
    # the first two lines after the cue are always scope (grace); then 3 off-topic lines in a row = drift
    assert "vendor" not in out and "pricing" not in out and "conference room" not in out
    assert "quarterly planning" in out and "Lunch order" in out and "Parking passes" in out


def test_scope_timeout_ends_off_scope():
    p = Pipeline(hold_seconds=10)
    feed(p, [sg("a", "Off the record, the vendor deal is falling apart.", 0),
             sg("b", "Their CEO is very unhappy with our pricing.", 3),
             sg("c", "Reminder that the offsite agenda is posted.", 300)])
    p.tick(1000)
    assert "offsite agenda" in note_text(p)


# ------------------------------------------------------------------ I2: live hold_seconds
def test_hold_seconds_is_live():
    p = Pipeline(hold_seconds=60)
    s = sg("x1", "We ship the dashboard next sprint.", 0)
    p.push(s, now=1)
    assert p.tick(30) == []
    p.hold_seconds = 5               # slider moved after the segment was already held
    assert [e.kind for e in p.tick(30)] == ["committed"]
    p.hold_seconds = 100
    p.push(sg("x2", "Another public planning remark here.", 40), now=41)
    assert p.tick(120) == []
    p.hold_seconds = 10
    assert [e.kind for e in p.tick(120)] == ["committed"]


# ------------------------------------------------------------------ streaming hardening
def test_duplicate_segment_ids_are_ignored():
    p = Pipeline(hold_seconds=1)
    s = sg("dup", "Public planning remark about the roadmap.", 0)
    assert [e.kind for e in p.push(s, now=1)] == ["held"]
    assert p.push(s, now=1) == []
    p.tick(10)
    assert p.push(s, now=11) == []
    assert [x.id for x in p.notes()] == ["dup"]


def test_clock_that_does_not_advance_and_goes_backwards():
    p = Pipeline(hold_seconds=5)
    p.push(sg("a", "First public remark about the roadmap.", 10), now=10)
    p.push(sg("b", "Second public remark about the budget.", 3), now=3)   # now moves backwards
    assert p.tick(4) == []                                                 # clock still 10, nothing due
    assert len(p.tick(15)) == 2
    assert [x.id for x in p.notes()] == ["b", "a"]                         # time-ordered release


def test_out_of_order_cue_governs_text_transcribed_earlier():
    p = Pipeline(hold_seconds=30)
    p.push(sg("a1", "Let's review the roadmap together today.", 0, 2, "ann"), now=2)
    p.push(sg("b1", "The acquisition price is forty million dollars.", 5, 7, "bob"), now=7)
    ev = p.push(sg("a2", "Off the record please everyone.", 3, 4, "ann"), now=8)   # late, earlier t_start
    assert p.state == "OFF"
    assert any(e.kind == "redacted" and e.segment_id == "b1" for e in ev)
    p.tick(100)
    p.flush()
    assert "acquisition" not in note_text(p) and "roadmap" in note_text(p)


def test_overlapping_speakers_interleaved():
    p = Pipeline(hold_seconds=30)
    p.push(sg("a", "Off the record, the layoffs list is long.", 0, 6, "ann"), now=6)
    p.push(sg("b", "Meanwhile the cafeteria menu changes tomorrow.", 2, 5, "bob"), now=7)   # overlaps ann
    p.tick(100)
    p.flush()
    assert "layoffs" not in note_text(p)


def test_thread_safety_concurrent_push_tick_confirm():
    import threading
    p = Pipeline(hold_seconds=1)
    errs = []

    def worker(k):
        try:
            for i in range(40):
                s = sg(f"w{k}-{i}", f"Public status update number {i} from worker {k}.", i, i + 1, f"s{k}")
                p.push(s, now=i + 1)
                p.tick(i + 2)
                p.confirm("nope", True)
                p.notes(), p.audit_log()
        except Exception as e:      # pragma: no cover
            errs.append(e)

    ts = [threading.Thread(target=worker, args=(k,)) for k in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    p.tick(10_000)
    p.flush()
    assert not errs and len(p.notes()) == 240


# ------------------------------------------------------------------ ASR noise
def test_noisy_asr_cues():
    assert detect("of the record he is leaving the company").kind == "start"
    assert detect("OFF DA RECORD for a second").kind == "start"
    assert detect("hold on awf the record").kind == "start"
    assert detect("strike dat please").kind == "retro"
    assert detect("scratch dat").kind == "retro"
    assert detect("okay we are back on da record").kind == "end"
    # fuzzy matching must not turn ordinary speech into cues
    for t in ["we are on the record with this statement", "the rest of the record shows growth",
              "a copy of the record is attached", "he is a strikingly good manager",
              "we need the end of the record keeping system"]:
        assert detect(t).kind != "start", t
    assert detect("the rest of the record shows growth").kind is None
    assert detect("Did you see the movie Of The Record last night").kind is None
    assert detect("Off the record is a great film honestly").kind is None


def test_noisy_cue_end_to_end():
    p = Pipeline(hold_seconds=10)
    feed(p, [sg("a", "we should ship friday", 0),
             sg("b", "of the record the vendor deal is dead", 3),
             sg("c", "their ceo hates our pricing proposal", 6),
             sg("d", "okay back on da record", 9),
             sg("e", "next the launch checklist please", 12)])
    p.tick(500)
    p.flush()
    out = note_text(p)
    assert "vendor" not in out and "pricing" not in out and "launch checklist" in out
    q = Pipeline(hold_seconds=30)
    feed(q, [sg("a", "pricing tier launches in june", 0), sg("b", "dana will leave for a competitor", 3),
             sg("c", "strike dat", 5)])
    q.flush()
    assert "competitor" not in note_text(q) and "pricing" in note_text(q)


# ------------------------------------------------------------------ I3 salary keyword framing
def test_salary_keywords_need_person_directed_framing():
    from otr.llm import keyword_sensitivity as ks
    for t in ["The salary calculator we launched has a new design.",
              "Compensation planning kickoff for the merit cycle.",
              "He is open to a compensation off the record, meaning outside the bands.",
              "Our paid time off policy is changing.",
              "Revenue doubled from 3 to 6 million in a year."]:
        assert ks(t) == (False, "none"), t
    for t in ["Her salary is the highest on the team.", "I'll bump Rosa's salary to 135.",
              "They offered me 210 thousand base.", "We should give him a raise.",
              "The salary band for this role is 140k.", "The CFO's bonus is 450 thousand."]:
        assert ks(t)[1] == "salary", t


# ------------------------------------------------------------------ I6 "strike that" rule
def test_strike_that_self_correction_rule():
    # same speaker, recent -> removes the previous line
    p = Pipeline(hold_seconds=60)
    feed(p, [sg("a", "Totally unrelated agenda item for planning.", 0, 2, "ann"),
             sg("b", "The secret codename is Falcon project.", 20, 22, "ann"),
             sg("c", "Strike that.", 23, 24, "ann")])
    p.flush()
    assert [s.id for s in p.notes()] == ["a"]
    # previous line is old (beyond the window): nothing is removed, the cue line itself is dropped
    p = Pipeline(hold_seconds=60)
    feed(p, [sg("a", "Totally unrelated agenda item for planning.", 0, 2, "ann"),
             sg("b", "Strike that.", 60, 61, "ann")])
    p.flush()
    assert [s.id for s in p.notes()] == ["a"]
    # another speaker's older line is not removed either
    p = Pipeline(hold_seconds=60)
    feed(p, [sg("a", "Budget numbers look rough this quarter honestly.", 0, 2, "bob"),
             sg("b", "Strike that.", 9, 10, "ann")])
    p.flush()
    assert [s.id for s in p.notes()] == ["a"]
    # a named topic overrides recency
    p = Pipeline(hold_seconds=60)
    feed(p, [sg("a", "Dana will leave for a competitor soon.", 0, 2, "bob"),
             sg("b", "Lunch plans are posted in the channel.", 30, 32, "bob"),
             sg("c", "Strike that, forget what I said about Dana.", 90, 92, "bob")])
    p.flush()
    assert [s.id for s in p.notes()] == ["b"]
    # counted retraction
    p = Pipeline(hold_seconds=60)
    feed(p, [sg("a", "Public roadmap update for the quarter.", 0, 2, "ann"),
             sg("b", "Private rumor one about layoffs coming.", 3, 5, "ann"),
             sg("c", "Private rumor two about the merger deal.", 6, 8, "ann"),
             sg("d", "Remove the last two comments please.", 9, 10, "ann")])
    p.flush()
    assert [s.id for s in p.notes()] == ["a"]


def test_implicit_thread_stays_out_after_keep_out():
    p = Pipeline(hold_seconds=10)
    s = sg("m", "My doctor says the diagnosis is serious, I start chemo on Monday.", 0, 3, "ann")
    p.push(s, now=3)
    p.confirm("m", keep_out=True)
    feed(p, [sg("r", "Oh Ann, I'm so sorry, take whatever time you need.", 4, 6, "bob"),
             sg("t", "Thanks. Anyway, for the experiment I'd split traffic fifty fifty.", 8, 11, "ann")])
    p.tick(500)
    p.flush()
    out = note_text(p)
    assert "sorry" not in out and "chemo" not in out
    assert "split traffic" in out


def test_paraphrased_cues_and_hr_keyword():
    assert detect("I'd rather this not go in the notes").kind == "start"
    assert detect("hold off on writing this down").kind == "start"
    assert detect("okay you can start taking notes again").kind == "end"
    assert detect("that's all of the sensitive part").kind == "end"
    assert detect("take that out of the notes, both of those").count == 2
    from otr.llm import keyword_sensitivity as ks
    assert ks("Our salary survey tool for the HR portal is in beta.")[0] is False
    assert ks("Let's add a bonus estimator next.")[0] is False
    assert ks("HR asked me to send it over.")[1] == "hr"
