### Set `heldout_noisy`: n = 36 items, 35 clusters, llm = `none`, hold = [30.0] s, md5 `3dd16142`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| A | 17/22 = 77% [57%-90%] | 10/36 = 28% [16%-44%] | 27/36 = 75% [59%-86%] | 88/107 = 82% [74%-88%] | 41/56 = 73% [60%-83%] | 73% |
| B-stub | 17/22 = 77% [57%-90%] | 6/36 = 17% [8%-32%] | 23/36 = 64% [48%-78%] | 100/107 = 93% [87%-97%] | 42/56 = 75% [62%-84%] | 75% |
| B+-stub | 18/22 = 82% [61%-93%] | 10/36 = 28% [16%-44%] | 27/36 = 75% [59%-86%] | 91/107 = 85% [77%-91%] | 37/56 = 66% [53%-77%] | 66% |
| B-stub/causal | 17/22 = 77% [57%-90%] | 6/36 = 17% [8%-32%] | 23/36 = 64% [48%-78%] | 100/107 = 93% [87%-97%] | 42/56 = 75% [62%-84%] | 75% |
| B+-stub/causal | 18/22 = 82% [61%-93%] | 10/36 = 28% [16%-44%] | 27/36 = 75% [59%-86%] | 91/107 = 85% [77%-91%] | 37/56 = 66% [53%-77%] | 66% |
| C | 7/22 = 32% [16%-53%] | 10/36 = 28% [16%-44%] | 16/36 = 44% [30%-60%] | 97/107 = 91% [84%-95%] | 13/56 = 23% [14%-36%] | 23% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | A | B-stub | B+-stub | B-stub/causal | B+-stub/causal | C |
|---|---|---|---|---|---|---|
| explicit_start_end (6) descriptive only | 4/6 | 2/6 | 4/6 | 0/6 | 4/6 | 2/6 | 4/6 | 0/6 | 4/6 | 2/6 | 1/6 | 0/6 |
| explicit_start_implicit_end (6) descriptive only | 5/6 | 1/6 | 5/6 | 0/6 | 5/6 | 1/6 | 5/6 | 0/6 | 5/6 | 1/6 | 3/6 | 0/6 |
| retroactive (6) descriptive only | 3/4 | 1/6 | 3/4 | 0/6 | 4/4 | 1/6 | 3/4 | 0/6 | 4/4 | 1/6 | 1/4 | 3/6 |
| implicit (6) descriptive only | 5/6 | 1/6 | 5/6 | 1/6 | 5/6 | 1/6 | 5/6 | 1/6 | 5/6 | 1/6 | 2/6 | 2/6 |
| false_alarm (6) descriptive only | 0/0 | 3/6 | 0/0 | 3/6 | 0/0 | 3/6 | 0/0 | 3/6 | 0/0 | 3/6 | 0/0 | 3/6 |
| public (6) descriptive only | 0/0 | 2/6 | 0/0 | 2/6 | 0/0 | 2/6 | 0/0 | 2/6 | 0/0 | 2/6 | 0/0 | 2/6 |
| ALL (36) | 17/22 | 10/36 | 17/22 | 6/36 | 18/22 | 10/36 | 17/22 | 6/36 | 18/22 | 10/36 | 7/22 | 10/36 |

**Paired exact McNemar (b = first system has the outcome and second does not; c = the reverse; risk diff = (b - c)/n).**

| first vs second | outcome | n | b | c | both | p | risk diff |
|---|---|---|---|---|---|---|---|
| A vs C | leak | 22 | 10 | 0 | 7 | 0.0020 | +45.5 pts |
| A vs C | leak_or_omit | 36 | 15 | 4 | 12 | 0.0192 | +30.6 pts |
| B-stub vs B+-stub | leak | 22 | 0 | 1 | 17 | 1.0000 | -4.5 pts |
| B-stub vs B+-stub | leak_or_omit | 36 | 0 | 4 | 23 | 0.1250 | -11.1 pts |
| B-stub vs B-stub/causal | leak | 22 | 0 | 0 | 17 | 1.0000 | +0.0 pts |
| B-stub vs B-stub/causal | leak_or_omit | 36 | 0 | 0 | 23 | 1.0000 | +0.0 pts |
| B-stub vs C | leak | 22 | 10 | 0 | 7 | 0.0020 | +45.5 pts |
| B-stub vs C | leak_or_omit | 36 | 11 | 4 | 12 | 0.1185 | +19.4 pts |
| B+-stub vs B+-stub/causal | leak | 22 | 0 | 0 | 18 | 1.0000 | +0.0 pts |
| B+-stub vs B+-stub/causal | leak_or_omit | 36 | 0 | 0 | 27 | 1.0000 | +0.0 pts |
| B+-stub vs C | leak | 22 | 11 | 0 | 7 | 0.0010 | +50.0 pts |
| B+-stub vs C | leak_or_omit | 36 | 15 | 4 | 12 | 0.0192 | +30.6 pts |
| B-stub/causal vs B+-stub/causal | leak | 22 | 0 | 1 | 17 | 1.0000 | -4.5 pts |
| B-stub/causal vs B+-stub/causal | leak_or_omit | 36 | 0 | 4 | 23 | 0.1250 | -11.1 pts |
| B-stub/causal vs C | leak | 22 | 10 | 0 | 7 | 0.0020 | +45.5 pts |
| B-stub/causal vs C | leak_or_omit | 36 | 11 | 4 | 12 | 0.1185 | +19.4 pts |
| B+-stub/causal vs C | leak | 22 | 11 | 0 | 7 | 0.0010 | +50.0 pts |
| B+-stub/causal vs C | leak_or_omit | 36 | 15 | 4 | 12 | 0.0192 | +30.6 pts |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | scope: 31, confirm: 5, retro: 4, cue: 3 |
| private_leaked | hold_elapsed: 13 |
| public_lost | scope: 12, cue: 6, confirm: 2, retro: 1 |

_n=36 synthetic items written by the team that built the systems; early evidence only. -stub systems are heuristic stand-ins, not LLMs. Intervals are Wilson 95%; with this n they are wide._