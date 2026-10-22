# Status dashboard

Regenerated each pass by the Docs Keeper (this file is NOT append-only). Every statement cites a command or file observed in that pass. Nothing here is claimed verified unless someone ran it.

**Pass 2 · 2026-10-22 · observed about 13:08 local** (pass 1 was at 12:42)

## Git

`git log --graph --all`: HEAD is branch `p2-brain` at `366f7b8` (13:02), which is also `origin/p2-brain`. `origin/master` is `1850cfa` (Lance's PR #1 merged). Local `master` is still `aa9835e`, 3 behind. `p2-brain` is not merged into master. `git status --short` at observation: modified `demo/static/index.html`, `tests/test_demo.py` (uncommitted), plus the docs edited in this pass.

## Area status

Scale: not-started / in-progress / built-untested / tested-offline / verified-live.

| Area | Status | Evidence |
|---|---|---|
| Ingest (`otr/ingest/`) | tested-offline (replay, token/consent logic); live paths built-untested | `tests/test_ingest.py` (9 test functions) passes; `livekit_source.py` and `stt.py` changed 12:46 (Lance); no record of a real LiveKit or STT run |
| Engine (`otr/pipeline.py`, `state_machine.py`, `cue_detector.py`, `hold_buffer.py`, `llm.py`) | tested-offline | 74 passed in the full run. `pipeline.py` / `state_machine.py` 12:55, `cue_detector.py` / `llm.py` 13:00. Heuristic only: LLM path never run against Ollama |
| Runtime (`otr/runtime.py`) | tested-offline | `tests/test_runtime.py` (8 test functions) now exists and passes. Not run live |
| Live consent (`demo/live_session.py`, `demo/static/live.*`) | tested-offline | Lance's per-person consent path; `tests/test_demo.py` has a consent test (`test_live_consent_is_bound_to_server_issued_identity`). Not run against a real LiveKit server on record |
| Demo UI (`demo/static/index.html`, `demo/server.py`) | built-untested, uncommitted | `index.html` 46.5 KB, mtime 13:06, has "Level 1: insights" and "Level 2: explain" sections (the coordinator calls it a 3-level view); nobody on record opened it in a browser. `--source` is now replay / livekit / livekit-stream (two unreconciled live modes) |
| Bench (`bench/`) | tested-offline, dev set | 47 synthetic items (`wc -l bench/otr_bench.jsonl`), `_items_c.py` adds 7 ASR-style items; `tests/test_bench.py` passes. Results 13:00:52, `llm: none`. `bench/results.png` is stale (12:32). Importers not run. Dev-set caveat below |
| Research | built (drafts, critiques, merged) | `docs/RESEARCH.md` 13:02; `docs/research/draft_a.md`, `draft_b.md`, `critique_of_a.md`, `critique_of_b.md` 12:56-12:58 |
| Docs | in-progress | This pass: C-012..C-017, L-009..L-014, PRD R-003, R-004, A-007, Q10-Q18 pointer, WORK_SPLIT statuses. Not yet reflected in PRD Part 1 (frozen) |

## Test run

`OTR_NO_PRESIDIO=1 python -m pytest tests -q` (about 13:07): **74 passed, 1 warning** in 6.08 s (warning: PyJWT `InsecureKeyLengthWarning`, 6-byte HMAC key in a test). Pass 1 was a collection error and 25 passed without `test_demo.py`. Not tested: the Presidio path (env var disables it).

## Latest eval (dev-set tuned, synthetic, no LLM, early)

**HELD-OUT CAVEAT.** The engine heuristics were written while reading these same 47 items (`bench/README.md`). A separate 9-item check written afterwards (not committed) reportedly gave C 53% leak, equal to A, before further fixes. The C numbers below are a regression check on the dev set, not evidence for the hypothesis.

Files: `bench/results.json` (13:00:52, md5 1546dc42b9937c496ee5f98589108b54), `bench/results.md`, `bench/results_sweep.json` (13:00:53, md5 90eb955d95fc7fabcdedd44d4f705f5b), `bench/otr_bench.jsonl` (12:58, md5 ebe64fba645191c37df914599b4ef0b0, 47 items). Meta: n_items 47, llm none.

| system | leak | item-level leak | over-redaction | summary usefulness |
|---|---|---|---|---|
| A (rules + PII) | 21% | 30% | 37% | 69% |
| B-stub (heuristic, NOT an LLM) | 27% | 38% | 17% | 87% |
| C (ours, no LLM) | 1% | 3% | 3% | 98% |

Hold sweep for C (committed-leak, final-notes leak is 1% at all): 0 s 11%, 5 s 10%, 15 s 1%, 30 s 1%, 60 s 1%. Logged in PRD 2.5 as R-003 and R-004.

## Open issues I1-I6 (WORK_SPLIT.md)

| # | Status | Evidence |
|---|---|---|
| I1 implicit-end closes scope early | fixed on dev set, with caveat | C leak 45% -> 1% (`bench/results.md`); tuned on the same items |
| I2 hold sweep identical | fixed on dev set | committed-leak varies with hold (`bench/results_sweep.md`); final-notes leak flat by design (`bench/README.md`) |
| I3 salary keyword flags public text | fixed on dev set | `tests/test_pipeline.py` line 405; `demo_false_alarm.txt` not rerun through `--pipeline real` on record |
| I4 `demo_retro_committed` ambiguity | open, no evidence | no run of the script through the real pipeline on record |
| I5 `@pause` parser mismatch | open | no `@pause` in `otr/ingest/replay_source.py`; the shim lives in `demo/server.py`; test import now collects |
| I6 labels unchecked | partly fixed on dev set | ASR-style items added; labels unreviewed (`bench/README.md`) |

## Inconsistencies seen

- PRD 2.7 has two entries titled A-001 (Docs Keeper's and Lance's); new addenda continue from A-007 (A-002 is taken).
- `bench/results.png` (12:32) does not match the current results.
- WORK_SPLIT.md still opens with the Person 1 / Person 2 split, and now also names Lance and Deekshith; the owner mapping in the table headings is the old one.
- Part 1 of the PRD still carries the unchecked wording that RESEARCH.md corrects (A-007 proposes a decision).
- Local `master` lags `origin/master` by 3 commits.

## Nobody has verified

- Live LiveKit end to end (either mode), real STT latency, diarization.
- The rewritten demo page in a browser.
- Any Ollama / LLM path (C with LLM, a real B, a stronger B+).
- Held-out performance: no committed held-out set exists.
- Hand-checked benchmark labels.
- The Presidio path.
- Each cited literature figure beyond what RESEARCH.md reports (the Docs Keeper has not read the papers).

## Next 5 actions

**Person 1 (live side)**
1. Open the rewritten `demo/static/index.html` in a browser (`python -m demo.server --script demo/scripts/demo_main.txt`); commit the UI and `tests/test_demo.py` if good.
2. Run a real LiveKit session (`docker compose -f docker-compose.livekit.yml up -d`); save Segment JSONL.
3. Reconcile `--source livekit` (per-person consent) with `--source livekit-stream` (shared StreamRunner).
4. Add `@pause N` to `parse_script` and drop the `demo/server.py` shim (I5).
5. Get `p2-brain` merged to master after checks.

**Person 2 (brain + proof)**
1. Install Ollama; run C with the LLM and a stronger B+ (RESEARCH.md Q10).
2. Write and freeze a bigger held-out set before any more tuning; report dev and held-out separately.
3. Compare causal B with hindsight B at matched delay.
4. Hand-check about 10 labels; mark them in `bench/README.md`.
5. Regenerate `bench/results.png`; log each run in PRD 2.5.
