# Work Split: two people, working in parallel

## Branches and integration (2026-10-22)

The remote has three branches: `master` is the shared integration branch,
`feat/20261022-meeting-ui` is Lance's branch, and `p2-brain` is Deekshith's
branch. Each person keeps committing to their own branch. Worktrees can be used
for separate local tasks without creating more remote branches.

Lance's meeting UI is in [draft PR #3](https://github.com/Dee-1862/agent-filter/pull/3)
against `master`. Deekshith's `p2-brain` work is still on his branch. Before
either branch is merged, its owner should pull the latest `master`, resolve any
overlap with the other person's changes, run the relevant tests, and review the
resulting PR. Do not push one person's work directly to the other's branch or
force-push a shared branch. Merge into `master` only after the integration
check and review.

## Current decision (2026-10-22)

**Lance owns the live meeting path. Deekshith owns local NLP and policy.** The
original Person 1 / Person 2 task lists below are a scaffold, not authority to
use one meeting-wide privacy state. Consent is always **per participant**.

- **Lance / live side:** self-hosted LiveKit, join tokens and participant identity,
  individual Start/Stop controls, selective recorder subscription, local per-track
  ASR, visible recording states, approved per-speaker transcript, and live demo
  wiring. Owns `otr/ingest/`, `demo/`, LiveKit configuration, and their tests.
- **Deekshith / local NLP side:** spoken stop/delete cues, retrospective removal,
  HR/number and contextual sensitivity checks, hold and confirmation policy,
  per-speaker privacy state, local model evaluation, and benchmarks. Owns the
  pipeline and policy modules under `otr/` plus `bench/` and their tests.
- **Shared seam:** `Segment` carries the authenticated LiveKit participant identity.
  Capture consent is enforced before ASR and defaults OFF; the policy pipeline
  receives only segments from opted-in speakers. A stop invalidates that speaker's
  pending work. The pipeline must keep speaker-specific state and return only
  policy-approved text for the shared transcript. `otr/types.py` changes require
  agreement from both owners before either side edits it.
- **Privacy boundary:** raw audio, provisional ASR, held/redacted text, and raw audit
  events never go to the shared browser feed. A transcript row appears only after
  local policy approval. The browser may show a text-free processing indicator.

The code committed as `aa9835e` is an initial scaffold. Its `Pipeline` currently
has one global `StateMachine`, and its LiveKit source auto-subscribes to every
track. Neither behavior satisfies the current consent requirement; both are
implementation tasks, not a change to the product decision.

## Original implementation scaffold (superseded where it differs above)

Split along the seam in [otr/types.py](../otr/types.py): **Person 1 owns everything that produces `Segment`s and shows `Event`s. Person 2 owns everything between them and the proof that it works.** If neither side changes `otr/types.py`, you will not collide.

```
 PERSON 1: "Live side"                    PERSON 2: "Brain + proof"
 ─────────────────────                    ─────────────────────────
 LiveKit / replay ──Segment──▶  Pipeline  ──Event──▶ demo UI
 (otr/ingest/)                 (otr/*.py)           (demo/)
                                   ▲
                                   └── bench/ runs the same Pipeline offline
```

## Person 1: Live side (ingest, diarization, demo)

**Owns:** `otr/ingest/`, `demo/`, `docker-compose.livekit.yml`, `docs/INGEST.md`, `tests/test_ingest.py`, `tests/test_demo.py`.

| # | Task | Done when |
|---|---|---|
| 1 | Open the demo page in a real browser, fix layout, colours, countdown bar, Yes/No buttons, slider (never checked visually) | `python -m demo.server --script demo/scripts/demo_main.txt` looks right on a projector |
| 2 | Bring up LiveKit locally (`docker compose -f docker-compose.livekit.yml up -d`), mint tokens, join from two browser tabs | Two tabs and the bot in one room |
| 3 | Fix the LiveKit bot against the real SDK. `Room.connect`, `track_subscribed` and `TrackKind` were written from memory | Bot prints Segment JSONL with correct `speaker` per participant |
| 4 | Tune STT: faster-whisper model, energy threshold (untuned at 500), chunking | Spoken sentences come out readable with sane latency |
| 5 | Wire `--source livekit` in `demo/server.py` to `otr.ingest.livekit_source` (currently a stub). Remove the duplicate script parser in favour of `otr.ingest.replay_source` | Live speech shows up as grey, then green, in the page |
| 6 | Diarization for mixed audio: try pyannote (needs an HF token). `energy_turns()` is only a placeholder | A recorded 2-person clip gets SPEAKER_00 / SPEAKER_01 labels |
| 7 | Run the LLM call off the event loop in `demo/server.py` (a slow Ollama call would freeze the stream) | Stream stays live while the LLM is working |
| 8 | Stretch: Google Meet / Zoom via Vexa or Attendee bot | Only after 1–7 work. LiveKit cannot join Meet or Zoom itself |

**Demo fallback to keep working at all times:** `ReplaySource` with `demo/scripts/*.txt`. If LiveKit misbehaves on stage, the replay still shows the full story.

## Person 2: Brain + proof (engine, benchmark, eval, slides)

**Owns:** `otr/pipeline.py`, `otr/hold_buffer.py`, `otr/cue_detector.py`, `otr/state_machine.py`, `otr/pii.py`, `otr/llm.py`, `bench/`, `tests/test_pipeline.py`, `tests/test_bench.py`, the results log in `docs/PRD.md` 2.5, slides.

| # | Task | Done when |
|---|---|---|
| 1 | Install Ollama and pull `qwen2.5:3b` (or `7b`); check `OllamaLLM` works | `OllamaLLM().complete("hi")` returns text |
| 2 | Review the engine code and tests. Run `python -m pytest tests -q` | All green; read the cue lists and fix gaps |
| 3 | Run the three demo scripts through the real pipeline (`--pipeline real`) and fix mismatches with the demo's three beats | Explicit OTR, "strike that" on held text, salary → pending all behave |
| 4 | Make the pipeline read `hold_seconds` at tick time so the UI slider works on text already held | Slider change affects held segments |
| 5 | Hand-check about 10 benchmark items in `bench/otr_bench.jsonl`; fix wrong labels | Hand-checked items marked in `bench/README.md` |
| 6 | Run the eval for A, B and C: `python -m bench.run_eval --systems A,B,C --out bench/results.json`, with and without Ollama | Results table and bar chart |
| 7 | Improve C where it leaks (read the per-type breakdown). Sweep hold-seconds (30 vs 60) | Leak rate per type recorded |
| 8 | Log every run in `docs/PRD.md` 2.5; check the cited ConfAIde / PrivacyLens numbers (see L-001); build slides | Numbers on slides trace to a run or a source |
| 9 | Stretch: import real ConfAIde Tier 4 / QMSum with `bench/import_*.py` | Only if cloned |

## Handoffs and rules

1. **Contract:** `otr/types.py` is the only shared file. Change it only after both of you agree, and log it in `docs/CHANGES.md`.
2. **Handoff A (Person 2 → Person 1):** the real pipeline passes the three demo scripts. Until then Person 1 uses `demo/fake_pipeline.py`.
3. **Handoff B (Person 1 → Person 2):** transcripts from real LiveKit sessions (save the Segment JSONL). Person 2 replays them through the pipeline as extra test data.
4. **Integration checkpoint:** when both finish their tasks 3–5 (Person 1) and 3–4 (Person 2), do one run together: LiveKit speech → real pipeline → demo page.
5. **Git:** use the branches named in "Branches and integration" above. Each person touches only owned files. Merge to `master` after the checkpoint. Don't edit the other person's files; message them instead.
6. **Docs:** append to `docs/CHANGES.md` and `docs/LESSONS_LEARNED.md` as you go (append-only, never rewrite).
7. **Honesty:** the benchmark is small and synthetic, so call it early evidence. The live LiveKit path and the web page are untested until Person 1 finishes tasks 1–3.

## Needed from the machine

- **Both:** `pip install -r requirements-core.txt -r requirements-demo.txt`
- **Person 1:** Docker Desktop (installed), `requirements-ingest.txt`, optional HF token for pyannote
- **Person 2:** Ollama, plus `requirements-bench.txt` (matplotlib for the chart)

## Known issues from the first integration run (2026-10-22)

All 33 tests pass (`python -m pytest tests -q`, with `OTR_NO_PRESIDIO=1`). First eval run on the 40 synthetic items, no LLM:

| system | leak rate | item-level leak | over-redaction | summary usefulness |
|---|---|---|---|---|
| A (rules + PII) | 14% | 22% | 38% | 68% |
| B-stub (heuristic, not a real LLM) | 21% | 31% | 18% | 85% |
| C (ours) | 45% | 72% | 11% | 90% |

**C currently leaks more than A and B-stub, so the hypothesis is not supported yet.** That is expected for a first run with no LLM, but do not put these numbers on a slide as a result.

| # | Issue | Owner | Evidence | Status (Docs Keeper pass 2, 2026-10-22) |
|---|---|---|---|---|
| I1 | **Implicit-end heuristic ends OFF scope too early.** In `ese-01` the scope closed at the 2nd private line (`implicit_end:topic_change`) although the topic (the deal, a hiring freeze) had not changed; lines s05 and s06 then reached the notes. The no-LLM check in `otr/state_machine.py` `topic_changed` is the likely cause | Person 2 | `ese-01`; C leaks 28–52% by case type | fixed on dev set, with caveat (pass 2): C leak 45% -> 1% on 47 items (`bench/results.md` 13:00), but tuned on those items; a 9-item fresh check was 53% before further fixes (`bench/README.md`). Not validated held-out |
| I2 | Hold-seconds sweep gives identical numbers for 0 and 30. The harness only ticks at each segment's `t_start`, and the pipeline may not honour `hold_seconds` at tick time | Person 2 | `bench/results_sweep.json` | fixed on dev set (pass 2): sweep now varies committed-leak 11/10/1/1/1% at hold 0/5/15/30/60 (`bench/results_sweep.md`); final-notes leak flat by design (`bench/README.md`) |
| I3 | Salary keyword check flags public text ("salary calculator we launched") and flush then redacts it | Person 2 | `demo/scripts/demo_false_alarm.txt` | fixed on dev set (pass 2): `tests/test_pipeline.py` line 405 asserts the salary-calculator sentence is public; 74 tests pass. `demo_false_alarm.txt` not rerun through `--pipeline real` on record |
| I4 | `demo_retro_committed`: "Dana from finance told me in confidence..." was committed; confirm the script intends it as private | Person 2 | script run | open, no evidence (pass 2): no run of `demo_retro_committed.txt` through the real pipeline on record; script intent unconfirmed |
| I5 | `@pause N` is plain text for `otr.ingest.replay_source.parse_script`, but a directive for the demo's own parser. Make the ingest parser handle it | Person 1 | `otr/ingest/replay_source.py` | open (pass 2): `otr/ingest/replay_source.py` has no `@pause` handling (grep); `demo/server.py` handles it in `load_script_segments`; `tests/test_demo.py` collects again (74 pass) |
| I6 | Benchmark labels unchecked; cue lines ("strike that") are unscored; "strike that" used as an ordinary correction removes the previous line | Person 2 | `bench/README.md` | partly fixed on dev set (pass 2): cue/false-alarm handling and 7 ASR-style items added; labels still unreviewed, hand-check not done (`bench/README.md`) |

Fix I1 first: it dominates the leak rate. Re-run `python -m bench.run_eval --systems A,B,C --llm none --out bench/results.json` after each change and log the run in `docs/PRD.md` section 2.5.

### Next 5 actions (Docs Keeper pass 2, 2026-10-22)

**Person 1 (live side, Lance)**
1. Open the rewritten `demo/static/index.html` in a real browser; run `python -m demo.server --script demo/scripts/demo_main.txt`; commit the UI and `tests/test_demo.py` if it looks right.
2. Do a live LiveKit run (`docker compose -f docker-compose.livekit.yml up -d`, two tabs plus recorder); save the Segment JSONL as Handoff B.
3. Reconcile `--source livekit` (per-person consent, `demo/live_session.py`) with `--source livekit-stream` (shared `StreamRunner`) into one design.
4. Add `@pause N` to `otr.ingest.replay_source.parse_script` and drop the shim in `demo/server.py` (I5).
5. Get `p2-brain` merged to master (local master is still `aa9835e`) once the above is checked.

**Person 2 (brain + proof, Deekshith)**
1. Install Ollama, pull `qwen2.5:3b` or `7b`, confirm `OllamaLLM().complete("hi")`, then run C with the LLM check and a stronger B+ (RESEARCH.md Q10).
2. Build a larger held-out set: write and freeze it before any further tuning, commit it, report dev and held-out separately.
3. Compare causal B (no future text) with hindsight B at matched delay.
4. Hand-check about 10 labels in `bench/otr_bench.jsonl`, mark them in `bench/README.md` (I6).
5. Regenerate `bench/results.png` (still 12:32) and log each new run in PRD 2.5.
