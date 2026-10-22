### Set `heldout`: n = 36 items, 35 clusters, llm = `none`, hold = [30.0] s, md5 `001cbad4`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| A | 17/22 = 77% [57%-90%] | 14/36 = 39% [25%-55%] | 30/36 = 83% [68%-92%] | 79/107 = 74% [65%-81%] | 41/56 = 73% [60%-83%] | 73% |
| B-stub | 17/22 = 77% [57%-90%] | 10/36 = 28% [16%-44%] | 26/36 = 72% [56%-84%] | 93/107 = 87% [79%-92%] | 42/56 = 75% [62%-84%] | 75% |
| B+-stub | 18/22 = 82% [61%-93%] | 14/36 = 39% [25%-55%] | 30/36 = 83% [68%-92%] | 82/107 = 77% [68%-84%] | 37/56 = 66% [53%-77%] | 66% |
| B-stub/causal | 17/22 = 77% [57%-90%] | 10/36 = 28% [16%-44%] | 26/36 = 72% [56%-84%] | 93/107 = 87% [79%-92%] | 42/56 = 75% [62%-84%] | 75% |
| B+-stub/causal | 18/22 = 82% [61%-93%] | 14/36 = 39% [25%-55%] | 30/36 = 83% [68%-92%] | 82/107 = 77% [68%-84%] | 37/56 = 66% [53%-77%] | 66% |
| C | 5/22 = 23% [10%-43%] | 9/36 = 25% [14%-41%] | 13/36 = 36% [22%-52%] | 98/107 = 92% [85%-96%] | 9/56 = 16% [9%-28%] | 16% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | A | B-stub | B+-stub | B-stub/causal | B+-stub/causal | C |
|---|---|---|---|---|---|---|
| explicit_start_end (6) descriptive only | 4/6 | 2/6 | 4/6 | 0/6 | 4/6 | 2/6 | 4/6 | 0/6 | 4/6 | 2/6 | 0/6 | 0/6 |
| explicit_start_implicit_end (6) descriptive only | 5/6 | 1/6 | 5/6 | 0/6 | 5/6 | 1/6 | 5/6 | 0/6 | 5/6 | 1/6 | 2/6 | 0/6 |
| retroactive (6) descriptive only | 3/4 | 3/6 | 3/4 | 2/6 | 4/4 | 3/6 | 3/4 | 2/6 | 4/4 | 3/6 | 1/4 | 3/6 |
| implicit (6) descriptive only | 5/6 | 1/6 | 5/6 | 1/6 | 5/6 | 1/6 | 5/6 | 1/6 | 5/6 | 1/6 | 2/6 | 2/6 |
| false_alarm (6) descriptive only | 0/0 | 5/6 | 0/0 | 5/6 | 0/0 | 5/6 | 0/0 | 5/6 | 0/0 | 5/6 | 0/0 | 2/6 |
| public (6) descriptive only | 0/0 | 2/6 | 0/0 | 2/6 | 0/0 | 2/6 | 0/0 | 2/6 | 0/0 | 2/6 | 0/0 | 2/6 |
| ALL (36) | 17/22 | 14/36 | 17/22 | 10/36 | 18/22 | 14/36 | 17/22 | 10/36 | 18/22 | 14/36 | 5/22 | 9/36 |

**Paired exact McNemar (b = first system has the outcome and second does not; c = the reverse; risk diff = (b - c)/n).**

| first vs second | outcome | n | b | c | both | p | risk diff |
|---|---|---|---|---|---|---|---|
| A vs C | leak | 22 | 12 | 0 | 5 | 0.0005 | +54.5 pts |
| A vs C | leak_or_omit | 36 | 18 | 1 | 12 | 0.0001 | +47.2 pts |
| B-stub vs B+-stub | leak | 22 | 0 | 1 | 17 | 1.0000 | -4.5 pts |
| B-stub vs B+-stub | leak_or_omit | 36 | 0 | 4 | 26 | 0.1250 | -11.1 pts |
| B-stub vs B-stub/causal | leak | 22 | 0 | 0 | 17 | 1.0000 | +0.0 pts |
| B-stub vs B-stub/causal | leak_or_omit | 36 | 0 | 0 | 26 | 1.0000 | +0.0 pts |
| B-stub vs C | leak | 22 | 12 | 0 | 5 | 0.0005 | +54.5 pts |
| B-stub vs C | leak_or_omit | 36 | 14 | 1 | 12 | 0.0010 | +36.1 pts |
| B+-stub vs B+-stub/causal | leak | 22 | 0 | 0 | 18 | 1.0000 | +0.0 pts |
| B+-stub vs B+-stub/causal | leak_or_omit | 36 | 0 | 0 | 30 | 1.0000 | +0.0 pts |
| B+-stub vs C | leak | 22 | 13 | 0 | 5 | 0.0002 | +59.1 pts |
| B+-stub vs C | leak_or_omit | 36 | 18 | 1 | 12 | 0.0001 | +47.2 pts |
| B-stub/causal vs B+-stub/causal | leak | 22 | 0 | 1 | 17 | 1.0000 | -4.5 pts |
| B-stub/causal vs B+-stub/causal | leak_or_omit | 36 | 0 | 4 | 26 | 0.1250 | -11.1 pts |
| B-stub/causal vs C | leak | 22 | 12 | 0 | 5 | 0.0005 | +54.5 pts |
| B-stub/causal vs C | leak_or_omit | 36 | 14 | 1 | 12 | 0.0010 | +36.1 pts |
| B+-stub/causal vs C | leak | 22 | 13 | 0 | 5 | 0.0002 | +59.1 pts |
| B+-stub/causal vs C | leak_or_omit | 36 | 18 | 1 | 12 | 0.0001 | +47.2 pts |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | scope: 36, confirm: 4, retro: 4, cue: 3 |
| private_leaked | hold_elapsed: 9 |
| public_lost | scope: 10, cue: 4, confirm: 2, retro: 1 |

_n=36 synthetic items written by the team that built the systems; early evidence only. -stub systems are heuristic stand-ins, not LLMs. Intervals are Wilson 95%; with this n they are wide._