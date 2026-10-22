### Set `dev2`: n = 246 items, 133 clusters, llm = `none`, hold = [30.0] s, md5 `0c743eb9`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| A | 142/165 = 86% [80%-91%] | 41/246 = 17% [13%-22%] | 178/246 = 72% [66%-78%] | 668/702 = 95% [93%-97%] | 289/350 = 83% [78%-86%] | 83% |
| B-stub | 144/165 = 87% [81%-92%] | 38/246 = 15% [11%-20%] | 177/246 = 72% [66%-77%] | 689/702 = 98% [97%-99%] | 292/350 = 83% [79%-87%] | 83% |
| B+-stub | 141/165 = 85% [79%-90%] | 41/246 = 17% [13%-22%] | 174/246 = 71% [65%-76%] | 677/702 = 96% [95%-98%] | 284/350 = 81% [77%-85%] | 81% |
| C | 98/165 = 59% [52%-67%] | 87/246 = 35% [30%-42%] | 165/246 = 67% [61%-73%] | 661/702 = 94% [92%-96%] | 195/350 = 56% [50%-61%] | 56% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| explicit_start_end (34) | 27/34 | 6/34 | 29/34 | 3/34 | 26/34 | 7/34 | 21/34 | 14/34 |
| explicit_start_implicit_end (24) | 23/24 | 1/24 | 23/24 | 1/24 | 24/24 | 2/24 | 10/24 | 9/24 |
| retroactive (57) | 30/36 | 6/57 | 30/36 | 6/57 | 30/36 | 6/57 | 18/36 | 25/57 |
| implicit (71) | 62/71 | 9/71 | 62/71 | 9/71 | 61/71 | 11/71 | 49/71 | 21/71 |
| false_alarm (38) | 0/0 | 19/38 | 0/0 | 19/38 | 0/0 | 14/38 | 0/0 | 16/38 |
| public (22) | 0/0 | 0/22 | 0/0 | 0/22 | 0/0 | 1/22 | 0/0 | 2/22 |
| ALL (246) | 142/165 | 41/246 | 144/165 | 38/246 | 141/165 | 41/246 | 98/165 | 87/246 |

**Paired exact McNemar (b = first system has the outcome and second does not; c = the reverse; risk diff = (b - c)/n).**

| first vs second | outcome | n | b | c | both | p | risk diff |
|---|---|---|---|---|---|---|---|
| A vs B-stub | leak | 165 | 0 | 2 | 142 | 0.5000 | -1.2 pts |
| A vs B-stub | leak_or_omit | 246 | 1 | 0 | 177 | 1.0000 | +0.4 pts |
| A vs B+-stub | leak | 165 | 7 | 6 | 135 | 1.0000 | +0.6 pts |
| A vs B+-stub | leak_or_omit | 246 | 14 | 10 | 164 | 0.5413 | +1.6 pts |
| A vs C | leak | 165 | 50 | 6 | 92 | 0.0000 | +26.7 pts |
| A vs C | leak_or_omit | 246 | 34 | 21 | 144 | 0.1048 | +5.3 pts |
| B-stub vs B+-stub | leak | 165 | 9 | 6 | 135 | 0.6072 | +1.8 pts |
| B-stub vs B+-stub | leak_or_omit | 246 | 14 | 11 | 163 | 0.6900 | +1.2 pts |
| B-stub vs C | leak | 165 | 50 | 4 | 94 | 0.0000 | +27.9 pts |
| B-stub vs C | leak_or_omit | 246 | 34 | 22 | 143 | 0.1409 | +4.9 pts |
| B+-stub vs C | leak | 165 | 47 | 4 | 94 | 0.0000 | +26.1 pts |
| B+-stub vs C | leak_or_omit | 246 | 29 | 20 | 145 | 0.2529 | +3.7 pts |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | scope: 84, confirm: 55, cue: 11, retro: 5 |
| private_leaked | hold_elapsed: 195 |
| public_lost | scope: 250, cue: 24, flush: 22, confirm: 19, retro: 7 |

**By subtype: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| subtype (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| contextual_confidential (12) | 4/12 | 8/12 | 4/12 | 8/12 | 4/12 | 8/12 | 4/12 | 8/12 |
| cross_segment_pii (12) | 12/12 | 0/12 | 12/12 | 0/12 | 12/12 | 0/12 | 12/12 | 1/12 |
| ese_long_reactions (17) | 14/17 | 4/17 | 16/17 | 1/17 | 14/17 | 4/17 | 14/17 | 4/17 |
| ese_short (17) | 13/17 | 2/17 | 13/17 | 2/17 | 12/17 | 3/17 | 7/17 | 10/17 |
| esie_long (12) | 12/12 | 1/12 | 12/12 | 1/12 | 12/12 | 1/12 | 8/12 | 3/12 |
| esie_short (12) | 11/12 | 0/12 | 11/12 | 0/12 | 12/12 | 1/12 | 2/12 | 6/12 |
| fa_named_work (7) | 0/0 | 4/7 | 0/0 | 4/7 | 0/0 | 4/7 | 0/0 | 2/7 |
| fa_negated_cue (8) | 0/0 | 2/8 | 0/0 | 2/8 | 0/0 | 3/8 | 0/0 | 7/8 |
| fa_public_lookalike (8) | 0/0 | 7/8 | 0/0 | 7/8 | 0/0 | 1/8 | 0/0 | 1/8 |
| fa_quoted_cue (7) | 0/0 | 5/7 | 0/0 | 5/7 | 0/0 | 6/7 | 0/0 | 5/7 |
| fa_record_sense (8) | 0/0 | 1/8 | 0/0 | 1/8 | 0/0 | 0/8 | 0/0 | 1/8 |
| implicit_health (8) | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 | 0/8 | 3/8 | 0/8 |
| implicit_hr_performance (8) | 8/8 | 0/8 | 8/8 | 0/8 | 7/8 | 0/8 | 5/8 | 2/8 |
| implicit_layoffs (7) | 7/7 | 0/7 | 7/7 | 0/7 | 7/7 | 0/7 | 6/7 | 2/7 |
| implicit_legal (8) | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 | 0/8 | 6/8 | 3/8 |
| implicit_personal (8) | 8/8 | 0/8 | 8/8 | 0/8 | 8/8 | 1/8 | 5/8 | 2/8 |
| implicit_salary (8) | 7/8 | 1/8 | 7/8 | 1/8 | 7/8 | 2/8 | 8/8 | 3/8 |
| public_plain (22) | 0/0 | 0/22 | 0/0 | 0/22 | 0/0 | 1/22 | 0/0 | 2/22 |
| repair (14) | 0/0 | 3/14 | 0/0 | 3/14 | 0/0 | 3/14 | 0/0 | 4/14 |
| retro_count (11) | 11/11 | 1/11 | 11/11 | 1/11 | 11/11 | 1/11 | 6/11 | 2/11 |
| retro_other_confirmed (10) | 7/10 | 1/10 | 7/10 | 1/10 | 8/10 | 1/10 | 6/10 | 5/10 |
| retro_other_refused (7) | 0/0 | 0/7 | 0/0 | 0/7 | 0/0 | 0/7 | 0/0 | 2/7 |
| retro_topic (15) | 12/15 | 1/15 | 12/15 | 1/15 | 11/15 | 1/15 | 6/15 | 12/15 |

**By group: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| group (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| confaide (12) | 4/12 | 8/12 | 4/12 | 8/12 | 4/12 | 8/12 | 4/12 | 8/12 |
| seen-author (234) | 138/153 | 33/234 | 140/153 | 30/234 | 137/153 | 33/234 | 94/153 | 79/234 |

**By domain: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| domain (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| ami (124) | 81/89 | 14/124 | 82/89 | 12/124 | 81/89 | 9/124 | 58/89 | 35/124 |
| committee (42) | 21/23 | 9/42 | 21/23 | 9/42 | 20/23 | 14/42 | 14/23 | 22/42 |
| confaide (12) | 4/12 | 8/12 | 4/12 | 8/12 | 4/12 | 8/12 | 4/12 | 8/12 |
| icsi (68) | 36/41 | 10/68 | 37/41 | 9/68 | 36/41 | 10/68 | 22/41 | 22/68 |

**By difficulty: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| difficulty (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| easy (39) | 13/17 | 2/39 | 13/17 | 2/39 | 12/17 | 4/39 | 7/17 | 12/39 |
| hard (88) | 77/81 | 3/88 | 77/81 | 3/88 | 77/81 | 5/88 | 59/81 | 23/88 |
| medium (119) | 52/67 | 36/119 | 54/67 | 33/119 | 52/67 | 32/119 | 32/67 | 52/119 |

**Wall-clock per segment (offline replay; includes LLM calls when used)**: A mean 0.0 ms, p95 0.1 ms; B-stub mean 0.0 ms, p95 0.1 ms; B+-stub mean 0.0 ms, p95 0.1 ms; C mean 13.8 ms, p95 20.9 ms

_OTR-Bench v2 (246 items): real QMSum meeting turns (AMI/ICSI/parliamentary committees) with LLM-authored inserted privacy events, plus ConfAIde Tier 4; labels by LLM authors, 15% cross-checked by a blind LLM labeller, no human review. -stub systems are heuristic stand-ins, not LLMs. Wilson 95% intervals; exact McNemar is paired over items._