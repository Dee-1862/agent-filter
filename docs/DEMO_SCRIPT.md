# Demo script and checks

Everything here runs on the laptop. Run the checks first, then the demo.

## 1. One-line checks (run before going on stage)

| Check | Command | Pass looks like |
|---|---|---|
| Everything is installed and running | `python -m otr.app --source livekit --check` | all rows `ok` (LiveKit port may say will start) |
| Redaction rules, no model | `python scripts/redaction_check.py` | 9 of 10 cases pass |
| Redaction with the local model | `python scripts/redaction_check.py --llm ollama` | 10 of 10 cases pass |
| See every line's fate | `python scripts/redaction_check.py --llm ollama --verbose` | NOTES or kept out per line |
| Lines to say aloud | `python scripts/redaction_check.py --live` | prints the script for your real voice |
| Full test suite | `python -m pytest tests -q` | no failures (4 known xfail) |
| Background voices are ignored | `python -m pytest tests/test_nearfield.py -q` | 3 passed |
| Sensitive text never leaves the server | `python -m pytest tests/test_egress.py tests/test_demo.py -q` | all pass |

These redaction cases are demo cases we wrote. They are not an independent benchmark.
The honest benchmark numbers are in `bench/data_v2/README.md` (leak is still high on realistic data).

## 2. Start

```
python -m otr.app --source livekit --port 8010 --fast
```

Open http://127.0.0.1:8010/ for the meeting and http://127.0.0.1:8010/meet for the
Realtime, Insights and Explainability view. Turn your notes on before speaking.
`--fast` shortens the hold to 2 seconds, so a line shows up sooner but a later "strike that" has less time to catch it.

## 3. Three minute live script (say the quoted lines)

1. **Consent at the microphone.** Two people join. One has notes off. Only the person with notes on appears.
   Point out: the bot never subscribes to the other person's audio.
2. **Off the record.** "Before we go on, this next part is off the record." Then "The vendor contract is being cancelled." Then "Okay, back on the record."
   Show: the status changes, the middle line shows as a gray kept-out row, public lines stay.
3. **Strike that.** "We ship to fifty customers." then "Actually, strike that." The line disappears before it was approved.
4. **No cue needed.** "The new hire wants one hundred forty thousand dollars in salary." Kept out as Pay and HR with no spoken signal.
5. **Click a kept-out row.** Show why: rule, state before and after, hold time. No private text is shown.
6. **Insights.** Counts by kind only. Say: it shows what kinds of things were held back, never the content.
7. **Background people.** Have someone talk quietly behind you. Nothing from them appears.

Fallback if audio fails: `python -m otr.app --source replay --script demo/scripts/demo_main.txt --speed 4 --hold 3`.

## 4. How we are different (say only what is true)

Based on `docs/COMPETITORS.md` (vendor pages, not code audits):

- Consent is per person at the audio track. The products we read use per account or per meeting consent.
- Summaries and notes are built only from released text. The big platforms summarize the full transcript, then control who sees it.
- A spoken "off the record" and "strike that" are handled by content, not only a manual pause button.
- You see what kinds of things were withheld and why, with no private text.
- Nothing is stored by default: no audio files, no transcript database.
- No voiceprints. Speaker names come from the meeting identity, which avoids the biometric risk some competitors face.

Where they are better, say so first: speech accuracy, summaries, polish, integrations, scale.

## 5. Do not claim

- "Nothing leaves the laptop" for the Vercel or tunnel setup. Only transcription and filtering stay local there.
- "Zero leaks." On realistic data our leak rate is still high (about 59 to 67 percent without a model). The scripted demo cases pass because we wrote them.
- "End to end private" through any tunnel.
- That the model alone catches everything. The rules decide scope. The model helps with meaning (pay, health).

## 6. About copying

The repository uses the MIT license (see `LICENSE`). That is a deliberate choice for openness:
anyone may copy, modify and ship the code, including commercially, as long as the copyright notice stays.
It does not stop someone from taking the code. If that matters, a source-available license such as
PolyForm Noncommercial, or keeping the repository private, are the options. Not legal advice.

What still protects you under MIT:

- Your authorship record is the dated commit history and the benchmark manifest hashes. Do not squash it.
- The copyright notice must stay in any copy.
- The sealed benchmark split stays out of git.
- Do not put keys or meeting data in the repository.
- The name "Off The Record" is separate from the code. Check that it is free to use before launch.
