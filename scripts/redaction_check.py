"""Quick redaction check: runs scripted conversations through the real pipeline and prints PASS or FAIL.

Usage:
  python scripts/redaction_check.py                 # rules only, no model
  python scripts/redaction_check.py --llm ollama    # also use the local model (OTR_LLM_MODEL, default granite4.2:3b)
  python scripts/redaction_check.py --verbose       # show every line and what happened to it
  python scripts/redaction_check.py --live          # print the lines to say aloud into the meeting, case by case

Each case lists text that must NOT appear in the final notes (hidden) and text that must stay (visible).
A line that is still waiting for an answer at the end of the meeting is treated as kept out.
These cases were written to demo the behaviour, they are not a benchmark and are not independent evidence.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from otr.pipeline import Pipeline  # noqa: E402
from otr.types import Segment  # noqa: E402

# (case name, [(speaker, text)], hidden phrases, visible phrases)
CASES = [
    ("Explicit off the record, then back on",
     [("Ana", "Let's start with the launch plan for March."),
      ("Ben", "Before that, this next part is off the record please."),
      ("Ben", "The vendor contract is being terminated and nobody outside this call knows."),
      ("Ana", "Understood, I will keep that to myself."),
      ("Ben", "Okay, back on the record."),
      ("Ana", "So the launch date stays March twelfth.")],
     ["vendor contract is being terminated", "keep that to myself"],
     ["launch plan for March", "launch date stays March twelfth"]),

    ("Between us, plus a reaction from someone else",
     [("Ana", "Quick status on the migration."),
      ("Ben", "Between us, the reorg will cut the platform team by half."),
      ("Ana", "Wow, I did not expect that."),
      ("Ben", "Alright, we can write things down again."),
      ("Ana", "Next step is the database cutover on Friday.")],
     ["cut the platform team by half", "did not expect that"],
     ["status on the migration", "database cutover on Friday"]),

    ("Strike that, removes a line that is still waiting",
     [("Ana", "We will ship the beta to fifty customers."),
      ("Ana", "Actually, strike that, I should not have said fifty."),
      ("Ben", "Fine, we keep the customer count out of the notes."),
      ("Ben", "The beta ships on the fourteenth.")],
     ["fifty customers"],
     ["beta ships on the fourteenth"]),

    ("Retraction by topic",
     [("Ana", "The renewal price went up twelve percent."),
      ("Ben", "Let's get the legal review scheduled."),
      ("Ana", "Please forget what I said about the renewal price."),
      ("Ben", "Legal review is booked for Thursday.")],
     ["renewal price went up twelve percent"],
     ["legal review is booked for Thursday"]),

    ("Salary mention without any spoken cue",
     [("Ana", "One more item on staffing."),
      ("Ben", "The new hire is asking for one hundred forty thousand dollars in salary."),
      ("Ana", "That is above the band for that level."),
      ("Ben", "Let's move on to the roadmap.")],
     ["one hundred forty thousand dollars in salary"],
     ["item on staffing"]),

    ("Health information",
     [("Ana", "Planning the sprint now."),
      ("Ben", "I need to tell you my biopsy came back and I start chemotherapy next month."),
      ("Ana", "Take whatever time you need."),
      ("Ben", "Back to the sprint, we have six tickets left.")],
     ["biopsy came back", "chemotherapy"],
     ["sprint now", "six tickets left"]),

    ("Phone number split across two lines",
     [("Ana", "You can reach me on four one five five five five."),
      ("Ana", "zero one nine nine if the line drops."),
      ("Ben", "Got it, and the email is dana dot lee at acme dot com."),
      ("Ben", "We confirm the demo for Monday.")],
     ["four one five five five five zero one nine nine", "dana dot lee at acme dot com", "dana.lee@acme.com"],
     ["demo for Monday"]),

    ("False alarm: a movie called Off the Record",
     [("Ana", "Did you see the movie Off the Record last night?"),
      ("Ben", "Yes, the ending was great."),
      ("Ana", "Anyway, the release notes are due tomorrow.")],
     [],
     ["movie Off the Record", "release notes are due tomorrow"]),

    ("Public look-alikes must stay",
     [("Ana", "Our salary calculator launched last month and it is public."),
      ("Ben", "The health insurance enrollment deadline is Friday."),
      ("Ana", "The HR portal link is in the wiki.")],
     [],
     ["salary calculator launched", "enrollment deadline is Friday", "HR portal link"]),

    ("Repair, not a retraction",
     [("Ana", "The review is on Monday."),
      ("Ana", "Strike that, I meant Tuesday."),
      ("Ben", "Tuesday works for me.")],
     [],
     ["Tuesday works for me"]),
]


def run_case(speakers_lines, llm, hold: float):
    pipe = Pipeline(llm=llm, hold_seconds=hold)
    log, now = [], 0.0
    for i, (who, text) in enumerate(speakers_lines):
        seg = Segment(id=f"s{i:02d}", speaker=who, text=text, t_start=now, t_end=now + 4.0)
        now += 6.0
        for ev in pipe.push(seg, now=seg.t_end):
            log.append(ev)
        for ev in pipe.tick(now):
            log.append(ev)
    for ev in pipe.tick(now + hold + 1):
        log.append(ev)
    for ev in pipe.flush():
        log.append(ev)
    return pipe, log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check redaction on scripted conversations")
    ap.add_argument("--llm", choices=["none", "ollama"], default="none")
    ap.add_argument("--hold", type=float, default=4.0, help="hold seconds used for the check")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--live", action="store_true", help="print what to say aloud, case by case, and exit")
    a = ap.parse_args(argv)

    if a.live:
        print("Say these lines in a meeting with notes ON, one person per speaker name if you can.")
        print("After each case, look at the notes and at what was kept out.\n")
        for name, lines, hidden, visible in CASES:
            print(f"== {name}")
            for who, text in lines:
                print(f"   {who}: {text}")
            if hidden:
                print(f"   expected kept out: {hidden}")
            print(f"   expected in notes: {visible}\n")
        return 0

    llm = None
    if a.llm == "ollama":
        from otr.llm import OllamaLLM
        llm = OllamaLLM()
        print(f"using local model {getattr(llm, 'model', '?')}")

    failed = 0
    print(f"{'case':52} result   notes  kept-out  reasons")
    for name, lines, hidden, visible in CASES:
        pipe, log = run_case(lines, llm, a.hold)
        notes_text = " ".join(s.text for s in pipe.notes()).lower()
        leaks = [h for h in hidden if h.lower() in notes_text]
        lost = [v for v in visible if v.lower() not in notes_text]
        ok = not leaks and not lost
        failed += 0 if ok else 1
        reasons = sorted({e.reason.split("(")[0] for e in log if e.kind in ("redacted", "retro_removed", "pending_confirm")})
        kept_out = len({e.segment_id for e in log if e.kind in ("redacted", "retro_removed", "pending_confirm")})
        print(f"{name[:51]:52} {'PASS' if ok else 'FAIL':8} {len(pipe.notes()):<6} {kept_out:<9} {', '.join(reasons)[:60]}")
        if not ok:
            for h in leaks:
                print(f"      LEAK: '{h}' reached the notes")
            for v in lost:
                print(f"      LOST: '{v}' was removed but should stay")
        if a.verbose:
            kept = {s.id for s in pipe.notes()}
            for i, (who, text) in enumerate(lines):
                sid = f"s{i:02d}"
                where = "NOTES   " if sid in kept else "kept out"
                print(f"      {where} {who}: {text}")
    print(f"\n{len(CASES) - failed} of {len(CASES)} cases passed (llm={a.llm}, hold={a.hold}s)")
    return 1 if failed else 0


if __name__ == "__main__":
    os.environ.setdefault("OTR_NO_PRESIDIO", "")
    raise SystemExit(main())
