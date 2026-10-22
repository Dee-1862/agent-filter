# Sealed held-out set

SEALED: `heldout.jsonl` and `heldout_noisy.jsonl` are for evaluation only. The engine owner
must not read them, grep them, or tune cue lists, regexes, prompts or thresholds against them.
If a system is changed after seeing a held-out failure, the set is burned for that system and a
new set is needed. Report results with the md5 of the file (`bench/run_eval.py` stores it).

- `heldout.jsonl`: 36 items, 6 per case type (`explicit_start_end`, `explicit_start_implicit_end`,
  `retroactive`, `implicit`, `false_alarm`, `public`), `source = "synthetic-heldout"`, 8-10 segments each.
  Same schema as `otr_bench.jsonl` plus two optional fields: `cluster` (items that share a
  scenario, e.g. a retraction item and its no-cue control twin share one) and `cue_ids`
  (segments that carry a cue or cue-like phrase; used only to choose what the noisy variant corrupts).
  `retroactive` and `false_alarm`/`public` items may have empty `private_ids` (repairs, no-cue controls,
  look-alikes). Neutral segments (cue lines, topic-change lines) are in neither list and are not scored.
- `heldout_noisy.jsonl`: the same 36 items (ids get a `-n` suffix, `source = "synthetic-heldout-noisy"`)
  with deterministic ASR-style corruption applied to `cue_ids` segments only. Gold labels are unchanged.
- Rebuild with `python -m bench.heldout.build_heldout` (deterministic; sources in `_items.py`).
- Written by the same team that built the systems and not hand-checked by an independent person.
  Wording was deliberately varied from the dev set, but the author knows the dev cue lists, so
  this is a held-out set, not an independent test set.

## Noisy-ASR corruption rules (cue-bearing segments only)

Applied in this order to each segment in `cue_ids`; `h = int(md5(original segment id), 16)`.

1. R4 (negation drop): if `h % 10 == 0`, delete the first negation token (`don't`, `do not`, `not`, `never`, `nothing`, `no`). About 10% of cue lines; 1 of 34 cue lines was hit.
2. Lowercase everything.
3. R2 (cue mishearing): `off the record` -> `of the record`; `strike that` / `scratch that` -> `strike dat` / `scratch dat`.
4. R3 (homophones): `write` -> `right`; `pause` -> `paws`; if `h % 2 == 0`, `notes` -> `nodes`.
5. R1 (punctuation): drop every character that is not a word character, space, apostrophe or hyphen; collapse whitespace.

Segments not in `cue_ids` are untouched. `public_facts` are filtered to those still present in the corrupted public text.
