### Set `sealed2`: n = 40 items, 33 clusters, llm = `ollama:granite4.2:3b`, hold = [30.0] s, md5 `35f17d27`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| A | 23/28 = 82% [64%-92%] | 6/40 = 15% [7%-29%] | 28/40 = 70% [55%-82%] | 110/115 = 96% [90%-98%] | 48/61 = 79% [67%-87%] | 79% |
| C | 19/28 = 68% [49%-82%] | 9/40 = 22% [12%-38%] | 25/40 = 62% [47%-76%] | 114/115 = 99% [95%-100%] | 30/61 = 49% [37%-61%] | 49% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | A | C |
|---|---|---|
| explicit_start_end (6) descriptive only | 4/6 | 1/6 | 5/6 | 2/6 |
| explicit_start_implicit_end (4) descriptive only | 4/4 | 0/4 | 3/4 | 0/4 |
| retroactive (10) | 7/7 | 1/10 | 2/7 | 2/10 |
| implicit (11) | 8/11 | 2/11 | 9/11 | 1/11 |
| false_alarm (5) descriptive only | 0/0 | 2/5 | 0/0 | 1/5 |
| public (4) descriptive only | 0/0 | 0/4 | 0/0 | 3/4 |
| ALL (40) | 23/28 | 6/40 | 19/28 | 9/40 |

**Paired exact McNemar (b = first system has the outcome and second does not; c = the reverse; risk diff = (b - c)/n).**

| first vs second | outcome | n | b | c | both | p | risk diff |
|---|---|---|---|---|---|---|---|
| A vs C | leak | 28 | 8 | 4 | 15 | 0.3877 | +14.3 pts |
| A vs C | leak_or_omit | 40 | 9 | 6 | 19 | 0.6072 | +7.5 pts |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | confirm: 28, cue: 3 |
| private_leaked | hold_elapsed: 30 |
| public_lost | confirm: 11, cue: 2, retro: 1 |

**By subtype: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| subtype (n) | A | C |
|---|---|---|
| contextual_confidential (2) | 0/2 | 2/2 | 2/2 | 0/2 |
| cross_segment_pii (2) | 2/2 | 0/2 | 2/2 | 0/2 |
| ese_long_reactions (3) | 3/3 | 1/3 | 3/3 | 1/3 |
| ese_short (3) | 1/3 | 0/3 | 2/3 | 1/3 |
| esie_long (2) | 2/2 | 0/2 | 2/2 | 0/2 |
| esie_short (2) | 2/2 | 0/2 | 1/2 | 0/2 |
| fa_named_work (1) | 0/0 | 0/1 | 0/0 | 0/1 |
| fa_negated_cue (1) | 0/0 | 0/1 | 0/0 | 0/1 |
| fa_public_lookalike (1) | 0/0 | 1/1 | 0/0 | 1/1 |
| fa_quoted_cue (1) | 0/0 | 1/1 | 0/0 | 0/1 |
| fa_record_sense (1) | 0/0 | 0/1 | 0/0 | 0/1 |
| implicit_health (1) | 1/1 | 0/1 | 1/1 | 1/1 |
| implicit_hr_performance (1) | 0/1 | 0/1 | 1/1 | 0/1 |
| implicit_layoffs (2) | 2/2 | 0/2 | 2/2 | 0/2 |
| implicit_legal (1) | 1/1 | 0/1 | 0/1 | 0/1 |
| implicit_personal (1) | 1/1 | 0/1 | 0/1 | 0/1 |
| implicit_salary (1) | 1/1 | 0/1 | 1/1 | 0/1 |
| public_plain (4) | 0/0 | 0/4 | 0/0 | 3/4 |
| repair (2) | 0/0 | 1/2 | 0/0 | 1/2 |
| retro_count (2) | 2/2 | 0/2 | 1/2 | 0/2 |
| retro_other_confirmed (2) | 2/2 | 0/2 | 1/2 | 0/2 |
| retro_other_refused (1) | 0/0 | 0/1 | 0/0 | 1/1 |
| retro_topic (3) | 3/3 | 0/3 | 0/3 | 0/3 |

**By group: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| group (n) | A | C |
|---|---|---|
| confaide (2) | 0/2 | 2/2 | 2/2 | 0/2 |
| seen-author (15) | 11/13 | 1/15 | 9/13 | 3/15 |
| unseen-author (23) | 12/13 | 3/23 | 8/13 | 6/23 |

**By domain: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| domain (n) | A | C |
|---|---|---|
| ami (16) | 10/11 | 2/16 | 7/11 | 4/16 |
| committee (9) | 7/7 | 1/9 | 3/7 | 2/9 |
| confaide (2) | 0/2 | 2/2 | 2/2 | 0/2 |
| icsi (13) | 6/8 | 1/13 | 7/8 | 3/13 |

**By difficulty: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| difficulty (n) | A | C |
|---|---|---|
| easy (7) | 1/3 | 0/7 | 2/3 | 4/7 |
| hard (14) | 12/13 | 0/14 | 10/13 | 2/14 |
| medium (19) | 10/12 | 6/19 | 7/12 | 3/19 |

**Wall-clock per segment (offline replay; includes LLM calls when used)**: A mean 0.0 ms, p95 0.1 ms; C mean 249.5 ms, p95 314.6 ms

_OTR-Bench v2 (40 items): real QMSum meeting turns (AMI/ICSI/parliamentary committees) with LLM-authored inserted privacy events, plus ConfAIde Tier 4; labels by LLM authors, 15% cross-checked by a blind LLM labeller, no human review. -stub systems are heuristic stand-ins, not LLMs. Wilson 95% intervals; exact McNemar is paired over items._