# Status dashboard

Regenerated each pass by the Docs Keeper (this file is NOT append-only). Every statement cites a command or file observed in that pass. Nothing here is claimed verified unless someone ran it.

**Pass 1 · 2026-10-22 · observed 12:42 local**

## Area status

Scale: not-started / in-progress / built-untested / tested-offline / verified-live.

| Area | Status | Evidence |
|---|---|---|
| Ingest (`otr/ingest/`) | built-untested (live paths) / tested-offline (replay) | `tests/test_ingest.py` passes in the 25-test run below; files mtime 12:29-12:30; LiveKit/STT/diarize never run against real services (no evidence in repo) |
| Engine (`otr/pipeline.py`, `state_machine.py`, `cue_detector.py`, `hold_buffer.py`, `pii.py`, `llm.py`) | tested-offline, in-progress | 25 tests pass (`OTR_NO_PRESIDIO=1 python -m pytest tests -q --ignore=tests/test_demo.py`, 12:42). `otr/cue_detector.py` still being edited (mtime 12:41:59; working-tree diff adds an ASR-noise repair step, uncommitted). `pipeline.py` mtime 12:32:00 and `state_machine.py` 12:30:28: no sign yet of an I1 fix |
| Runtime (`otr/runtime.py`) | built-untested | New untracked file, 361 lines, mtime 12:40:08. Docstring describes `StreamRunner` (worker thread for pipeline calls, bounded subscriber queues). No test file for it in `tests/` |
| Demo UI (`demo/server.py`, `demo/static/index.html`) | in-progress, tests broken | Both modified, mtime 12:40. `demo/server.py` no longer exports `parse_script` (now `load_script_segments`), so `tests/test_demo.py` fails at collection: `ImportError: cannot import name 'parse_script' from 'demo.server'` (seen at 12:41 and 12:42). Nobody has looked at the page in a browser |
| Bench (`bench/`) | tested-offline, early | 40 synthetic items (`wc -l bench/otr_bench.jsonl` = 40), `tests/test_bench.py` passes. Results generated 12:32:41 with `llm: none` (`bench/results.json` meta). ConfAIde/QMSum importers exist but have not been run (`bench/README.md`) |
| Research (`docs/research/`) | not-started (as observed) | Directory does not exist; draft_a.md and draft_b.md absent |
| Docs | in-progress | This pass created STATUS.md, appended C-003..C-006 and L-002..L-005, filled PRD 2.1/2.5/2.6/2.7 |

## Test run

- `OTR_NO_PRESIDIO=1 python -m pytest tests -q` (12:41 and again 12:42): **fails at collection**, 1 error in `tests/test_demo.py` (ImportError above), 0 tests run. Cause is a sibling agent mid-refactor of `demo/server.py`.
- `OTR_NO_PRESIDIO=1 python -m pytest tests -q --ignore=tests/test_demo.py`: **25 passed in 0.19s**.
- The previous documented total was 33 (WORK_SPLIT.md "Known issues"); test_demo.py therefore presumably holds about 8 tests, which did not run this pass.

## Latest eval

Files: `bench/results.json` (mtime 12:32:41, md5 aebe132af0f1bf59758876737a57dcaf), `bench/results.md`, `bench/results_sweep.json` (12:32:42, md5 cc2aa7b966cc72244410331016b88e9f), `bench/otr_bench.jsonl` (md5 9133c471c7c8cb7bee8069babd68e80c, 40 items). Settings: n_items 40, llm none, hold 0 s and 30 s in the sweep. **Synthetic, unreviewed, early.** Not valid for slides.

| system | leak | item-level leak | over-redaction | summary usefulness |
|---|---|---|---|---|
| A (rules + PII) | 14% | 22% | 38% | 68% |
| B-stub (heuristic, NOT an LLM) | 21% | 31% | 18% | 85% |
| C (ours, no LLM) | 45% | 72% | 12% | 90% |

Per-type leak (A / B-stub / C): explicit_start_end 0/0/28; explicit_start_implicit_end 0/0/50; retroactive 8/50/50; implicit 43/43/52; false_alarm n/a (no private segments).

The hypothesis (structure beats prompting) is **not supported** by this run. The results predate the 12:41 cue_detector edit and have not been regenerated since.

## Open issues I1-I6 (WORK_SPLIT.md)

| # | Status | Evidence |
|---|---|---|
| I1 implicit-end heuristic closes scope early | open | `state_machine.py` untouched since 12:30:28; C figures in results.json equal those quoted in WORK_SPLIT (45%; per type 28/50/50/52) |
| I2 hold sweep identical for 0 and 30 | open | `bench/results_sweep.json` (12:32:42): C@0s and C@30s equal in every cell |
| I3 salary keyword flags public text | unknown | no rerun of `demo_false_alarm.txt` observed |
| I4 `demo_retro_committed` ambiguity | unknown | no evidence either way |
| I5 `@pause` parser mismatch | partially mitigated, still open | `demo/server.py` now builds segments through `otr.ingest.replay_source.parse_script` and pre-splits `@pause` itself (`load_script_segments`), so the duplicate parser is gone. `parse_script` itself still does not understand `@pause` (grep of `otr/ingest/replay_source.py`), which is what the issue asked for. The refactor also broke the `tests/test_demo.py` import |
| I6 labels unchecked, cue lines unscored | open | `bench/README.md`: about 10 hand-checked "if any", rest unreviewed |

## Nobody has verified

- Live LiveKit: bot, token minting, real SDK calls, per-participant speaker labels (no recorded run).
- The demo page in a real browser (layout, countdown bar, Yes/No buttons, slider).
- Any Ollama/LLM path: all evals ran with `llm: none`; B is a heuristic stub; `OllamaLLM` never exercised in a recorded run.
- Hand-checked benchmark labels (none marked checked).
- The Presidio path (tests ran with `OTR_NO_PRESIDIO=1`).
- `otr/runtime.py` (no tests).
- Cited literature figures (L-001 still open).

## Next 5 actions

**Person 1 (live side)**
1. Make `tests/test_demo.py` match the refactored `demo/server.py` (or restore the export) so the full suite collects again.
2. Open the demo page in a browser with `python -m demo.server --script demo/scripts/demo_main.txt`; fix layout and controls.
3. Bring up LiveKit (`docker compose -f docker-compose.livekit.yml up -d`), join from two tabs plus the bot, save Segment JSONL.
4. Fix the LiveKit bot against the real SDK; wire `--source livekit` through `otr.runtime.StreamRunner`; add tests for the runtime.
5. Teach `otr.ingest.replay_source.parse_script` the `@pause N` directive (I5) and drop the shim in `demo/server.py`.

**Person 2 (brain + proof)**
1. Fix I1 (`state_machine.topic_changed`), then rerun `python -m bench.run_eval --systems A,B,C --llm none --out bench/results.json`.
2. Rerun the hold sweep after making the pipeline read `hold_seconds` at tick time (I2).
3. Install Ollama, pull `qwen2.5:3b`, confirm `OllamaLLM().complete("hi")`, rerun the eval with a real LLM for B and C.
4. Hand-check about 10 items in `bench/otr_bench.jsonl` and mark them in `bench/README.md` (I6).
5. Run the three demo scripts with `--pipeline real` (I3, I4); verify the ConfAIde/PrivacyLens figures (L-001) before any slide.
