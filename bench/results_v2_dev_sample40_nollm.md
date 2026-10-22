### Set `dev2`: n = 40 items, 36 clusters, llm = `none`, hold = [30.0] s, md5 `0c743eb9`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| C | 14/27 = 52% [34%-69%] | 18/40 = 45% [31%-60%] | 29/40 = 72% [57%-84%] | 105/112 = 94% [88%-97%] | 26/58 = 45% [33%-58%] | 45% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | C |
|---|---|
| explicit_start_end (6) descriptive only | 4/6 | 3/6 |
| explicit_start_implicit_end (4) descriptive only | 2/4 | 2/4 |
| retroactive (10) | 2/7 | 6/10 |
| implicit (10) | 6/10 | 3/10 |
| false_alarm (6) descriptive only | 0/0 | 3/6 |
| public (4) descriptive only | 0/0 | 1/4 |
| ALL (40) | 14/27 | 18/40 |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | scope: 16, confirm: 13, retro: 2, cue: 1 |
| private_leaked | hold_elapsed: 26 |
| public_lost | scope: 46, cue: 6, flush: 4, confirm: 2 |

**By subtype: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| subtype (n) | C |
|---|---|
| contextual_confidential (2) | 1/2 | 1/2 |
| cross_segment_pii (2) | 2/2 | 0/2 |
| ese_long_reactions (3) | 2/3 | 1/3 |
| ese_short (3) | 2/3 | 2/3 |
| esie_long (2) | 2/2 | 0/2 |
| esie_short (2) | 0/2 | 2/2 |
| fa_named_work (1) | 0/0 | 1/1 |
| fa_negated_cue (1) | 0/0 | 1/1 |
| fa_public_lookalike (2) | 0/0 | 0/2 |
| fa_quoted_cue (1) | 0/0 | 0/1 |
| fa_record_sense (1) | 0/0 | 1/1 |
| implicit_health (1) | 0/1 | 0/1 |
| implicit_hr_performance (1) | 0/1 | 0/1 |
| implicit_layoffs (1) | 1/1 | 1/1 |
| implicit_legal (1) | 1/1 | 0/1 |
| implicit_personal (1) | 0/1 | 1/1 |
| implicit_salary (1) | 1/1 | 0/1 |
| public_plain (4) | 0/0 | 1/4 |
| repair (2) | 0/0 | 1/2 |
| retro_count (2) | 0/2 | 0/2 |
| retro_other_confirmed (2) | 1/2 | 1/2 |
| retro_other_refused (1) | 0/0 | 1/1 |
| retro_topic (3) | 1/3 | 3/3 |

**By group: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| group (n) | C |
|---|---|
| confaide (2) | 1/2 | 1/2 |
| seen-author (38) | 13/25 | 17/38 |

**By domain: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| domain (n) | C |
|---|---|
| ami (24) | 10/17 | 11/24 |
| committee (2) | 0/0 | 2/2 |
| confaide (2) | 1/2 | 1/2 |
| icsi (12) | 3/8 | 4/12 |

**By difficulty: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| difficulty (n) | C |
|---|---|
| easy (7) | 2/3 | 3/7 |
| hard (13) | 8/12 | 4/13 |
| medium (20) | 4/12 | 11/20 |

**Wall-clock per segment (offline replay; includes LLM calls when used)**: C mean 17.6 ms, p95 17.4 ms

_OTR-Bench v2 (40 items): real QMSum meeting turns (AMI/ICSI/parliamentary committees) with LLM-authored inserted privacy events, plus ConfAIde Tier 4; labels by LLM authors, 15% cross-checked by a blind LLM labeller, no human review. -stub systems are heuristic stand-ins, not LLMs. Wilson 95% intervals; exact McNemar is paired over items._