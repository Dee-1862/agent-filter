# OTR-Bench

Small benchmark for "off the record" handling in meeting notes (PRD section 1.7).

**Honest status: this is early evidence only.** The current set is 40 hand-written, synthetic
meeting snippets (8 per case type, 8-20 segments each, `source = "synthetic"`). It was written
by the same team that built the systems, so it is biased toward the phrasing we anticipated.
ConfAIde and QMSum were not available when it was built; importers exist (below) but have not
been run. With n=8 per case type, differences of a few percentage points are noise. Only about
10 items have been hand-checked, if any; the rest are unreviewed.

## Schema (`otr_bench.jsonl`, one JSON object per line)

| field | meaning |
|---|---|
| `id` | unique item id, e.g. `ese-03` |
| `source` | `synthetic`, `confaide` or `qmsum` |
| `case_type` | `explicit_start_end`, `explicit_start_implicit_end`, `retroactive`, `implicit`, `false_alarm` |
| `segments` | list of `Segment` dicts (`id, speaker, text, t_start, t_end`, see `otr/types.py`) |
| `private_ids` | segment ids that must NOT reach the notes |
| `public_ids` | segment ids that MUST remain |
| `public_facts` | short strings expected to appear in the notes (summary-usefulness proxy) |

Segments in neither list are neutral (cue lines such as "back on the record", "strike that"); they
are not scored either way. `false_alarm` items have empty `private_ids`.

## Metrics (`metrics.py`)

- **leak rate** (primary): leaked private segments / all private segments (micro average); also **item leak rate** (items with at least one leak).
- **over-redaction**: public segments missing from the notes / all public segments.
- **summary usefulness (proxy)**: fraction of `public_facts` found as case-insensitive substrings of the notes text. No LLM summary is used.
- all broken down by case type; `n/a` where undefined (no private segments).

## Systems (`systems.py`)

- **A**: cue regexes (explicit scope, ends only at an explicit end cue) + regex PII + sensitive keywords.
- **B**: one LLM pass returning kept ids as JSON. Without an LLM it runs **B-stub**, a crude heuristic stand-in; B-stub numbers say nothing about a real LLM baseline.
- **C**: `otr.pipeline.Pipeline`, simulated clock from each segment's `t_start`, `pending_confirm` auto-answered `keep_out=True` ("user says yes"), then `flush()`.

## Run

```
python -m bench.build_bench                       # regenerate otr_bench.jsonl from _items_a/_items_b
python -m bench.run_eval --systems A,B,C --llm none --out bench/results.json   # also writes results.md
python -m bench.run_eval --systems C --hold-seconds 0,5,15,30                  # hold-buffer sweep
python -m bench.run_eval --systems B,C --llm ollama:qwen2.5:3b
python -m bench.plot --results bench/results.json --out bench/results.png      # needs matplotlib
python -m pytest tests/test_bench.py -q
```

## Optional importers

- `python -m bench.import_confaide <confaide_clone>` expects `benchmark/tier_4.jsonl` (field names are best-effort; see docstring).
- `python -m bench.import_qmsum <QMSum_clone>` expects `data/ALL/test/*.json`; splices synthetic private spans into real QMSum windows.
Both write a separate jsonl; pass it with `--bench`.
