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
- G5: A familiar video-call view with a visible notes state for each person. Each speaker can open a private drawer to review and remove their own policy-approved draft lines. Other participants see only that speaker's notes on/off state. The combined transcript becomes available for an explicit copy action after contributors finish their notes.
- G6: Local-only ASR, content classification, summaries and storage. No meeting content, transcript, identity or consent metadata is sent to hosted APIs.
- G7: Keep health, salary, HR, employee identifiers and associated sensitive numbers out of the shared or saved transcript, and measure misses using synthetic cases. This is a design goal to test, not a claim of perfect detection.
- G8: Let someone create an instant meeting, copy its link, and admit each guest from a waiting room. Guests enter an email and display name before requesting entry. The host sees both fields and chooses Admit or Deny. Email is an unverified label in this prototype; it is not proof of identity.

**Non-goals (foundation)**
- Joining Zoom, Meet or Teams as a bot.
- Scheduling meetings or sending invitations from the app.
- Voiceprints or identifying speakers from a mixed recording. Use authenticated LiveKit participant/track identity instead.
- Cloud processing of meeting content. Everything runs locally.
- Claiming a final or generalizable result. Results are early evidence.
- Preventing secondhand disclosure when another speaker repeats an opted-out person's information, for the first version.

## 1.6 Architecture (frozen)

```
participant browsers + visible per-person notes state
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
   │ approved text only, routed to the speaker's private draft
speaker review and removal → explicit finish → combined final transcript on request
```

**Core mechanics**
- **Source-level consent**: every participant starts OFF. The local recorder subscribes to that person's microphone track only after their own opt-in. Stop changes the consent epoch immediately, discards any in-flight frames and pending text, then unsubscribes; do not wait for network acknowledgement to suppress content. Unknown identity, disconnection or policy failure defaults OFF. Consent events log identity, state, time and purpose, never audio or text. A participant's control request must be authenticated as that participant; display names are not authority.
- **Meeting UI**: use a video-call grid and bottom controls. Each tile shows that person's notes on/off state; the speaker controls only their own state. A side drawer holds that speaker's approved draft and removal controls. Do not send another person's draft text, line IDs or private pause reason to a participant. After a speaker finishes, capture stays off. Serve the combined final only when contributors have finished and a participant explicitly requests it to copy.
- **Meeting entry**: the home page offers Create a meeting and Join a meeting. Creating produces a random room ID and a link. Guests request admission with email and display name; the host must admit each request before the guest receives a room media token. Room membership, requests, and email labels remain in local memory. A link alone does not grant admission.
- **Hold buffer**: opted-in ASR text waits in memory for the local policy check and a configurable release delay before reaching that speaker's private draft. Measure latency on the target laptop. The prior LocalAgreement hook remains a candidate implementation, but the source is now a participant track rather than mixed meeting audio. Audio stays in volatile memory; no raw-audio files by default.
- **Cue detector**: rules for obvious stop/delete cues, then a local model for scope and retroactive targets, returning source-entry IDs. A spoken Stop has detection latency; the button is authoritative.
- **Sensitive-content gate**: local Presidio and explicit HR patterns catch identifiers and numbers; a local small model checks contextual cases. Sensitive utterances are withheld as a whole unless a safe redacted span can be established. If uncertain, pause that speaker's capture and keep the text out of draft and final output. A model cannot guarantee that every sensitive disclosure is caught.
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
- **Cross-participant leak rate**: private draft text, line IDs, or sensitive pause reasons that reach another participant's display or network response; sensitive content that reaches the final transcript.
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
| P1 | Clone and run | 0:00–0:25 | Clone repos; Ollama with qwen2.5:7b (3b if slow); whisper_online.py transcribes a test file; locate LocalAgreement hook | proposed (2026-10-22 pass 2: still no evidence of whisper_streaming or an Ollama run; ingest uses faster-whisper chunking) |
| P2 | Benchmark | 0:25–0:55 | 20 ConfAIde Tier 4 items + 20 QMSum chunks with LLM-inserted spans; hand-check ~10; save `otr_bench.jsonl` | in-progress (pass 2: 47 synthetic items incl. `bench/_items_c.py`; no ConfAIde/QMSum imported; labels unreviewed; the set doubled as the dev set, see R-003) |
| P3 | Build system C | 0:55–1:45 | Hold buffer, cue detector, state machine, wired into emit point | in-progress (pass 2: built, 74 offline tests pass; C leak 1% on the dev set it was tuned on, held-out check not committed, see R-003) |
| P4 | Evaluate | 1:45–2:15 | Run A, B, C; leak rate, over-redaction, per-type table; one table + one bar chart | in-progress (pass 2: A/B-stub/C and a 5-point hold sweep run with no LLM; `results.png` is stale at 12:32; no LLM run) |
| P5 | Live demo | 2:15–2:45 | Streamlit page: grey = held, green = committed, red = redacted; scripted demo | in-progress (pass 2: web page, not Streamlit; rewritten UI uncommitted at 13:06; two LiveKit modes unreconciled; never viewed in a browser on record) |
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

_Add one dated entry per evaluation run: system, buffer length, model, benchmark version, leak rate, over-redaction, per-type numbers. Entries are appended below._

### R-001 · 2026-10-22 (files written 12:32) · first three-system run · synthetic, unreviewed, early
- Source: `bench/results.json` / `bench/results.md`. Benchmark: `bench/otr_bench.jsonl`, 40 synthetic items (8 per case type), none known hand-checked. LLM: none (`llm: none`). Hold seconds: harness default (not recorded in results.json meta). Systems: A = rules + PII; B-stub = heuristic stand-in, not an LLM; C = ours without LLM.
- Leak rate: A 14%, B-stub 21%, C 45%. Item-level leak: 22% / 31% / 72%. Over-redaction: 38% / 18% / 12%. Summary usefulness: 68% / 85% / 90%.
- Per-type leak (A / B-stub / C): explicit_start_end 0 / 0 / 28; explicit_start_implicit_end 0 / 0 / 50; retroactive 8 / 50 / 50; implicit 43 / 43 / 52; false_alarm n/a.
- Reading: C leaks more than A and B-stub; the hypothesis is not supported by this run. Do not use on slides.

### R-002 · 2026-10-22 (files written 12:32) · hold-length sweep · synthetic, unreviewed, early
- Source: `bench/results_sweep.json` / `bench/results_sweep.md`. Same 40 items, LLM none, system C only, hold 0 s vs 30 s.
- Result: identical in every cell (leak 45%, item leak 72%, over-redaction 12%, usefulness 90%). This is a suspected harness/pipeline artefact (WORK_SPLIT I2), not evidence that hold length does not matter. Bears on Q3 and F5.

### R-003 · 2026-10-22 (files written 13:00:52) · three-system run on 47 items · dev-set tuned, synthetic, no LLM, early
- **HELD-OUT CAVEAT: these are dev-set numbers.** The engine heuristics were developed while reading these same 47 items (`bench/README.md`). A separate 9-item check written afterwards (not committed, not auditable) reportedly gave C 53% leak vs A 53% before the gaps it found were fixed. Do not report the C figures below as the result. Use only as a regression check.
- Source: `bench/results.json` / `bench/results.md`, md5 of results.json 1546dc42b9937c496ee5f98589108b54, benchmark `bench/otr_bench.jsonl` md5 ebe64fba645191c37df914599b4ef0b0 (47 items). LLM: none. B-stub is a heuristic stand-in, not an LLM. Hold seconds: default (not recorded in meta). Command: `python -m bench.run_eval --systems A,B,C --llm none --out bench/results.json` (per `bench/README.md`; the exact invocation used is not recorded).
- Leak rate (final notes): A 21%, B-stub 27%, C 1%. Item-level leak: 30% / 38% / 3%. Over-redaction: 37% / 17% / 3%. Summary usefulness: 69% / 87% / 98%.
- Per-type leak (A / B-stub / C): explicit_start_end 13 / 13 / 0; explicit_start_implicit_end 13 / 13 / 0; retroactive 13 / 47 / 0; implicit 43 / 43 / 5; false_alarm n/a. Per-type over-redaction for C: false_alarm 6%, implicit 7%, others 0%.
- Supersedes R-001 for the same system (R-001 used the 40-item set and the pre-hardening engine; the files it cites were overwritten, so R-001 is now reproducible only from this document and `git log`).
- Reading: C below A and B-stub on the dev set. This does not test the hypothesis: no LLM, B is a stub, and the set was used for tuning.

### R-004 · 2026-10-22 (files written 13:00:53) · hold-length sweep 0/5/15/30/60 s · dev-set tuned, synthetic, no LLM, early
- Source: `bench/results_sweep.json` / `results_sweep.md`, md5 90eb955d95fc7fabcdedd44d4f705f5b; 47 items; system C only; LLM none. Supersedes R-002 (R-002 was flat; the harness has since been fixed per C-012).
- Final-notes leak: 1% at every hold. Over-redaction 3% and usefulness 98% at every hold.
- Committed-leak rate (private text ever committed, even if later retracted): 11% at 0 s, 10% at 5 s, 1% at 15 s, 1% at 30 s, 1% at 60 s. Retroactive type: 53% / 47% / 0 / 0 / 0.
- Reading: on this synthetic set, 15 s already catches the retractions; 30 vs 60 s is not distinguished. RESEARCH.md Q11 says the real retraction-delay distribution is unmeasured, so this does not settle Q3.

## 2.6 Open questions

| ID | Question | Status |
|---|---|---|
| Q1 | Is whisper_streaming fast enough on the target laptop, or do we switch to SimulStreaming? | open |
| Q2 | How do we label "implicit end" of a scope reliably in inserted spans? | open |
| Q3 | What is the right hold-buffer default (30 s vs. 60 s)? | open |
| Q4 | Which leak judge do we use (string match, LLM judge, or both)? | open (2026-10-22: bench/metrics.py scores by segment id, i.e. neither) |
| Q5 | Can local ASR plus policy checks approve live text within a few seconds on the target laptop? | open |
| Q6 | How do we authenticate participant identity without adding a cloud identity provider? | open |
| Q7 | Which HR categories and numeric values must be suppressed as entire utterances, versus safe span redaction? | open |
| Q8 | Can publisher-side LiveKit track permissions harden consent beyond recorder-side selective subscription without slowing the demo? | open |
| Q9 | Is the 40-item synthetic set, written by the team that built the systems, a fair test, and how much should the ConfAIde/QMSum import replace it? | open |
| Q10-Q18 | Research questions (B+ baseline design, retraction delay, cue recall under ASR error, privacy-signal ownership, implicit labelling, local model adequacy, local judge vs gold labels, consent boundary). Kept in `docs/RESEARCH.md` section 7.1, not copied here | open (2026-10-22 pass 2) |

## 2.7 Additions (new addenda go here)

### A-001 · 2026-10-22 · Early implementation differs from the initial plan · accepted
What: Observed deviations from 2.1: ingest is LiveKit plus faster-whisper chunking and a replay source (docs/INGEST.md), not whisper_streaming; the demo is a web page served by `demo/server.py`, not Streamlit; the benchmark is 40 synthetic items rather than 20 ConfAIde plus 20 QMSum; system B is a heuristic stub until an LLM run exists.
Why: Recorded so the PRD status matches the repo. Source: file listing and `bench/README.md` on 2026-10-22.
Impact on foundation: none (1.6 and 1.7 remain the target; the deviations are scope gaps to close)

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

### A-007 · 2026-10-22 · Wording corrections recommended by RESEARCH.md for PRD 1.1 and 1.4 · proposed
What: `docs/RESEARCH.md` section 1 recommends these corrections. Part 1 is frozen and is NOT edited here; any change to it needs an explicit decision logged in CHANGES.md. (a) ConfAIde 39% / 57% is the Tier 4 meeting-summary "Leaks Secret" rate (mean of 10 runs, privacy instruction already in the prompt); the action-item figures are 29% / 38%. (b) PrivacyLens 25.68% / 38.69% is the helpfulness-adjusted leak rate; the raw rates are 24.54% / 39.15%. (c) Survey figures in 1.1: 34.7% always asked, 36.5% sometimes, 25.1% never, 3.6% found out afterward; commissioned by a law firm; n=167 exposed respondents. This does not support "most people aren't asked". (d) Novelty wording: "no prior published evaluation" of spoken off-the-record cues, scope end or retroactive requests in streaming meeting transcription; do not claim no prior work (a Zoom patent claims keyword-triggered off-the-record requests). Also: newer-model prompting results (RESEARCH.md bottom line item 2) make a one-pass B a weak baseline, so a B+ is needed (Q10). Note: A-002 is already used by Lance's addendum, so this is A-007.
Why: the PRD figures came from a pasted plan (L-001); RESEARCH.md checked them against sources. The Docs Keeper has not re-checked the papers itself.
Impact on foundation: requires decision (see CHANGES.md) before 1.1 / 1.4 text changes

### A-008 · 2026-10-22 · Private live notes and a count-only final report · accepted

What: The meeting remains a normal video call: camera and microphone have their
own controls, separate from each participant's notes switch. The notes drawer
shows only that participant's approved lines after the local safety hold, plus
plain-language status for capture, filtering, and finalization. It must not
show raw ASR text while policy is still deciding. The final report gives counts
of suppressed and removed lines, without the withheld words or private reasons.
It becomes available only when all admitted participants finish their notes.
The combined transcript is fetched only when someone explicitly opens the
report or copies it. Report counts describe what the local policy actually
suppressed or removed; they do not claim to count speech that was never
captured because a participant left notes off.

Why: Participants need to understand what the local notetaker is doing without
turning the call into a monitoring dashboard or revealing the material they
chose to keep out. The UI must also make a delayed transcript distinguishable
from a failed audio or transcription connection.

Impact on foundation: clarifies G1, G5, and the hold-buffer behavior; logged in
C-018. Secondhand disclosure remains deferred.

### A-009 · 2026-10-22 · Optional final transcript email draft · accepted

What: Each participant may opt in to receiving the final transcript after
finishing their own notes. Their join email is only a suggested address, not
consent to email. Only the host can see the opted-in recipient list, and only
after every contributor has finished. When ending the meeting, the host may
review the approved combined transcript and open a preaddressed draft in their
own mail app. The app does not send mail. The host can end without drafting an
email. Long transcripts need a copy-and-paste fallback so a mail link cannot
silently cut off the text. Opening a draft may sync the final transcript through
the host's mail provider; the UI must say so before the host opens it. Live
drafts from other participants stay private.

Why: Email is a useful way to share the finished notes, but a join address
does not authorize delivery and a mail client is outside the local runtime.
An explicit choice by each recipient and a final review by the host keep the
export boundary visible.

Impact on foundation: adds an optional final export path to A-008; logged in
C-019.
