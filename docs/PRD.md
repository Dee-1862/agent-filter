# PRD: Off-the-Record Meeting Agent (OTR Agent)

> **How this document works**
> - **Part 1 (Foundation)** is frozen. It holds the core idea, the research question and the architecture. Change it only by an explicit decision, and log that decision in [CHANGES.md](CHANGES.md).
> - **Part 2 (Living Addenda)** is append-only. New scope, refinements, results and open questions go there, each with a date and an ID. Never rewrite an addendum; supersede it with a new one.
> - Lessons go in [LESSONS_LEARNED.md](LESSONS_LEARNED.md). Every addendum change gets a line in [CHANGES.md](CHANGES.md).

---

# PART 1: FOUNDATION (frozen)

## 1.1 Problem

AI meeting notetakers capture everything and have no notion of how people signal privacy in conversation. Four signals matter:

1. **Participant choice**: each person opts in, stops, or declines without losing access to the meeting.
2. **Explicit speech**: "off the record", "don't write this down".
3. **After the fact**: "strike that", "forget what I said about the layoffs".
4. **Unspoken**: health, salary and HR content, including sensitive amounts and employee numbers, that is private from context alone.

Real-world harm is current: litigation over notetaker bots, voiceprint complaints, and surveys showing most people aren't asked before a notetaker joins. (Citations are listed in 1.9 and must be re-verified before being shown publicly.)

## 1.2 Research question

> Can a local meeting agent enforce each participant's consent at the audio-track boundary, respect explicit, retrospective and implicit privacy signals, and prevent sensitive content from reaching the shared transcript or notes? Does **structure** beat **prompting alone**?

## 1.3 Hypothesis

A per-participant consent state machine at capture, followed by a commit-delay hold buffer and local content policy, leaks less than a single LLM pass over mixed meeting audio. The gain should be largest on opt-out, after-the-fact and implicit cases.

## 1.4 Why it's a real gap

Prior work reports that prompting alone does not fix this. Figures below are as stated in the source plan and must be checked against the papers before use.

- **ConfAIde (ICLR 2024)**: GPT-4 and ChatGPT leak private information in contexts where humans wouldn't (reported 39% and 57%). Privacy-inducing prompts and chain-of-thought did not fully fix it. Its Tier 4 (meeting summarization and action items) is exactly this use case.
- **PrivacyLens (NeurIPS 2024)**: agents leak even with privacy-enhancing instructions (reported 25.68% for GPT-4, 38.69% for Llama-3-70B).

## 1.5 Goals and non-goals

**Goals**
- G0: Every participant starts unrecorded, can opt in or stop from the meeting UI, and remains in the call when declined. The recorder receives only opted-in tracks.
- G1: Live, local transcription feeding a privacy layer before anything reaches the notes.
- G2: Handle participant choice and the three speech/content signal types with measurable leak reduction versus baselines.
- G3: Remove already-committed content on retroactive request, by meaning, with an audit log.
- G4: A reproducible benchmark (OTR-Bench) and a three-system comparison.
- G5: A meeting UI that shows every participant's recording state and per-person transcript state. Live text appears only after a local policy check, grouped by speaker; no raw provisional text is shown to anyone. A declined participant is labeled **Not recorded / Not transcribed**, with no transcript row.
- G6: Local-only ASR, content classification, summaries and storage. No meeting content, transcript, identity or consent metadata is sent to hosted APIs.
- G7: Keep health, salary, HR, employee identifiers and associated sensitive numbers out of the shared or saved transcript, and measure misses using synthetic cases. This is a design goal to test, not a claim of perfect detection.

**Non-goals (foundation)**
- Joining Zoom, Meet or Teams as a bot.
- Voiceprints or identifying speakers from a mixed recording. Use authenticated LiveKit participant/track identity instead.
- Cloud processing of meeting content. Everything runs locally.
- Claiming a final or generalizable result. Results are early evidence.
- Preventing secondhand disclosure when another speaker repeats an opted-out person's information, for the first version.

## 1.6 Architecture (frozen)

```
participant browsers + visible consent and transcript UI
   │ separate microphone tracks
self-hosted local LiveKit room
   │
local recorder (autoSubscribe=false; subscribe only to consenting identities)
   │ opted-in audio only
local streaming ASR, one speaker identity per track
   │ confirmed text, in memory only
PROVISIONAL POLICY BUFFER (short UI delay; longer note commit delay)
   │   ├─ explicit / retrospective cue detector
   │   ├─ local Presidio + HR/number policies
   │   └─ local small-model context check for implicit sensitivity
   ▼
per-participant state: OFF / ON / PENDING_CONFIRM
   │ approved text only
shared delayed transcript → local notes / summary with source-entry IDs
```

**Core mechanics**
- **Source-level consent**: every participant starts OFF. The local recorder subscribes to that person's microphone track only after their own opt-in. Stop changes the consent epoch immediately, discards any in-flight frames and pending text, then unsubscribes; do not wait for network acknowledgement to suppress content. Unknown identity, disconnection or policy failure defaults OFF. Consent events log identity, state, time and purpose, never audio or text. A participant's control request must be authenticated as that participant; display names are not authority.
- **Meeting UI**: each participant sees who is being recorded and their own Start/Stop control. Transcript cards carry the same state. Everyone sees only policy-approved text, grouped by speaker; while an utterance is checked, show a processing indicator. Never show raw provisional HR or other sensitive text to any transcript viewer.
- **Hold buffer**: opted-in ASR text waits in memory for a fast local policy check before appearing in the live transcript, then a longer configurable delay before durable notes. Target a few seconds for approved live text and start with 30 seconds for note commit, but measure achievable latency on the target laptop. The prior LocalAgreement hook remains a candidate implementation, but the source is now a participant track rather than mixed meeting audio. Audio stays in volatile memory; no raw-audio files by default.
- **Cue detector**: rules for obvious stop/delete cues, then a local model for scope and retroactive targets, returning source-entry IDs. A spoken Stop has detection latency; the button is authoritative.
- **Sensitive-content gate**: local Presidio and explicit HR patterns catch identifiers and numbers; a local small model checks contextual cases. Sensitive utterances are withheld as a whole unless a safe redacted span can be established. If uncertain, show the speaker a private confirmation and keep the text out of shared/saved output.
- **State machine**: per person, `ON` (capture), `OFF` (no subscription), `PENDING_CONFIRM` (capture paused and subscription removed after a sensitive flag while the speaker decides). No model may auto-resume someone.
- **Retroactive removal**: delete matching held/committed source entries and invalidate or regenerate every derived summary that cited them. Audit only sanitized action metadata.
- **Locality**: run LiveKit, ASR, detectors, model, UI and notes on a controlled machine/LAN. No hosted Ketch SDK, model endpoint, analytics, CDN, external STUN service or remote error reporting in the first version. Remote participants would later require a self-hosted reachable server/TLS/TURN; today's LAN demo avoids that complexity. Audit outbound connections and run an offline LAN check after dependencies are installed.

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
- **Consent boundary**: recorder audio frames from an OFF participant (target: zero), Stop-to-last-frame time, and any transcript entry attributable to an OFF period (target: zero).
- **Shared-transcript leak rate**: private or HR content, including amounts and employee numbers, that reaches another participant's display or saved transcript.
- **Over-redaction**: public content wrongly removed.
- Breakdown by case type.
- **Summary usefulness**: does the summary still contain the public items (ConfAIde-style)?

## 1.8 Risks (stated openly)

- The benchmark is small and partly synthetic. Report as early evidence.
- The hold buffer adds delay to live notes. Present it as the price of safety; vary buffer length if time allows.
- A raw live transcript would disclose sensitive text before the detector runs. The visible transcript must be delayed until local policy approval; the exact latency remains to be measured.
- A later "strike that" can remove saved and displayed text, but it cannot make other participants forget content they already saw. The UI and demo must be honest about that limit.
- Automatic sensitivity detection can miss HR context or over-redact ordinary numbers. Do not promise zero leaks from the classifier; use fail-closed handling for uncertain spans and report measured results.
- Selective subscription enforces the app's policy, but a trusted server operator still controls the SFU. Cryptographic per-track authorization and publisher-side subscription restrictions are later hardening work.

## 1.9 Borrowed vs. new

| Borrowed | New |
|---|---|
| Self-hosted LiveKit participant tracks and selective subscription | Per-person consent controller and source-level capture gate |
| Streaming ASR and LocalAgreement (ufal/whisper_streaming), if viable per track | Privacy hold stage after ASR confirmation |
| PII detection (Presidio) | ON / OFF / PENDING state machine with scope-end detection |
| Meeting-secret scenarios and leakage metric (ConfAIde) | Per-speaker transcript UI and retroactive removal through derived notes |
| Leak-judging approach (PrivacyLens) | OTR-Bench's explicit, retroactive and scope cases on top of ConfAIde |
| Real transcripts (QMSum / AMI) | |
| Contextual integrity framework (Nissenbaum) | |

**Reference repos**: livekit/livekit, ufal/whisper_streaming, ufal/SimulStreaming (fallback if too slow), QuentinFuxa/WhisperLiveKit (fast live demo), ConfAIde, SALT-NLP/PrivacyLens, microsoft/presidio, Yale-LILY/QMSum or AMI. Reference only: Meetily, Vexa, Attendee. LiveKit's [self-hosting](https://docs.livekit.io/transport/self-hosting/) and [selective subscription](https://docs.livekit.io/intro/basics/rooms-participants-tracks/tracks/) docs support the new capture path.

---

# PART 2: LIVING ADDENDA (append-only)

Rules: add new entries at the bottom of the relevant section. Each entry has an ID, a date, a status (`proposed` / `accepted` / `done` / `dropped` / `superseded by X`) and a one-line reason. Log every addition in [CHANGES.md](CHANGES.md).

## 2.1 Build plan and status (initial 3-hour plan)

Historical plan; superseded for the LiveKit consent demo by A-005 below.

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

F2 and F3 are now core scope under A-001; the original rows remain as history.

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
| Q5 | Can local ASR plus policy checks approve live text within a few seconds on the target laptop? | open |
| Q6 | How do we authenticate participant identity without adding a cloud identity provider? | open |
| Q7 | Which HR categories and numeric values must be suppressed as entire utterances, versus safe span redaction? | open |
| Q8 | Can publisher-side LiveKit track permissions harden consent beyond recorder-side selective subscription without slowing the demo? | open |

## 2.7 Additions (new addenda go here)

Template:

```
### A-001 · YYYY-MM-DD · <title> · status
What: ...
Why: ...
Impact on foundation: none | requires decision (see CHANGES.md)
```

### A-001 · 2026-10-22 · Source-level participant consent · accepted

What: Use a self-hosted LiveKit room and one track per participant. The recorder starts with no subscriptions. Each participant controls their own Start/Stop state in the meeting UI, and declined speakers remain fully in the call. The consent controller is the single local source of truth for capture and downstream use. Audit only state changes and enforcement results, never audio or withheld text.

Why: Filtering a mixed audio transcript after capture cannot guarantee that a declining person's speech was not processed. LiveKit exposes participant tracks and selective subscriptions. Sources: [LiveKit track management](https://docs.livekit.io/intro/basics/rooms-participants-tracks/tracks/) and [self-hosting](https://docs.livekit.io/transport/self-hosting/).

Impact on foundation: explicit decision changes 1.1–1.3, 1.5–1.9; logged in C-003. F2 and F3 are superseded as future-work ideas by this accepted core scope. F1 (other meeting platforms) remains later work.

### A-002 · 2026-10-22 · Visible consent and live transcript · accepted

What: Put recording status beside every participant's name. The owner sees an always-visible Start/Stop button; all participants see **Recording**, **Not recorded / Not transcribed**, or **Paused for review** for each person. The transcript is grouped by participant and contains only policy-approved utterances. A speaker currently being checked shows a processing state, not raw words. Stopping immediately invalidates that speaker's consent epoch and clears pending content, then removes the recorder's subscription. A user who did not opt in has no transcript text, even temporarily in the shared view.

Why: The meeting must make consent legible to everyone and the real-time transcript cannot itself leak a sensitive utterance before the gate runs. Live text therefore has a short local policy delay; durable notes have a longer hold. The UI must show the measured delay rather than imply instantaneous protection.

Impact on foundation: explicit decision changes 1.5–1.8; logged in C-003.

### A-003 · 2026-10-22 · Local HR and numeric data policy · accepted

What: Process only opted-in audio locally. Before any text enters the displayed or saved transcript, run explicit cue rules, Presidio/custom recognizers for identifiers and structured numbers, and a local contextual classifier for HR, salary, benefits, performance, employee records, layoffs and health content. Default to withholding an entire uncertain utterance and showing the speaker **Paused for review**; do not auto-resume. A participant's click or verbal Stop overrides all classifier decisions. Store no raw audio by default and send no content to hosted models. [Presidio supports local recognizers](https://microsoft.github.io/presidio/analyzer/).

Why: The requested outcome is no sensitive HR data or associated numbers in transcripts. A classifier can miss implicit context, so the product must report measured leak and over-redaction rates and retain manual controls. Spoken sensitivity can be judged only after brief volatile processing; this is not a claim of zero capture before detection.

Impact on foundation: explicit decision changes 1.1, 1.5–1.8; logged in C-003.

### A-004 · 2026-10-22 · Ketch fit and zero-cloud boundary · accepted

What: Align the local design with Ketch's language of **identity**, **purpose**, **Permission Vault**, **enforcement**, **orchestration**, and **auditability**: a participant's consent governs track subscription, transcript display, note generation and deletion. This is a parallel local design, not a Ketch integration. Ketch's public documentation describes a server-side Permission Vault; its [web API example](https://github.com/ketch-sdk/ketch-web-api) uses `https://global.ketchcdn.com/web/v2`, and its [mobile SDK](https://github.com/ketch-com/ketch-ios) requires a Ketch organization account. No offline local Ketch deployment has been verified. The first version must not load Ketch's remote script or call its API because even consent metadata would leave the machine. Reassess an optional integration only if the owner changes the zero-cloud requirement or Ketch offers a verified offline path. Sources: [Ketch platform](https://www.ketch.com/platform/overview), [Ketch docs](https://docs.ketch.com/), [super{set} portfolio](https://superset.com/portfolio).

Why: Ketch is the clearest super{set} portfolio connection, but a hosted dependency conflicts with the product's core data boundary. A local permission ledger makes the concept concrete without misrepresenting affiliation or integration.

Impact on foundation: none beyond C-003's local architecture; logged in C-004.

### A-005 · 2026-10-22 · Fastest implementation path · accepted

What: Keep one local LiveKit server, one meeting web UI, and one local Python service for participant tokens, consent state, track subscription, ASR, policy checks and notes. Use the existing ASR plan only if it handles per-track streams with acceptable latency; otherwise choose a local in-memory ASR path. Do not build a Zoom/Meet bot, egress recording service, separate mobile app, remote auth, or Ketch integration for the hackathon. Supersede P1–P6's initial three-hour sequence with this order:

1. Self-hosted room with two identities and visible consent states.
2. Recorder starts unsubscribed; verify zero frames for an opted-out track and immediate unsubscribe on Stop.
3. Per-speaker local ASR and policy-approved live transcript with a visible processing state.
4. Explicit verbal Stop and retrospective delete, including invalidating sourced summaries.
5. HR/number policy using local rules and a local model; test synthetic examples for leaks and false positives.
6. Add the A/B/C benchmark and slides only after the core interaction works; no invented metrics.

Why: This is the shortest route to a demo that visibly proves Track 2's consent and privacy concepts. It avoids spending the hackathon on a mixed-audio benchmark while consent remains unimplemented. The [event](https://luma.com/superset-hy5n) lists a 5 PM Pacific project deadline on 2026-10-22.

Impact on foundation: none beyond C-003; logged in C-004. Initial P1–P6 remain as historical plan entries and are superseded by this addendum.

### A-006 · 2026-10-22 · Per-person consent is the integration contract · accepted

What: Lance owns LiveKit setup, selective capture, local per-track transcription,
and the meeting UI. Deekshith owns local NLP, privacy policy, and evaluation.
There is no meeting-wide recording or privacy switch. Each authenticated
participant begins OFF, controls only their own capture state, and can remain in
the room while unrecorded. The recorder must not subscribe to an OFF track.
The NLP pipeline must maintain independent privacy state per speaker; an explicit
or implicit cue for one speaker cannot toggle another speaker. Stopping one
speaker invalidates that speaker's pending ASR and policy work. Only approved
text may cross into the shared transcript; held, redacted, pending and audit
payloads are internal. The shared `Segment` / `Event` seam is defined in
`otr/types.py`, with any changes agreed by both owners. The current scaffold's
global `StateMachine` and automatic LiveKit subscription are known gaps, not
accepted design choices.

Why: Source-level consent and speaker-specific policy are the product's core
claim. A meeting-wide state would let one person's request affect another's
capture and would make the visible status misleading.

Impact on foundation: clarifies A-001–A-003 and the two-person work split;
logged in C-006. See [WORK_SPLIT.md](WORK_SPLIT.md).
