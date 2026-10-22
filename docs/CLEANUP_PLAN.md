# Cleanup plan (2026-10-22)

Goal: the repository keeps only what supports the project. Each item below was grepped across code, tests, scripts and docs before a decision. Anything that code, tests or scripts import or read stays where it is. Archived files move to [archive/](archive/README.md) with a note saying why. Nothing in `otr/` or `demo/` changes behaviour.

Decisions: **keep**, **merge** (fold into another file), **archive** (move under `docs/archive/`), **delete** (junk only).

## Top level

| Item | Decision | Reason |
|---|---|---|
| `.gitignore` | keep | Protects sealed bench splits, audio, models and service config from commits |
| `LICENSE` | keep | MIT license |
| `README.md` | keep | Entry point; gets the simpler diagram and a link to RESULTS.md |
| `bench/` | keep | Benchmark data, manifests, systems, metrics and every result file; results files are read by docs and by `scripts/make_charts.py` |
| `demo/` | keep | Web server and pages served by `otr.app`; all files are served or tested |
| `docker-compose.livekit.yml` | keep | Started by `otr.app` for the local call server |
| `docs/` | keep | Restructured as listed below |
| `experiments/` | keep | Browser and audio injection tools that drive the real call path; `livekit_sim.py` is imported by tests |
| `otr/` | keep | The engine |
| `requirements-*.txt` (5 files) | keep | Install sets named in README, SETUP.md and `scripts/check_env.py` |
| `scripts/` | keep | Environment check, audits, redaction check, demo audio, model check, remote watcher; new `make_charts.py` |
| `tests/` | keep | Offline test suite |
| `vercel-demo/` | keep | Builds the hosted demo page described in LOCAL_PRIVACY.md |
| `demo_audio/`, `models/`, `.otr-service.json` | keep (local, ignored) | Generated audio, model weights and service config; never committed |
| `.claude/`, `.gyst/`, `.pytest_cache/`, `__pycache__/` | keep (local, ignored) | Tool state on this machine; not tracked, so nothing to remove from the repository |

## docs/

| File | Decision | Reason |
|---|---|---|
| `ARCHITECTURE.md` | keep | Diagrams; section 0 gets the simpler five-box flowchart |
| `CHANGES.md` | keep | Append-only log; one new entry for this cleanup |
| `COMPETITORS.md` | keep | Source for the capability grid |
| `DEMO_SCRIPT.md` | keep | Stage script and checks |
| `HOW_IT_WORKS.md` | keep | Plain-language guide; uses the same diagram as README |
| `INGEST.md` | keep | Lance's ingest guide, still current |
| `LESSONS_LEARNED.md` | keep | Append-only log |
| `LOCAL_PRIVACY.md` | keep | Lance's data boundary doc |
| `LOCAL_SETUP.md` | keep | Lance's Mac setup; link to WORK_SPLIT.md repointed to the archive |
| `PITCH.md` | keep | Pitch with traceable claims |
| `PRD.md` | keep | Part 1 frozen; one Part 2 link repointed to the archive (path only) |
| `PUBLIC_MEDIA_DEMO.md` | keep | Read by `demo/start_cloud_media.sh` error message |
| `REMOTE.md` | keep | Internet sharing guide linked from README |
| `RESEARCH.md` | keep | Merged literature review; path to the drafts updated |
| `RUNNING.md` | keep | Full option reference for `python -m otr.app`; two stale defaults corrected and now linked from README |
| `SECURE_LAN.md` | keep | Named by `demo/lan.py` error message |
| `SETUP.md` | keep | Windows setup from scratch; now linked from README |
| `TTS_EXPERIMENT.md` | keep | Lance's synthetic voice test record |
| `UI_STYLE.md` | keep | Rules enforced by `scripts/ui_slop_audit.py` and named in the CSS |
| `STATUS.md` | archive | Docs Keeper dashboard from pass 2 (13:08); its test counts and open issues are long superseded |
| `.docs-keeper-state.json` | archive | Machine state that only STATUS.md used |
| `WORK_SPLIT.md` | archive | Early two-person plan; ownership now lives in README "Contributing" |
| `research/draft_a.md`, `draft_b.md`, `critique_of_a.md`, `critique_of_b.md` | archive | Inputs to RESEARCH.md, which is the merged and checked result |
| `images/media/` (empty, untracked) | delete | Empty folder |
| Output folders of the three person recorder (screenshots under `images/`, videos and proof JSON) | not touched | Being written by the recorder work in progress |
| `CLEANUP_PLAN.md` (this file), `RESULTS.md`, `images/charts/` | new | Plan, results write-up and charts |

## bench/

All kept. The 47-item set (`results.json`, `results.md`, `results.png`), the 36-item held-out set (`results_heldout*`), the sweep and the 40-item samples are named in PRD.md, COMPETITORS.md and README, are the default outputs of `bench/run_eval.py`, and feed the charts. README already calls the small sets regression checks, not evidence, so moving them would only break references. `bench/data_v3/` is the next benchmark in progress and holds data plus manifests.

## Counts

| Decision | Count |
|---|---|
| keep (top-level items plus docs files) | 17 top-level tracked items, 19 docs files, 5 screenshots |
| merge | 0 |
| archive | 10 files (STATUS.md, .docs-keeper-state.json, WORK_SPLIT.md, 4 research files, 3 screenshots) |
| delete | 1 empty untracked folder |

## Not removed, and why

- The operator console `demo/static/index.html` is served by `demo/server.py` and read by `tests/test_demo.py` and `tests/js/harness.js`, so it stays.
- `experiments/browser_chain.py`, `browser_fake_mic.py`, `inject_audio.py` and `scripts/llm_check.py` are not imported anywhere, but each is a working tool for checking the live path or the local model by hand.
- No tracked `__pycache__` or scratch output was found; the only empty tracked files are `__init__.py` package markers.
