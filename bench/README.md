# OTR-Bench

Small benchmark for "off the record" handling in meeting notes (PRD section 1.7).

**Honest status: this is early evidence only.** The current set is 47 hand-written, synthetic
meeting snippets (8-10 per case type, 8-20 segments each, `source = "synthetic"`); the last 7
(`_items_c.py`) mimic live-ASR text (lower case, no punctuation, garbled cues such as "of the
record", "strike dat", "back on da record"). The cue heuristics in `otr/` were developed while
reading these items, so they are a dev set, not a test set: a separate 9-item check written
afterwards (not committed) gave C 53% leak vs A 53% before gaps found there were fixed. It was written
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
- **C**: `otr.pipeline.Pipeline`, replayed as a live stream: each segment is pushed at its `t_end`, the clock is ticked there, and after the last segment the clock runs to `t_end + hold_seconds` (so `tick()` releases held text) before `flush()`. `pending_confirm` is auto-answered `keep_out=True` ("user says yes"). C also reports the **committed-leak rate** (private segments ever committed, even if retro-removed later): this is what `--hold-seconds` changes; the final-notes leak rate is the same for any hold because committed text can still be retro-removed.

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

## Held-out set, B+, causal modes, new metrics (added)

- `bench/heldout/` holds a SEALED 36-item set and a noisy-ASR variant; see `bench/heldout/README.md`. Engine code must not be tuned on it.
- `python -m bench.run_eval --set dev|heldout|heldout_noisy|all` (results: `results*.json`, `.md`, and a leak vs omit scatter `.png`).
- Systems: `A`, `B`, `B+` (contextual-integrity extract-then-judge), `B/causal`, `B+/causal` (each segment decided with text only up to `t_end + hold`, the same lag as C), `C`. Without `--llm`, B and B+ are labelled `-stub` heuristics; the stubs are forward-only scanners, so their hindsight and causal variants differ only when a retraction arrives later than the hold window.
- Metrics: item-level Leak, Omit-Public, Leak-or-Omit (ConfAIde Table 4 style), Conveyance, Wilson 95% intervals, exact McNemar between systems (b, c, p, risk difference), cluster counts, per-stage log for C from `Pipeline.audit_log()`. Per-case cells with n < 10 are descriptive only.
