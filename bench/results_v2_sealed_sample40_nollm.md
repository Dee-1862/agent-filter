### Set `sealed2`: n = 40 items, 33 clusters, llm = `none`, hold = [30.0] s, md5 `35f17d27`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| C | 15/28 = 54% [36%-70%] | 10/40 = 25% [14%-40%] | 23/40 = 57% [42%-71%] | 109/115 = 95% [89%-98%] | 28/61 = 46% [34%-58%] | 46% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | C |
|---|---|
| explicit_start_end (6) descriptive only | 2/6 | 2/6 |
| explicit_start_implicit_end (4) descriptive only | 1/4 | 1/4 |
| retroactive (10) | 7/7 | 3/10 |
| implicit (11) | 5/11 | 4/11 |
| false_alarm (5) descriptive only | 0/0 | 0/5 |
| public (4) descriptive only | 0/0 | 0/4 |
| ALL (40) | 15/28 | 10/40 |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | scope: 21, confirm: 7, cue: 5 |
| private_leaked | hold_elapsed: 28 |
| public_lost | scope: 22, confirm: 8, cue: 2, flush: 1 |

**By subtype: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| subtype (n) | C |
|---|---|
| contextual_confidential (2) | 0/2 | 2/2 |
| cross_segment_pii (2) | 2/2 | 0/2 |
| ese_long_reactions (3) | 2/3 | 1/3 |
| ese_short (3) | 0/3 | 1/3 |
| esie_long (2) | 1/2 | 1/2 |
| esie_short (2) | 0/2 | 0/2 |
| fa_named_work (1) | 0/0 | 0/1 |
| fa_negated_cue (1) | 0/0 | 0/1 |
| fa_public_lookalike (1) | 0/0 | 0/1 |
| fa_quoted_cue (1) | 0/0 | 0/1 |
| fa_record_sense (1) | 0/0 | 0/1 |
| implicit_health (1) | 0/1 | 0/1 |
| implicit_hr_performance (1) | 0/1 | 0/1 |
| implicit_layoffs (2) | 2/2 | 0/2 |
| implicit_legal (1) | 1/1 | 1/1 |
| implicit_personal (1) | 0/1 | 0/1 |
| implicit_salary (1) | 0/1 | 1/1 |
| public_plain (4) | 0/0 | 0/4 |
| repair (2) | 0/0 | 1/2 |
| retro_count (2) | 2/2 | 0/2 |
| retro_other_confirmed (2) | 2/2 | 0/2 |
| retro_other_refused (1) | 0/0 | 1/1 |
| retro_topic (3) | 3/3 | 1/3 |

**By group: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| group (n) | C |
|---|---|
| confaide (2) | 0/2 | 2/2 |
| seen-author (15) | 6/13 | 2/15 |
| unseen-author (23) | 9/13 | 6/23 |

**By domain: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| domain (n) | C |
|---|---|
| ami (16) | 6/11 | 1/16 |
| committee (9) | 4/7 | 6/9 |
| confaide (2) | 0/2 | 2/2 |
| icsi (13) | 5/8 | 1/13 |

**By difficulty: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| difficulty (n) | C |
|---|---|
| easy (7) | 0/3 | 1/7 |
| hard (14) | 8/13 | 4/14 |
| medium (19) | 7/12 | 5/19 |

**Wall-clock per segment (offline replay; includes LLM calls when used)**: C mean 15.5 ms, p95 18.1 ms

_OTR-Bench v2 (40 items): real QMSum meeting turns (AMI/ICSI/parliamentary committees) with LLM-authored inserted privacy events, plus ConfAIde Tier 4; labels by LLM authors, 15% cross-checked by a blind LLM labeller, no human review. -stub systems are heuristic stand-ins, not LLMs. Wilson 95% intervals; exact McNemar is paired over items._