# PRD: Off-the-Record Meeting Agent (OTR Agent)

> **How this document works**
> - **Part 1 (Foundation)** is frozen. It holds the core idea, the research question and the architecture. Change it only by an explicit decision, and log that decision in [CHANGES.md](CHANGES.md).
> - **Part 2 (Living Addenda)** is append-only. New scope, refinements, results and open questions go there, each with a date and an ID. Never rewrite an addendum; supersede it with a new one.
> - Lessons go in [LESSONS_LEARNED.md](LESSONS_LEARNED.md). Every addendum change gets a line in [CHANGES.md](CHANGES.md).

---

# PART 1: FOUNDATION (frozen)

## 1.1 Problem

AI meeting notetakers capture everything and have no notion of how people signal privacy in conversation. Three signals matter:

1. **Explicit**: "off the record", "don't write this down".
2. **After the fact**: "strike that", "forget what I said about the layoffs".
3. **Unspoken**: health, salary and HR content that is sensitive from context alone.

Real-world harm is current: litigation over notetaker bots, voiceprint complaints, and surveys showing most people aren't asked before a notetaker joins. (Citations are listed in 1.9 and must be re-verified before being shown publicly.)

## 1.2 Research question

> Can a local meeting agent respect how people signal privacy (explicit "off the record", after-the-fact "strike that", and unspoken sensitive content) without leaking into the notes, and does **structure** beat **prompting alone**?

## 1.3 Hypothesis

An explicit privacy state machine plus a commit-delay hold buffer leaks less than a single LLM pass. The gain should be largest on after-the-fact and implicit cases.

## 1.4 Why it's a real gap

Prior work reports that prompting alone does not fix this. Figures below are as stated in the source plan and must be checked against the papers before use.

- **ConfAIde (ICLR 2024)**: GPT-4 and ChatGPT leak private information in contexts where humans wouldn't (reported 39% and 57%). Privacy-inducing prompts and chain-of-thought did not fully fix it. Its Tier 4 (meeting summarization and action items) is exactly this use case.
- **PrivacyLens (NeurIPS 2024)**: agents leak even with privacy-enhancing instructions (reported 25.68% for GPT-4, 38.69% for Llama-3-70B).

## 1.5 Goals and non-goals

**Goals**
- G1: Live, local transcription feeding a privacy layer before anything reaches the notes.
- G2: Handle all three signal types with measurable leak reduction versus baselines.
- G3: Remove already-committed content on retroactive request, by meaning, with an audit log.
- G4: A reproducible benchmark (OTR-Bench) and a three-system comparison.
- G5: A demo that makes the held / committed / redacted states visible.

**Non-goals (foundation)**
- Joining Zoom, Meet or Teams as a bot.
- Speaker identification or voiceprints.
- Cloud processing of meeting content. Everything runs locally.
- Claiming a final or generalizable result. Results are early evidence.

## 1.6 Architecture (frozen)

```
mic / meeting audio
   │
whisper_streaming (LocalAgreement)      ← existing
   │ confirmed text
PRIVACY HOLD BUFFER (30–60 s)           ← new
   │   ├─ Presidio: obvious PII          ← existing
   │   ├─ cue detector: explicit, retroactive, scope end   ← new
   │   └─ LLM context check: implicit sensitive content    ← new (ConfAIde-informed prompt)
   ▼
state machine: ON / OFF / PENDING_CONFIRM   ← new
   │
committed notes → local LLM summary (Ollama)
```

**Core mechanics**
- **Hold buffer**: text confirmed by ASR waits N seconds before committing. Hook point is where LocalAgreement emits confirmed text in `whisper_online.py`.
- **Cue detector**: regex for obvious cues, then an LLM call for scope and retroactive targets, returning JSON span IDs.
- **State machine**: `ON` (record), `OFF` (suppress), `PENDING_CONFIRM` (implicit flag; agent asks "Keep that out of the notes?").
- **Retroactive removal**: matches by meaning across the hold buffer and committed notes. Committed matches are removed and logged.

## 1.7 Evaluation design (frozen)

**OTR-Bench**: about 40 snippets saved as `otr_bench.jsonl`.
- 20 from ConfAIde Tier 4 (implicit secrets, already labeled).
- 20 built on QMSum/AMI transcripts with inserted labeled spans of five types:
  1. explicit start and end
  2. explicit start, implicit end
  3. retroactive
  4. implicit (health, salary, HR)
  5. false alarms (e.g. "that movie *Off the Record*")
- Hand-check about 10 items.

**Systems**
- **A**: keyword rules + Presidio.
- **B**: one LLM pass ("remove anything off the record or private").
- **C** (ours): hold buffer + cue detector + state machine + LLM context check.

**Metrics**
- **Leak rate** (primary): private content that reaches the notes.
- **Over-redaction**: public content wrongly removed.
- Breakdown by case type.
- **Summary usefulness**: does the summary still contain the public items (ConfAIde-style)?

## 1.8 Risks (stated openly)

- The benchmark is small and partly synthetic. Report as early evidence.
- The hold buffer adds delay to live notes. Present it as the price of safety; vary buffer length if time allows.

## 1.9 Borrowed vs. new

| Borrowed | New |
|---|---|
| Streaming ASR and LocalAgreement (ufal/whisper_streaming) | Privacy hold stage after ASR confirmation |
| PII detection (Presidio) | ON / OFF / PENDING state machine with scope-end detection |
| Meeting-secret scenarios and leakage metric (ConfAIde) | Retroactive removal by meaning |
| Leak-judging approach (PrivacyLens) | OTR-Bench's explicit, retroactive and scope cases on top of ConfAIde |
| Real transcripts (QMSum / AMI) | |
| Contextual integrity framework (Nissenbaum) | |

**Reference repos**: ufal/whisper_streaming, ufal/SimulStreaming (fallback if too slow), QuentinFuxa/WhisperLiveKit (fast live demo), ConfAIde, SALT-NLP/PrivacyLens, microsoft/presidio, Yale-LILY/QMSum or AMI. Reference only: Meetily, Vexa, Attendee.

---

# PART 2: LIVING ADDENDA (append-only)

Rules: add new entries at the bottom of the relevant section. Each entry has an ID, a date, a status (`proposed` / `accepted` / `done` / `dropped` / `superseded by X`) and a one-line reason. Log every addition in [CHANGES.md](CHANGES.md).

## 2.1 Build plan and status (initial 3-hour plan)

| ID | Phase | Window | Deliverable | Status |
|---|---|---|---|---|
| P1 | Clone and run | 0:00–0:25 | Clone repos; Ollama with qwen2.5:7b (3b if slow); whisper_online.py transcribes a test file; locate LocalAgreement hook | proposed |
| P2 | Benchmark | 0:25–0:55 | 20 ConfAIde Tier 4 items + 20 QMSum chunks with LLM-inserted spans; hand-check ~10; save `otr_bench.jsonl` | proposed |
| P3 | Build system C | 0:55–1:45 | Hold buffer, cue detector, state machine, wired into emit point | proposed |
| P4 | Evaluate | 1:45–2:15 | Run A, B, C; leak rate, over-redaction, per-type table; one table + one bar chart | proposed |
| P5 | Live demo | 2:15–2:45 | Streamlit page: grey = held, green = committed, red = redacted; scripted demo | proposed |
| P6 | Slides | 2:45–3:00 | Problem, gap, method, results, demo, future work | proposed |

## 2.2 Team split (initial)

- **A**: whisper_streaming hook, hold buffer, demo page.
- **B**: benchmark construction and evaluation.
- **C**: cue detector, state machine, slides.

## 2.3 Demo script (initial)

1. An explicit off-the-record moment is suppressed.
2. "Strike that" removes held text.
3. A salary mention is flagged for confirmation.

## 2.4 Future work (candidate backlog)

| ID | Idea | Status |
|---|---|---|
| F1 | Join Zoom, Meet and Teams as a bot via Vexa or Attendee | proposed |
| F2 | Speaker-level opt-out (target-speaker unlearning in ASR) | proposed |
| F3 | Consent roll call as layer 1 | proposed |
| F4 | Pre-Alexa voice gate | proposed |
| F5 | Sweep hold-buffer length (delay vs. leak trade-off) | proposed |

## 2.5 Results log

_Empty. Add one dated entry per evaluation run: system, buffer length, model, benchmark version, leak rate, over-redaction, per-type numbers._

## 2.6 Open questions

| ID | Question | Status |
|---|---|---|
| Q1 | Is whisper_streaming fast enough on the target laptop, or do we switch to SimulStreaming? | open |
| Q2 | How do we label "implicit end" of a scope reliably in inserted spans? | open |
| Q3 | What is the right hold-buffer default (30 s vs. 60 s)? | open |
| Q4 | Which leak judge do we use (string match, LLM judge, or both)? | open |

## 2.7 Additions (new addenda go here)

_None yet. Template:_

```
### A-001 · YYYY-MM-DD · <title> · status
What: ...
Why: ...
Impact on foundation: none | requires decision (see CHANGES.md)
```
