"""Generalisation tests: paraphrased start / end / retract cues that were NOT used to build the
phrase lists. Each case is a small scripted meeting. `P` lines are private (must never reach the
notes), `R` lines are public text that a retraction must remove, `K` lines are public and must be
kept (omission is also measured), `S` lines are implicit-sensitive (must reach PENDING_CONFIRM and
stay out unless confirmed).

Every case runs in three modes: no LLM, a MockLLM that knows nothing (replies "none"), and a
MockLLM scripted with what a competent model would say about the uncertain utterances.
Cases in HARD need the LLM fallback; without it they are *expected* to leak and the tests record
that honestly (see test_hard_cases_need_llm).
"""
import json
import os

os.environ.setdefault("OTR_NO_PRESIDIO", "1")

import pytest

from otr import cue_detector as cd
from otr.llm import MockLLM
from otr.pipeline import Pipeline
from otr.types import Segment

CUE_KEY = "retract note-taking"          # marker of the cue-intent prompt


def L(spec):
    return [(f"u{i}", sp, kind, text) for i, (sp, kind, text) in enumerate(spec)]


CASES = {
    # --- the fresh example from the bug report ---------------------------------------------
    "fresh": L([
        ("Dee", "K", "Let's lock the launch checklist. Docs are done and QA signs off Friday."),
        ("Sam", "P", "Quick thing, can we keep this part out of the notes? Finance told me the Series B term sheet is delayed until January."),
        ("Sam", "P", "So the runway number I gave the board is basically fiction, we have about five months of cash."),
        ("Dee", "P", "Wow. Okay, I won't repeat that to anyone."),
        ("Sam", "E", "Alright, we can write things down again."),
        ("Dee", "K", "Back to launch. Who owns the press release?"),
        ("Sam", "C", "I will. Also, scratch the bit about QA, I misspoke, they sign off Monday."),
        ("Dee", "S", "Noted. Also my doctor wants me out for two weeks for the surgery, so Lee covers the checklist."),
    ]),
    # --- 10 paraphrase variants (written after the detector, different wording) -------------
    "v1_prefer_minutes": L([
        ("Ana", "K", "Let's review the onboarding funnel numbers for the quarter."),
        ("Ben", "P", "I'd prefer this not end up in the minutes. Marcus is being let go at the end of next month."),
        ("Ana", "P", "Understood, I'll keep that to myself, and HR has not told him yet."),
        ("Ben", "E", "Okay, resume the notes."),
        ("Ana", "K", "The funnel conversion improved from four to six percent."),
    ]),
    "v2_writeup": L([
        ("Cy", "K", "The sprint demo is on Thursday afternoon."),
        ("Di", "P", "Please don't put this in the write-up: the security audit found an unencrypted backup bucket."),
        ("Cy", "P", "That is bad, how long has the bucket been exposed to the internet?"),
        ("Di", "P", "Since March, as far as the logs show."),
        ("Cy", "E", "Notes are back on."),
        ("Di", "K", "So for the demo we need the new dashboard ready by Wednesday."),
    ]),
    "v3_asr_noise_keep_nodes": L([
        ("Eve", "K", "Next up is the vendor contract renewal timeline."),
        ("Fay", "P", "can we keap this part out of the nodes. the vendor is about to sue us over the missed deliveries"),
        ("Eve", "P", "oh no, did legal see the demand letter yet?"),
        ("Fay", "E", "ok you can go ahead and write again"),
        ("Eve", "K", "Renewal decisions are due at the end of the quarter."),
    ]),
    "v4_asr_noise_no_punct": L([
        ("Gus", "K", "we start the offsite planning tomorrow morning"),
        ("Hal", "P", "uh could we leave that out of the recored for now the board is thinking about selling the company"),
        ("Gus", "P", "interesting who is the buyer then"),
        ("Hal", "E", "okay we can start recording again"),
        ("Gus", "K", "so the offsite agenda needs three sessions"),
    ]),
    "v5_skip_notes": L([
        ("Ivy", "K", "The design review notes go out after the call."),
        ("Jon", "P", "Skip the notes for this one, Priya's visa application got denied last week."),
        ("Ivy", "P", "That is awful, is the company going to appeal the decision for her?"),
        ("Jon", "E", "Alright, that's the private part done, notes are back on."),
        ("Ivy", "K", "Back to the design review: the navigation needs another pass."),
    ]),
    "v6_between_us_leave_out": L([
        ("Kim", "K", "Quarterly objectives are drafted and shared with the leads."),
        ("Lou", "P", "Between us, can you keep the next bit out of the minutes? Our biggest customer is leaving in June."),
        ("Kim", "P", "That would be a fifth of our revenue, how sure are we about it?"),
        ("Lou", "E", "We can take notes again."),
        ("Kim", "K", "Let's finalise the objectives list before the all hands."),
    ]),
    "v7_retract_disregard": L([
        ("Max", "R", "The Atlas migration lands in Q2 for all regions."),
        ("Max", "K", "Support tickets dropped by a third this month."),
        ("Max", "C", "Disregard what I said about the Atlas migration, I misspoke, it is moving to Q4 for all regions."),
        ("Nia", "K", "Thanks, so Q4 it is, we update the roadmap today."),
    ]),
    "v8_retract_noisy": L([
        ("Oz", "R", "Pricing for the pro plan will be thirty nine dollars."),
        ("Pam", "K", "We also plan a student discount in the fall."),
        ("Oz", "C", "scrach the number about pricing, i misspoke, it will be forty nine dollars"),
        ("Pam", "K", "Good, forty nine dollars goes on the pricing page."),
    ]),
    "v9_retract_take_back_plus_private": L([
        ("Quin", "R", "The rollout to Europe starts in January."),
        ("Rae", "P", "Off the record, the Europe rollout is only a fig leaf, legal blocked the entire plan."),
        ("Quin", "P", "Right, I will not repeat that to the team."),
        ("Rae", "E", "Okay, back on the record."),
        ("Quin", "C", "Take back what I said about the Europe rollout, I got that wrong, it starts in March."),
    ]),
    "v10_llm_only_paraphrase": L([
        ("Sol", "K", "The hiring plan has four open roles for engineering."),
        ("Tia", "P", "Let's pretend this conversation never happened as far as the minutes go. The CFO is leaving after the board meeting."),
        ("Sol", "P", "Wow, that is a big change, who takes over finance after her?"),
        ("Tia", "E", "Enough secrecy, scribe away again."),
        ("Sol", "K", "Okay, the hiring plan needs headcount approval by Friday."),
    ]),
}
HARD = {"v10_llm_only_paraphrase"}       # structured detector alone cannot see these cues

# what a competent LLM would say about the uncertain utterances of each case
LLM_SCRIPT = {
    "Let's pretend this conversation never happened as far as the minutes go": {"intent": "start", "topic": ""},
    "Enough secrecy, scribe away again.": {"intent": "end", "topic": ""},
}


def make_llm(mode):
    if mode == "nollm":
        return None
    if mode == "blank":
        return MockLLM(lambda pr: '{"intent":"none","topic":""}' if CUE_KEY in pr else "{}")

    def reply(pr):
        if CUE_KEY in pr:
            for k, v in LLM_SCRIPT.items():
                if k in pr:
                    return json.dumps(v)
            return '{"intent":"none","topic":""}'
        return "{}"
    return MockLLM(reply)


def run_case(name, mode, confirm=None):
    p = Pipeline(llm=make_llm(mode), hold_seconds=30)
    pending = []
    ev = []
    for i, (sid, sp, kind, text) in enumerate(CASES[name]):
        ev += p.push(Segment(sid, sp, text, i * 6.0, i * 6.0 + 4), now=i * 6.0 + 4)
    pending = [e.segment_id for e in ev if e.kind == "pending_confirm"]
    if confirm is not None:
        for sid in pending:
            ev += p.confirm(sid, keep_out=confirm)
    ev += p.tick(10_000)
    ev += p.flush()
    kept = {s.id for s in p.notes()}
    kinds = {sid: kind for sid, _, kind, _ in CASES[name]}
    return p, ev, kept, kinds, pending


def leaks(name, mode):
    _, _, kept, kinds, _ = run_case(name, mode)
    return sorted(i for i in kept if kinds[i] in ("P", "R", "S"))


def omissions(name, mode):
    _, _, kept, kinds, _ = run_case(name, mode)
    return sorted(i for i, k in kinds.items() if k in ("K", "C") and i not in kept)


MODES = ["nollm", "blank", "scripted"]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name", [n for n in CASES if n not in HARD])
def test_no_private_leak(name, mode):
    assert leaks(name, mode) == [], (name, mode)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name", [n for n in CASES if n not in HARD])
def test_public_content_kept(name, mode):
    # the retraction policy removes the retracted segment as a whole (that segment is "R", not "K")
    assert omissions(name, mode) == [], (name, mode)


def test_hard_case_with_llm_fallback():
    assert leaks("v10_llm_only_paraphrase", "scripted") == []
    assert omissions("v10_llm_only_paraphrase", "scripted") == []


def test_hard_cases_need_llm():
    """Honest record: a paraphrase with none of the structural features leaks without the LLM
    fallback (and with an LLM that says 'none'). If this starts passing, the detector improved."""
    for mode in ("nollm", "blank"):
        assert leaks("v10_llm_only_paraphrase", mode) != [], mode


# ------------------------------------------------------------------ the fresh example in detail
def test_fresh_example_u1_whole_utterance_redacted_and_scope_off():
    p, ev, kept, kinds, pending = run_case("fresh", "nollm")
    assert kept == {"u5", "u6"}
    red = {e.segment_id: e.reason for e in ev if e.kind == "redacted"}
    assert red["u1"].startswith("cue:")                      # request + secret in one utterance
    assert red["u2"] == "scope:off" and red["u3"] == "scope:off"   # content + reaction stay out
    assert [e.state for e in ev if e.kind == "state_change"][:2] == ["OFF", "ON"]


def test_fresh_example_retraction_policy():
    p, ev, kept, kinds, _ = run_case("fresh", "nollm")
    # earlier public statement about QA removed (it was still held: redacted with retro reason)
    assert any(e.segment_id == "u0" and e.reason.startswith("retro:match") for e in ev)
    # the correction itself is kept, without the retract clause
    txt = {s.id: s.text for s in p.notes()}
    assert "Monday" in txt["u6"] and "scratch" not in txt["u6"].lower() and "misspoke" not in txt["u6"]


def test_retraction_removes_already_committed_statement():
    p = Pipeline(hold_seconds=5)
    p.push(Segment("a", "Max", "QA signs off on the release Friday afternoon.", 0, 3), now=3)
    p.tick(100)                                              # committed
    p.push(Segment("b", "Max", "Scratch the bit about QA, I misspoke, they sign off Monday morning.", 110, 114), now=114)
    p.tick(1000)
    p.flush()
    assert [s.id for s in p.notes()] == ["b"]
    assert any(e.kind == "retro_removed" and e.segment_id == "a" for e in p.audit_log())


def test_sensitive_mention_in_on_state_goes_to_pending_confirm():
    p, ev, kept, kinds, pending = run_case("fresh", "nollm")
    assert pending == ["u7"] and "u7" not in kept
    p, ev, kept, kinds, pending = run_case("fresh", "nollm", confirm=False)
    assert "u7" in kept                                      # user said keep it in
    p, ev, kept, kinds, pending = run_case("fresh", "nollm", confirm=True)
    assert "u7" not in kept


# ------------------------------------------------------------------ false alarms must not trigger
PUBLIC_MENTIONS = [
    "Can you send the notes from yesterday's call to Lee?",
    "Please keep the meeting notes in Notion, not in Confluence.",
    "Let's record the demo video for the website tomorrow.",
    "The record shows revenue grew twelve percent last quarter.",
    "Don't forget to write the release notes before Friday.",
    "I am not in the notes channel anymore.",
    "We should skip the retrospective this sprint since the release is close.",
    "Did we keep the budget out of the minutes last time?",
    "I'd rather we ship the notes feature first, then the export.",
    "Can we forget about the old deadline, we can't make it anyway?",
    "She said the phrase \"keep this out of the notes\" is in the template.",
    "The bank keeps a record of every transaction we make.",
]


@pytest.mark.parametrize("text", PUBLIC_MENTIONS)
def test_public_mentions_are_not_cues(text):
    c = cd.detect(text)
    assert c.kind is None, (text, c)


def test_public_mentions_not_leaked_end_to_end():
    p = Pipeline(llm=None, hold_seconds=5)
    for i, t in enumerate(PUBLIC_MENTIONS):
        p.push(Segment(f"m{i}", "A", t, i * 6.0, i * 6.0 + 4), now=i * 6.0 + 4)
    p.tick(10_000)
    p.flush()
    assert len(p.notes()) == len(PUBLIC_MENTIONS)


# ------------------------------------------------------------------ LLM fallback mechanics
def _ask(llm, text, **kw):
    p = Pipeline(llm=llm, hold_seconds=30, **kw)
    ev = p.push(Segment("x", "A", text, 0, 3), now=3)
    return p, ev


def test_llm_not_called_for_ordinary_or_certain_segments():
    llm = MockLLM(lambda pr: '{"intent":"none","topic":""}' if CUE_KEY in pr else '{"sensitive": false}')
    p = Pipeline(llm=llm, hold_seconds=30)
    for i, t in enumerate(["We ship the dashboard next sprint.", "Off the record, the deal is falling apart.",
                           "Can we keep this part out of the notes?", "Back on the record.",
                           "Revenue is up and churn is down this month."]):
        p.push(Segment(f"s{i}", "A", t, i * 5.0, i * 5.0 + 3), now=i * 5.0 + 3)
    assert not any(CUE_KEY in pr for pr in llm.prompts)
    assert p.stats["cue_llm_calls"] == 0


def test_llm_called_only_when_gate_signal_and_no_cue():
    llm = MockLLM(lambda pr: '{"intent":"none","topic":""}' if CUE_KEY in pr else '{"sensitive": false}')
    p = Pipeline(llm=llm, hold_seconds=30)
    p.push(Segment("a", "A", "The minutes from last week are in the shared folder.", 0, 3), now=3)
    p.push(Segment("b", "A", "Lunch is at noon.", 4, 6), now=6)
    assert p.stats["cue_llm_calls"] == 1


def test_llm_failure_timeout_and_garbage_fall_back_to_structured():
    def boom(pr):
        if CUE_KEY in pr:
            raise RuntimeError("down")
        return "{}"
    p, ev = _ask(MockLLM(boom), "Can we keep this part out of the notes? The deal closes in May.")
    assert p.state == "OFF"                                   # certain structured cue still acts
    p, ev = _ask(MockLLM(lambda pr: "not json at all"), "Skip the notes for this: Priya's visa got denied.")
    assert p.state == "OFF"

    import time

    def slow(pr):
        time.sleep(1.0)
        return '{"intent":"none","topic":""}'
    t0 = time.time()
    p, ev = _ask(MockLLM(slow), "Skip the notes for this: Priya's visa got denied.", cue_llm_timeout=0.1)
    assert time.time() - t0 < 0.9 and p.state == "OFF"
    assert p.stats["cue_llm_failures"] == 1


def test_llm_can_veto_a_weak_structured_start():
    text = "That is not in the notes channel, it is in the minutes folder."   # weak: object + generic negation
    c = cd.detect(text)
    assert c.kind == "start" and c.weak and not c.accept_alone
    p, _ = _ask(None, text)
    assert p.state == "ON"                                     # no LLM: weak generic cue is not acted on
    llm = MockLLM(lambda pr: '{"intent":"start","topic":""}' if CUE_KEY in pr else "{}")
    p, _ = _ask(llm, text)
    assert p.state == "OFF"                                    # LLM confirms
    llm = MockLLM(lambda pr: '{"intent":"none","topic":""}' if CUE_KEY in pr else "{}")
    p, _ = _ask(llm, text)
    assert p.state == "ON"


def test_circuit_breaker_stops_calling_a_dead_llm():
    calls = []

    def bad(pr):
        calls.append(pr)
        return "garbage"
    p = Pipeline(llm=MockLLM(bad), hold_seconds=30)
    for i in range(10):
        p.push(Segment(f"g{i}", "A", f"Item {i}: the minutes are in folder number {i}.", i * 2.0, i * 2.0 + 1), now=i * 2.0 + 1)
    assert p.stats["cue_llm_calls"] == 3                       # breaker opened after 3 failures


def test_asr_noise_variants_detected_without_llm():
    for t, kind in [("can we keap this part out of the nodes", "start"),
                    ("could we leave that out of the recored", "start"),
                    ("ok we can start recording again", "end"),
                    ("scrach the number about pricing i misspoke", "retro")]:
        assert cd.detect(t).kind == kind, t
