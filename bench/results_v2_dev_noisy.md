### Set `dev2_noisy`: n = 63 items, 54 clusters, llm = `none`, hold = [30.0] s, md5 `cc1fdd9b`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| A | 40/41 = 98% [87%-100%] | 7/63 = 11% [5%-21%] | 45/63 = 71% [59%-81%] | 147/152 = 97% [93%-99%] | 83/87 = 95% [89%-98%] | 95% |
| B-stub | 40/41 = 98% [87%-100%] | 7/63 = 11% [5%-21%] | 45/63 = 71% [59%-81%] | 151/152 = 99% [96%-100%] | 83/87 = 95% [89%-98%] | 95% |
| B+-stub | 41/41 = 100% [91%-100%] | 6/63 = 10% [4%-19%] | 44/63 = 70% [58%-80%] | 148/152 = 97% [93%-99%] | 83/87 = 95% [89%-98%] | 95% |
| C | 29/41 = 71% [56%-82%] | 20/63 = 32% [22%-44%] | 43/63 = 68% [56%-78%] | 145/152 = 95% [91%-98%] | 61/87 = 70% [60%-79%] | 70% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| explicit_start_end (8) descriptive only | 8/8 | 1/8 | 8/8 | 1/8 | 8/8 | 1/8 | 5/8 | 4/8 |
| explicit_start_implicit_end (6) descriptive only | 6/6 | 0/6 | 6/6 | 0/6 | 6/6 | 1/6 | 4/6 | 1/6 |
| retroactive (15) | 8/9 | 1/15 | 8/9 | 1/15 | 9/9 | 1/15 | 6/9 | 6/15 |
| implicit (18) | 18/18 | 0/18 | 18/18 | 0/18 | 18/18 | 0/18 | 14/18 | 4/18 |
| false_alarm (10) | 0/0 | 5/10 | 0/0 | 5/10 | 0/0 | 3/10 | 0/0 | 4/10 |
| public (6) descriptive only | 0/0 | 0/6 | 0/0 | 0/6 | 0/0 | 0/6 | 0/0 | 1/6 |
| ALL (63) | 40/41 | 7/63 | 40/41 | 7/63 | 41/41 | 6/63 | 29/41 | 20/63 |

**Paired exact McNemar (b = first system has the outcome and second does not; c = the reverse; risk diff = (b - c)/n).**

| first vs second | outcome | n | b | c | both | p | risk diff |
|---|---|---|---|---|---|---|---|
| A vs B-stub | leak | 41 | 0 | 0 | 40 | 1.0000 | +0.0 pts |
| A vs B-stub | leak_or_omit | 63 | 0 | 0 | 45 | 1.0000 | +0.0 pts |
| A vs B+-stub | leak | 41 | 0 | 1 | 40 | 1.0000 | -2.4 pts |
| A vs B+-stub | leak_or_omit | 63 | 2 | 1 | 43 | 1.0000 | +1.6 pts |
| A vs C | leak | 41 | 11 | 0 | 29 | 0.0010 | +26.8 pts |
| A vs C | leak_or_omit | 63 | 8 | 6 | 37 | 0.7905 | +3.2 pts |
| B-stub vs B+-stub | leak | 41 | 0 | 1 | 40 | 1.0000 | -2.4 pts |
| B-stub vs B+-stub | leak_or_omit | 63 | 2 | 1 | 43 | 1.0000 | +1.6 pts |
| B-stub vs C | leak | 41 | 11 | 0 | 29 | 0.0010 | +26.8 pts |
| B-stub vs C | leak_or_omit | 63 | 8 | 6 | 37 | 0.7905 | +3.2 pts |
| B+-stub vs C | leak | 41 | 12 | 0 | 29 | 0.0005 | +29.3 pts |
| B+-stub vs C | leak_or_omit | 63 | 6 | 5 | 38 | 1.0000 | +1.6 pts |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | confirm: 13, scope: 12, cue: 1 |
| private_leaked | hold_elapsed: 61 |
| public_lost | scope: 61, cue: 7, confirm: 4, retro: 2 |

**By subtype: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| subtype (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| contextual_confidential (3) | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 |
| cross_segment_pii (3) | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 |
| ese_long_reactions (4) | 4/4 | 1/4 | 4/4 | 1/4 | 4/4 | 1/4 | 4/4 | 1/4 |
| ese_short (4) | 4/4 | 0/4 | 4/4 | 0/4 | 4/4 | 0/4 | 1/4 | 3/4 |
| esie_long (3) | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 |
| esie_short (3) | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 1/3 | 1/3 | 1/3 |
| fa_named_work (2) | 0/0 | 1/2 | 0/0 | 1/2 | 0/0 | 1/2 | 0/0 | 1/2 |
| fa_negated_cue (2) | 0/0 | 0/2 | 0/0 | 0/2 | 0/0 | 0/2 | 0/0 | 2/2 |
| fa_public_lookalike (2) | 0/0 | 2/2 | 0/0 | 2/2 | 0/0 | 0/2 | 0/0 | 0/2 |
| fa_quoted_cue (2) | 0/0 | 2/2 | 0/0 | 2/2 | 0/0 | 2/2 | 0/0 | 1/2 |
| fa_record_sense (2) | 0/0 | 0/2 | 0/0 | 0/2 | 0/0 | 0/2 | 0/0 | 0/2 |
| implicit_health (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 |
| implicit_hr_performance (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 1/2 | 0/2 |
| implicit_layoffs (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 2/2 |
| implicit_legal (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 0/2 | 1/2 |
| implicit_personal (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 1/2 | 1/2 |
| implicit_salary (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 |
| public_plain (6) | 0/0 | 0/6 | 0/0 | 0/6 | 0/0 | 0/6 | 0/0 | 1/6 |
| repair (4) | 0/0 | 0/4 | 0/0 | 0/4 | 0/0 | 0/4 | 0/0 | 1/4 |
| retro_count (3) | 3/3 | 1/3 | 3/3 | 1/3 | 3/3 | 1/3 | 2/3 | 1/3 |
| retro_other_confirmed (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 |
| retro_other_refused (2) | 0/0 | 0/2 | 0/0 | 0/2 | 0/0 | 0/2 | 0/0 | 1/2 |
| retro_topic (4) | 3/4 | 0/4 | 3/4 | 0/4 | 4/4 | 0/4 | 2/4 | 3/4 |

**By group: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| group (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| confaide (3) | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 |
| seen-author (60) | 37/38 | 7/60 | 37/38 | 7/60 | 38/38 | 6/60 | 26/38 | 20/60 |

**By domain: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| domain (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| ami (28) | 19/20 | 3/28 | 19/20 | 3/28 | 20/20 | 1/28 | 17/20 | 5/28 |
| committee (15) | 9/9 | 2/15 | 9/9 | 2/15 | 9/9 | 3/15 | 5/9 | 7/15 |
| confaide (3) | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 |
| icsi (17) | 9/9 | 2/17 | 9/9 | 2/17 | 9/9 | 2/17 | 4/9 | 8/17 |

**By difficulty: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| difficulty (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| easy (10) | 4/4 | 0/10 | 4/4 | 0/10 | 4/4 | 0/10 | 1/4 | 4/10 |
| hard (22) | 20/20 | 0/22 | 20/20 | 0/22 | 20/20 | 0/22 | 16/20 | 5/22 |
| medium (31) | 16/17 | 7/31 | 16/17 | 7/31 | 17/17 | 6/31 | 12/17 | 11/31 |

**Wall-clock per segment (offline replay; includes LLM calls when used)**: A mean 0.0 ms, p95 0.1 ms; B-stub mean 0.0 ms, p95 0.1 ms; B+-stub mean 0.1 ms, p95 0.2 ms; C mean 9.9 ms, p95 14.6 ms

_OTR-Bench v2 (63 items): real QMSum meeting turns (AMI/ICSI/parliamentary committees) with LLM-authored inserted privacy events, plus ConfAIde Tier 4; labels by LLM authors, 15% cross-checked by a blind LLM labeller, no human review. -stub systems are heuristic stand-ins, not LLMs. Wilson 95% intervals; exact McNemar is paired over items._