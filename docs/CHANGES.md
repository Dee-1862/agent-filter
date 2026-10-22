# Changes

Append-only log of every change to the plan, scope, architecture, benchmark or results. Newest entries at the top. Each entry says what changed, why, and which part of [PRD.md](PRD.md) it touches.

**Entry format**

```
## YYYY-MM-DD · C-### · <short title>
- Type: foundation | addendum | benchmark | system | eval | demo | process
- Touches: PRD section(s)
- What changed:
- Why:
- Decided by:
```

A `foundation` change is rare and needs a stated reason. Everything else is an `addendum`-type change.

---

## 2026-10-22 · C-018 · Video meeting UI and private final report
- Type: addendum
- Touches: PRD 2.7 (A-008)
- What changed: Added the instant meeting and host admission flow, independent camera and notes controls, private approved live notes, a count-only redaction report, and a local HTTPS path for people on the same network.
- Why: Lance wants a familiar video call with consent and filtering visible on demand, while meeting data stays on the local host.
- Decided by: Lance in the 2026-10-22 conversation

## 2026-10-22 · C-017 · Docs Keeper pass 2 (STATUS regenerated, PRD 2.1/2.5/2.6/2.7, WORK_SPLIT statuses)
- Type: process
- Touches: PRD 2.1, 2.5 (R-003, R-004), 2.6, 2.7 (A-007); WORK_SPLIT Known issues
- What changed: Regenerated `docs/STATUS.md`; updated `docs/.docs-keeper-state.json`; corrected stale cross-references in L-005..L-008 (they pointed at pre-merge C-numbers; see L-014). Recorded wording corrections from `docs/RESEARCH.md` as A-007 without touching PRD Part 1. Note: the PRD now has two entries titled A-001 (the Docs Keeper's, then Lance's); both are kept and new addenda continue from A-007.
- Why: keep docs tied to observed state after the merge.
- Decided by: project owner (Docs Keeper role)

## 2026-10-22 · C-016 · Branch and merge history
- Type: process
- Touches: WORK_SPLIT rule 5
- What changed: `git log --graph --all` shows: `aa9835e` basic foundation; Lance's branch `feat/20261022-livekit-consent` (`453c01b`, `be06d18`) merged into origin/master as PR #1 (`1850cfa`); `p2-brain` carried two WIP commits (`e4430aa`, `5fad7a5`), merged the consent branch (`41a24ad`) and origin/master (`544873f`), then `366f7b8` "Engine hardening: conservative scope end, live hold, ASR-noise cues; 47-item bench; research round 2" (13:02). Local `master` is still at `aa9835e`, 3 behind origin/master; `p2-brain` is not merged to master. Uncommitted at 13:06: `demo/static/index.html`, `tests/test_demo.py`.
- Why: record where the code lives, since the docs refer to both people's work.
- Decided by: observed via `git log --graph --all`, `git branch -a -vv`, `git status --short`

## 2026-10-22 · C-015 · RESEARCH.md merged from two researchers
- Type: process
- Touches: PRD 1.1, 1.4 (wording corrections only, see A-007), 2.6
- What changed: `docs/RESEARCH.md` (13:02) merges `docs/research/draft_a.md` (12:58) and `draft_b.md` (12:56) after cross-critiques (`critique_of_a.md`, `critique_of_b.md`). It has a verified-facts table, ranked design changes, a dispute log and open questions Q10-Q18. Owned by the researchers; the Docs Keeper only reads it.
- Why: replace the unchecked literature figures noted in L-001.
- Decided by: researchers and judge pass (see RESEARCH.md section 9)

## 2026-10-22 · C-014 · Demo UI rewritten (uncommitted)
- Type: demo
- Touches: PRD 2.1 P5
- What changed: `demo/static/index.html` is now 46.5 KB (was 17.7 KB), mtime 13:06. The file labels "Level 1: insights" and "Level 2: explain" sections; the coordinator describes it as a 3-level meeting view. `tests/test_demo.py` was modified alongside (17 test functions). Both are in the working tree, not in `366f7b8`. No record of anyone opening it in a browser.
- Why: make held / committed / redacted states and the reasons visible (G5).
- Decided by: runtime/demo agent

## 2026-10-22 · C-013 · demo/live_session.py split: two LiveKit modes
- Type: system
- Touches: PRD A-001..A-006 (Lance's), WORK_SPLIT
- What changed: `demo/live_session.py` (16 KB, 12:48) added. `demo/server.py` `--source` now takes `replay`, `livekit` or `livekit-stream` (line 234). `livekit` is Lance's per-person consent session; `livekit-stream` is the shared `otr.runtime.StreamRunner` path with reconnect. Both coexist and are not reconciled into one design; neither has been run against a real LiveKit server on record. `demo/static/live.html/js/css` and a vendored `livekit-client.umd.js` back the consent page.
- Why: Lance's consent contract (C-006, C-007) conflicts with the earlier single global pipeline state.
- Decided by: Lance (consent mode), runtime agent (stream mode)

## 2026-10-22 · C-012 · Engine hardening, 47-item bench, regenerated results
- Type: system
- Touches: PRD 1.6, 1.7, 2.1 P2-P4, 2.5
- What changed: Commit `366f7b8`. Engine files: `otr/state_machine.py` (8.1 KB, 12:55), `otr/pipeline.py` (18.9 KB, 12:55), `otr/cue_detector.py` (16 KB, 13:00, ASR-noise repair), `otr/llm.py` (13:00), `otr/hold_buffer.py` (12:51). The bench grew from 40 to 47 items with `bench/_items_c.py` (7 live-ASR-style items); `bench/build_bench.py`, `run_eval.py` (hold sweep 0,5,15,30,60 plus a committed-leak metric), `metrics.py`, `systems.py` updated; `bench/results*.json/md` regenerated 13:00. Evidence per issue: I1 (scope end) - C leak fell from 45% to 1% in `bench/results.md`; I2 (hold) - the sweep now varies the committed-leak rate (11%, 10%, 1%, 1%, 1% at hold 0/5/15/30/60) where the old sweep was flat; I3 - `tests/test_pipeline.py` line 405 asserts "The salary calculator we launched..." is public, and `otr/llm.py` line 92 comments on it; I6 - cue lines and false alarms are handled and 7 ASR-style items were added, but labels are still unreviewed. All on the dev set (see L-009). Tests: 74 passed (`OTR_NO_PRESIDIO=1 python -m pytest tests -q`, 6.08 s).
- Why: the first eval showed C worse than A (L-005).
- Decided by: engine agent

## 2026-10-22 · C-011 · Docs Keeper pass 1: STATUS dashboard and state file
- Type: process
- Touches: PRD 2.1 (statuses), 2.5 (results), 2.6 (Q5), 2.7 (A-001)
- What changed: Added `docs/STATUS.md` (regenerated each pass) and `docs/.docs-keeper-state.json` (observed mtimes, test count, results hash for diffing). Filled PRD 2.1 statuses, logged the visible eval runs in 2.5, added Q5 and A-001. Updated the Known issues table in `docs/WORK_SPLIT.md` with a status column.
- Why: Keep docs tied to observed repo state, not to claims.
- Decided by: project owner (Docs Keeper role)

## 2026-10-22 · C-010 · Cue detector gains ASR-noise repair (uncommitted)
- Type: system
- Touches: PRD 1.6 (cue detector), 2.1 P3
- What changed: `otr/cue_detector.py` working-tree diff (+118 lines, mtime 12:41:59) adds `repair_asr` / `_tok_match` / `_detect_strict`, rewriting near-matches of cue phrases to canonical text before the strict regexes run. `detect()` now wraps this.
- Why (as stated in the file comment): live STT garbles short cue phrases. Not yet evaluated: `bench/results.json` (12:32) predates it.
- Decided by: engine agent

## 2026-10-22 · C-009 · Benchmark and three-system eval generated
- Type: benchmark
- Touches: PRD 1.7, 2.1 P2/P4, 2.5
- What changed: `bench/` now holds 40 synthetic items (`bench/otr_bench.jsonl`, built from `bench/_items_a.py` and `_items_b.py` by `bench/build_bench.py`), systems A / B-stub / C (`bench/systems.py`), metrics, `run_eval.py`, plot, importers for ConfAIde and QMSum (not run), and outputs `bench/results.json`, `results.md`, `results.png`, `results_sweep.json`, `results_sweep.md` (all mtime 12:32). Tests in `tests/test_bench.py`.
- Why: PRD G4. Note the set is synthetic, not the ConfAIde/QMSum mix the PRD called for; B is a heuristic stub, not an LLM.
- Decided by: engine / bench agent

## 2026-10-22 · C-008 · Runtime module and demo server refactor (uncommitted)
- Type: demo
- Touches: PRD 1.5 G5, 2.1 P5; WORK_SPLIT Person 1 tasks 5 and 7
- What changed: New untracked `otr/runtime.py` (`StreamRunner`: runs all pipeline calls on one worker thread, queues segments, bounded subscriber queues with history). `demo/server.py` rewritten (-287/+ lines in the working tree): `load_script_segments` replaces the demo's own parser and uses `otr.ingest.replay_source.parse_script`; `demo/static/index.html` extended. Side effect: `demo.server.parse_script` is gone and `tests/test_demo.py` no longer collects.
- Why: keep slow LLM calls off the event loop; remove the duplicate script parser (I5, task 7).
- Decided by: runtime/demo agent
## 2026-10-22 · C-007 · Implement local LiveKit consent demo
- Type: system
- Touches: PRD A-001–A-006, INGEST.md, LOCAL_PRIVACY.md
- What changed: Added a local meeting page, server-issued participant identities, per-person Start/Stop and status, selective LiveKit recorder subscription, local utterance-level ASR, and a shared transcript containing only approved lines. Sensitive flags pause only the affected speaker and discard the pending utterance.
- Why: Make the per-person capture boundary visible and testable without sending meeting data to hosted services.
- Decided by: project owner request on 2026-10-22

## 2026-10-22 · C-006 · Make per-person consent the shared contract
- Type: addendum
- Touches: PRD A-006, WORK_SPLIT.md
- What changed: Assigned Lance the live LiveKit/UI path and Deekshith the local NLP/policy path; stated that capture and privacy state are per authenticated participant, and identified the existing global state and automatic subscription as scaffold gaps.
- Why: The owner confirmed per-person consent is the correct architecture and asked for the remote docs and implementation to follow it.
- Decided by: project owner in the 2026-10-22 conversation

## 2026-10-22 · C-005 · Prepare local repository assets
- Type: process
- Touches: LOCAL_SETUP.md, .gitignore
- What changed: Documented the cloned repository, locally installed LiveKit and whisper.cpp versions, the checksum-verified local Whisper model, and the next implementation slice. Ignored model weights, media, databases, environments and generated dependencies.
- Why: Keep the zero-cloud prototype reproducible and reduce accidental inclusion of sensitive artifacts in Git.
- Decided by: project owner request to set up the new repository locally

## 2026-10-22 · C-004 · Add local demo, UI and Ketch decisions
- Type: addendum
- Touches: PRD Part 2 (2.1–2.7, A-001–A-005)
- What changed: Added accepted addenda for per-person UI, transcript visibility, sensitive HR/number policy, Ketch alignment without hosted integration, and a build order that supersedes the initial P1–P6 timebox. Added open questions Q5–Q8.
- Why: The hackathon demo should prove consent at the source and show only approved per-speaker text, while keeping all data and inference local.
- Decided by: project owner in the 2026-10-22 conversation

## 2026-10-22 · C-003 · Move consent to LiveKit participant tracks
- Type: foundation
- Touches: PRD Part 1 (1.1–1.3, 1.5–1.9)
- What changed: Replaced mixed meeting-audio capture with a self-hosted LiveKit room and per-participant opt-in track subscription. Made visible consent, local per-speaker transcription, HR/number gating and deletion propagation core goals; kept voiceprints, cloud processing, other meeting-platform bots and secondhand disclosure out of first scope.
- Why: The owner explicitly chose LiveKit and per-person consent. A post-capture filter over mixed audio cannot enforce that a declining participant was not processed.
- Decided by: project owner in the 2026-10-22 conversation

## 2026-10-22 · C-002 · Added two-person work split
- Type: process
- Touches: PRD 2.2 (team split, now two people instead of three)
- What changed: Added `docs/WORK_SPLIT.md` dividing the work into Person 1 (live side: ingest, LiveKit, diarization, demo) and Person 2 (brain + proof: pipeline, benchmark, eval, slides). Scaffolding for all modules was generated by parallel agents against `otr/types.py`.
- Why: Two people will work simultaneously; the contract file is the seam.
- Decided by: project owner


## 2026-10-22 · C-001 · Initial PRD created
- Type: foundation
- Touches: PRD Part 1 (all), Part 2 (2.1–2.7)
- What changed: Created `docs/` with PRD.md, CHANGES.md and LESSONS_LEARNED.md. Part 1 captures the research question, hypothesis, architecture, evaluation design and risks from the source plan. Part 2 seeds the build plan, team split, demo script, future-work backlog and open questions.
- Why: Fix the foundation so later work adds to it instead of drifting from it.
- Decided by: project owner
- Note: Literature figures (ConfAIde, PrivacyLens) were carried over from the source plan and have not been independently re-verified.
