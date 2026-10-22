### Set `dev`: n = 47 items, 47 clusters, llm = `none`, hold = [30.0] s, md5 `30402121`

**Item-level metrics, ConfAIde Table 4 style (k/n = rate [Wilson 95%]).** Leak = items with a private segment in the notes (over items with private content); Omit-Public = items missing a public segment; Leak-or-Omit = either, over all items; Conveyance = public facts present.

| system | Leak | Omit-Public | Leak-or-Omit | Conveyance | segment leak | committed leak |
|---|---|---|---|---|---|---|
| A | 11/37 = 30% [17%-46%] | 24/47 = 51% [37%-65%] | 33/47 = 70% [56%-81%] | 126/182 = 69% [62%-75%] | 17/82 = 21% [13%-31%] | 21% |
| B-stub | 14/37 = 38% [24%-54%] | 17/47 = 36% [24%-50%] | 29/47 = 62% [47%-74%] | 158/182 = 87% [81%-91%] | 22/82 = 27% [18%-37%] | 27% |
| C | 1/37 = 3% [0%-14%] | 5/47 = 11% [5%-23%] | 6/47 = 13% [6%-25%] | 179/182 = 98% [95%-99%] | 1/82 = 1% [0%-7%] | 1% |

**Per case type: Leak k/n | Omit-Public k/n** (cells with fewer than 10 items are *descriptive only*, no ranking claims)

| case type (n) | A | B-stub | C |
|---|---|---|---|
| explicit_start_end (10) | 2/10 | 0/10 | 2/10 | 2/10 | 0/10 | 0/10 |
| explicit_start_implicit_end (9) descriptive only | 1/9 | 8/9 | 1/9 | 4/9 | 0/9 | 0/9 |
| retroactive (10) | 2/10 | 7/10 | 5/10 | 2/10 | 0/10 | 0/10 |
| implicit (8) descriptive only | 6/8 | 1/8 | 6/8 | 1/8 | 1/8 | 3/8 |
| false_alarm (10) | 0/0 | 8/10 | 0/0 | 8/10 | 0/0 | 2/10 |
| ALL (47) | 11/37 | 24/47 | 14/37 | 17/47 | 1/37 | 5/47 |

**Paired exact McNemar (b = first system has the outcome and second does not; c = the reverse; risk diff = (b - c)/n).**

| first vs second | outcome | n | b | c | both | p | risk diff |
|---|---|---|---|---|---|---|---|
| A vs C | leak | 37 | 11 | 1 | 0 | 0.0063 | +27.0 pts |
| A vs C | leak_or_omit | 47 | 28 | 1 | 5 | 0.0000 | +57.4 pts |
| B-stub vs C | leak | 37 | 14 | 1 | 0 | 0.0010 | +35.1 pts |
| B-stub vs C | leak_or_omit | 47 | 24 | 1 | 5 | 0.0000 | +48.9 pts |

**Per-stage log for C** (stage = prefix of the pipeline audit reason; read-only from `Pipeline.audit_log()`)

| outcome | stage counts |
|---|---|
| private_blocked | scope: 56, confirm: 14, retro: 8, cue: 3 |
| private_leaked | hold_elapsed: 1 |
| public_lost | scope: 5, cue: 2, retro: 1 |

_n=47 synthetic items written by the team that built the systems; early evidence only. -stub systems are heuristic stand-ins, not LLMs. Intervals are Wilson 95%; with this n they are wide._