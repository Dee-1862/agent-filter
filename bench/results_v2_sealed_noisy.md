### Set `sealed2_noisy`: n = 38 items, 34 clusters, llm = `none`, hold = [30.0] s, md5 `c51016f2`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| A | 23/26 = 88% [71%-96%] | 6/38 = 16% [7%-30%] | 28/38 = 74% [58%-85%] | 95/97 = 98% [93%-99%] | 52/59 = 88% [77%-94%] | 88% |
| B-stub | 23/26 = 88% [71%-96%] | 6/38 = 16% [7%-30%] | 28/38 = 74% [58%-85%] | 96/97 = 99% [94%-100%] | 52/59 = 88% [77%-94%] | 88% |
| B+-stub | 22/26 = 85% [66%-94%] | 6/38 = 16% [7%-30%] | 25/38 = 66% [50%-79%] | 95/97 = 98% [93%-99%] | 49/59 = 83% [72%-91%] | 83% |
| C | 20/26 = 77% [58%-89%] | 10/38 = 26% [15%-42%] | 26/38 = 68% [53%-81%] | 94/97 = 97% [91%-99%] | 41/59 = 69% [57%-80%] | 69% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| explicit_start_end (6) descriptive only | 5/6 | 0/6 | 5/6 | 0/6 | 5/6 | 0/6 | 5/6 | 1/6 |
| explicit_start_implicit_end (4) descriptive only | 4/4 | 0/4 | 4/4 | 0/4 | 4/4 | 0/4 | 4/4 | 0/4 |
| retroactive (9) descriptive only | 5/6 | 0/9 | 5/6 | 0/9 | 4/6 | 1/9 | 5/6 | 3/9 |
| implicit (10) | 9/10 | 2/10 | 9/10 | 2/10 | 9/10 | 3/10 | 6/10 | 5/10 |
| false_alarm (5) descriptive only | 0/0 | 4/5 | 0/0 | 4/5 | 0/0 | 2/5 | 0/0 | 1/5 |
| public (4) descriptive only | 0/0 | 0/4 | 0/0 | 0/4 | 0/0 | 0/4 | 0/0 | 0/4 |
| ALL (38) | 23/26 | 6/38 | 23/26 | 6/38 | 22/26 | 6/38 | 20/26 | 10/38 |

**Paired exact McNemar (b = first system has the outcome and second does not; c = the reverse; risk diff = (b - c)/n).**

| first vs second | outcome | n | b | c | both | p | risk diff |
|---|---|---|---|---|---|---|---|
| A vs B-stub | leak | 26 | 0 | 0 | 23 | 1.0000 | +0.0 pts |
| A vs B-stub | leak_or_omit | 38 | 0 | 0 | 28 | 1.0000 | +0.0 pts |
| A vs B+-stub | leak | 26 | 1 | 0 | 22 | 1.0000 | +3.8 pts |
| A vs B+-stub | leak_or_omit | 38 | 3 | 0 | 25 | 0.2500 | +7.9 pts |
| A vs C | leak | 26 | 3 | 0 | 20 | 0.2500 | +11.5 pts |
| A vs C | leak_or_omit | 38 | 5 | 3 | 23 | 0.7266 | +5.3 pts |
| B-stub vs B+-stub | leak | 26 | 1 | 0 | 22 | 1.0000 | +3.8 pts |
| B-stub vs B+-stub | leak_or_omit | 38 | 3 | 0 | 25 | 0.2500 | +7.9 pts |
| B-stub vs C | leak | 26 | 3 | 0 | 20 | 0.2500 | +11.5 pts |
| B-stub vs C | leak_or_omit | 38 | 5 | 3 | 23 | 0.7266 | +5.3 pts |
| B+-stub vs C | leak | 26 | 3 | 1 | 19 | 0.6250 | +7.7 pts |
| B+-stub vs C | leak_or_omit | 38 | 3 | 4 | 22 | 1.0000 | -2.6 pts |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | scope: 9, confirm: 8, cue: 1 |
| private_leaked | hold_elapsed: 41 |
| public_lost | scope: 25, confirm: 7, cue: 3, retro: 1, flush: 1 |

**By subtype: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| subtype (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| contextual_confidential (2) | 1/2 | 1/2 | 1/2 | 1/2 | 1/2 | 1/2 | 0/2 | 1/2 |
| cross_segment_pii (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 1/2 |
| ese_long_reactions (3) | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 |
| ese_short (3) | 2/3 | 0/3 | 2/3 | 0/3 | 2/3 | 0/3 | 2/3 | 1/3 |
| esie_long (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 |
| esie_short (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 0/2 |
| fa_named_work (1) | 0/0 | 1/1 | 0/0 | 1/1 | 0/0 | 0/1 | 0/0 | 0/1 |
| fa_negated_cue (1) | 0/0 | 1/1 | 0/0 | 1/1 | 0/0 | 1/1 | 0/0 | 1/1 |
| fa_public_lookalike (1) | 0/0 | 1/1 | 0/0 | 1/1 | 0/0 | 0/1 | 0/0 | 0/1 |
| fa_quoted_cue (1) | 0/0 | 1/1 | 0/0 | 1/1 | 0/0 | 1/1 | 0/0 | 0/1 |
| fa_record_sense (1) | 0/0 | 0/1 | 0/0 | 0/1 | 0/0 | 0/1 | 0/0 | 0/1 |
| implicit_health (1) | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| implicit_hr_performance (1) | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| implicit_layoffs (1) | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| implicit_legal (1) | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| implicit_personal (1) | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| implicit_salary (1) | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 0/1 | 1/1 |
| public_plain (4) | 0/0 | 0/4 | 0/0 | 0/4 | 0/0 | 0/4 | 0/0 | 0/4 |
| repair (2) | 0/0 | 0/2 | 0/0 | 0/2 | 0/0 | 0/2 | 0/0 | 0/2 |
| retro_count (2) | 2/2 | 0/2 | 2/2 | 0/2 | 2/2 | 1/2 | 2/2 | 0/2 |
| retro_other_confirmed (2) | 1/2 | 0/2 | 1/2 | 0/2 | 1/2 | 0/2 | 1/2 | 1/2 |
| retro_other_refused (1) | 0/0 | 0/1 | 0/0 | 0/1 | 0/0 | 0/1 | 0/0 | 1/1 |
| retro_topic (2) | 2/2 | 0/2 | 2/2 | 0/2 | 1/2 | 0/2 | 2/2 | 1/2 |

**By group: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| group (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| confaide (2) | 1/2 | 1/2 | 1/2 | 1/2 | 1/2 | 1/2 | 0/2 | 1/2 |
| seen-author (9) | 6/6 | 2/9 | 6/6 | 2/9 | 6/6 | 2/9 | 6/6 | 3/9 |
| unseen-author (27) | 16/18 | 3/27 | 16/18 | 3/27 | 15/18 | 3/27 | 14/18 | 6/27 |

**By domain: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| domain (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| ami (18) | 13/14 | 3/18 | 13/14 | 3/18 | 13/14 | 1/18 | 13/14 | 3/18 |
| committee (9) | 7/7 | 1/9 | 7/7 | 1/9 | 6/7 | 3/9 | 6/7 | 5/9 |
| confaide (2) | 1/2 | 1/2 | 1/2 | 1/2 | 1/2 | 1/2 | 0/2 | 1/2 |
| icsi (9) | 2/3 | 1/9 | 2/3 | 1/9 | 2/3 | 1/9 | 1/3 | 1/9 |

**By difficulty: Leak k/n | Omit-Public k/n** (n < 10: descriptive only)

| difficulty (n) | A | B-stub | B+-stub | C |
|---|---|---|---|---|
| easy (7) | 2/3 | 0/7 | 2/3 | 0/7 | 2/3 | 0/7 | 2/3 | 1/7 |
| hard (13) | 11/12 | 1/13 | 11/12 | 1/13 | 11/12 | 2/13 | 9/12 | 6/13 |
| medium (18) | 10/11 | 5/18 | 10/11 | 5/18 | 9/11 | 4/18 | 9/11 | 3/18 |

**Wall-clock per segment (offline replay; includes LLM calls when used)**: A mean 0.0 ms, p95 0.1 ms; B-stub mean 0.0 ms, p95 0.1 ms; B+-stub mean 0.0 ms, p95 0.1 ms; C mean 9.2 ms, p95 14.2 ms

_OTR-Bench v2 (38 items): real QMSum meeting turns (AMI/ICSI/parliamentary committees) with LLM-authored inserted privacy events, plus ConfAIde Tier 4; labels by LLM authors, 15% cross-checked by a blind LLM labeller, no human review. -stub systems are heuristic stand-ins, not LLMs. Wilson 95% intervals; exact McNemar is paired over items._