### Set `sealed2`: n = 150 items, 87 clusters, llm = `none`, hold = [30.0] s, md5 `35f17d27`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| A | 88/101 = 87% [79%-92%] | 24/150 = 16% [11%-23%] | 108/150 = 72% [64%-79%] | 409/429 = 95% [93%-97%] | 192/230 = 83% [78%-88%] | 83% |
| B-stub | 88/101 = 87% [79%-92%] | 23/150 = 15% [10%-22%] | 107/150 = 71% [64%-78%] | 416/429 = 97% [95%-98%] | 192/230 = 83% [78%-88%] | 83% |
| B+-stub | 88/101 = 87% [79%-92%] | 29/150 = 19% [14%-26%] | 107/150 = 71% [64%-78%] | 411/429 = 96% [93%-97%] | 185/230 = 80% [75%-85%] | 80% |
| C | 68/101 = 67% [58%-76%] | 38/150 = 25% [19%-33%] | 96/150 = 64% [56%-71%] | 402/429 = 94% [91%-96%] | 137/230 = 60% [53%-66%] | 60% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| explicit_start_end (22) | 20/22 | 1/22 | 20/22 | 1/22 | 20/22 | 1/22 | 15/22 | 4/22 |
| explicit_start_implicit_end (16) | 16/16 | 1/16 | 16/16 | 1/16 | 16/16 | 2/16 | 12/16 | 2/16 |
| retroactive (35) | 20/22 | 2/35 | 20/22 | 1/35 | 19/22 | 4/35 | 17/22 | 10/35 |
| implicit (41) | 32/41 | 10/41 | 32/41 | 10/41 | 33/41 | 13/41 | 24/41 | 15/41 |
| false_alarm (22) | 0/0 | 9/22 | 0/0 | 9/22 | 0/0 | 7/22 | 0/0 | 6/22 |
| public (14) | 0/0 | 1/14 | 0/0 | 1/14 | 0/0 | 2/14 | 0/0 | 1/14 |
| ALL (150) | 88/101 | 24/150 | 88/101 | 23/150 | 88/101 | 29/150 | 68/101 | 38/150 |

**Paired exact McNemar (b = first system has the outcome and second does not; c = the reverse; risk diff = (b - c)/n).**

| first vs second | outcome | n | b | c | both | p | risk diff |
|---|---|---|---|---|---|---|---|
| A vs B-stub | leak | 101 | 0 | 0 | 88 | 1.0000 | +0.0 pts |
| A vs B-stub | leak_or_omit | 150 | 1 | 0 | 107 | 1.0000 | +0.7 pts |
| A vs B+-stub | leak | 101 | 2 | 2 | 86 | 1.0000 | +0.0 pts |
| A vs B+-stub | leak_or_omit | 150 | 4 | 3 | 104 | 1.0000 | +0.7 pts |
| A vs C | leak | 101 | 20 | 0 | 68 | 0.0000 | +19.8 pts |
| A vs C | leak_or_omit | 150 | 17 | 5 | 91 | 0.0169 | +8.0 pts |
| B-stub vs B+-stub | leak | 101 | 2 | 2 | 86 | 1.0000 | +0.0 pts |
| B-stub vs B+-stub | leak_or_omit | 150 | 4 | 4 | 103 | 1.0000 | +0.0 pts |
| B-stub vs C | leak | 101 | 20 | 0 | 68 | 0.0000 | +19.8 pts |
| B-stub vs C | leak_or_omit | 150 | 17 | 6 | 90 | 0.0347 | +7.3 pts |
| B+-stub vs C | leak | 101 | 21 | 1 | 67 | 0.0000 | +19.8 pts |
| B+-stub vs C | leak_or_omit | 150 | 17 | 6 | 90 | 0.0347 | +7.3 pts |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | scope: 54, confirm: 27, cue: 12 |
| private_leaked | hold_elapsed: 137 |
| public_lost | scope: 124, confirm: 20, cue: 10, flush: 5, retro: 2 |

**By subtype: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| subtype (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| contextual_confidential (8) | 0/8 | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 |
| cross_segment_pii (8) | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 | 1/8 | 8/8 | 2/8 |
| ese_long_reactions (11) | 11/11 | 1/11 | 11/11 | 1/11 | 11/11 | 1/11 | 10/11 | 1/11 |
| ese_short (11) | 9/11 | 0/11 | 9/11 | 0/11 | 9/11 | 0/11 | 5/11 | 3/11 |
| esie_long (8) | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 | 1/8 | 7/8 | 1/8 |
| esie_short (8) | 8/8 | 1/8 | 8/8 | 1/8 | 8/8 | 1/8 | 5/8 | 1/8 |
| fa_named_work (5) | 0/0 | 2/5 | 0/0 | 2/5 | 0/0 | 1/5 | 0/0 | 0/5 |
| fa_negated_cue (4) | 0/0 | 2/4 | 0/0 | 2/4 | 0/0 | 2/4 | 0/0 | 3/4 |
| fa_public_lookalike (4) | 0/0 | 1/4 | 0/0 | 1/4 | 0/0 | 0/4 | 0/0 | 1/4 |
| fa_quoted_cue (5) | 0/0 | 4/5 | 0/0 | 4/5 | 0/0 | 4/5 | 0/0 | 2/5 |
| fa_record_sense (4) | 0/0 | 0/4 | 0/0 | 0/4 | 0/0 | 0/4 | 0/0 | 0/4 |
| implicit_health (4) | 4/4 | 0/4 | 4/4 | 0/4 | 4/4 | 0/4 | 1/4 | 0/4 |
| implicit_hr_performance (4) | 3/4 | 0/4 | 3/4 | 0/4 | 4/4 | 0/4 | 3/4 | 1/4 |
| implicit_layoffs (5) | 5/5 | 0/5 | 5/5 | 0/5 | 5/5 | 1/5 | 5/5 | 0/5 |
| implicit_legal (4) | 4/4 | 1/4 | 4/4 | 1/4 | 4/4 | 2/4 | 3/4 | 2/4 |
| implicit_personal (4) | 4/4 | 0/4 | 4/4 | 0/4 | 4/4 | 0/4 | 2/4 | 0/4 |
| implicit_salary (4) | 4/4 | 1/4 | 4/4 | 1/4 | 4/4 | 1/4 | 2/4 | 2/4 |
| public_plain (14) | 0/0 | 1/14 | 0/0 | 1/14 | 0/0 | 2/14 | 0/0 | 1/14 |
| repair (8) | 0/0 | 1/8 | 0/0 | 1/8 | 0/0 | 1/8 | 0/0 | 1/8 |
| retro_count (7) | 7/7 | 0/7 | 7/7 | 0/7 | 7/7 | 1/7 | 5/7 | 1/7 |
| retro_other_confirmed (6) | 4/6 | 1/6 | 4/6 | 0/6 | 4/6 | 1/6 | 4/6 | 3/6 |
| retro_other_refused (5) | 0/0 | 0/5 | 0/0 | 0/5 | 0/0 | 0/5 | 0/0 | 1/5 |
| retro_topic (9) | 9/9 | 0/9 | 9/9 | 0/9 | 8/9 | 1/9 | 8/9 | 4/9 |

**By group: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| group (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| confaide (8) | 0/8 | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 |
| seen-author (48) | 32/35 | 6/48 | 32/35 | 5/48 | 34/35 | 6/48 | 22/35 | 11/48 |
| unseen-author (94) | 56/58 | 10/94 | 56/58 | 10/94 | 54/58 | 15/94 | 46/58 | 19/94 |

**By domain: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| domain (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| ami (62) | 42/44 | 7/62 | 42/44 | 7/62 | 43/44 | 5/62 | 32/44 | 8/62 |
| committee (30) | 19/20 | 7/30 | 19/20 | 6/30 | 17/20 | 14/30 | 13/20 | 16/30 |
| confaide (8) | 0/8 | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 |
| icsi (50) | 27/29 | 2/50 | 27/29 | 2/50 | 28/29 | 2/50 | 23/29 | 6/50 |

**By difficulty: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| difficulty (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| easy (25) | 9/11 | 1/25 | 9/11 | 1/25 | 9/11 | 2/25 | 5/11 | 4/25 |
| hard (52) | 44/47 | 3/52 | 44/47 | 2/52 | 45/47 | 7/52 | 35/47 | 12/52 |
| medium (73) | 35/43 | 20/73 | 35/43 | 20/73 | 34/43 | 20/73 | 28/43 | 22/73 |

**Wall-clock per segment (offline replay; includes LLM calls when used)**: A mean 0.0 ms, p95 0.1 ms; B-stub mean 0.0 ms, p95 0.1 ms; B+-stub mean 0.0 ms, p95 0.1 ms; C mean 12.1 ms, p95 24.0 ms

_OTR-Bench v2 (150 items): real QMSum meeting turns (AMI/ICSI/parliamentary committees) with LLM-authored inserted privacy events, plus ConfAIde Tier 4; labels by LLM authors, 15% cross-checked by a blind LLM labeller, no human review. -stub systems are heuristic stand-ins, not LLMs. Wilson 95% intervals; exact McNemar is paired over items._