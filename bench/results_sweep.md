**Leak rate (private segments reaching final notes, lower is better)**

| case type | C@hold=0s | C@hold=5s | C@hold=15s | C@hold=30s | C@hold=60s |
|---|---|---|---|---|---|
| explicit_start_end | 0% | 0% | 0% | 0% | 0% |
| explicit_start_implicit_end | 0% | 0% | 0% | 0% | 0% |
| retroactive | 0% | 0% | 0% | 0% | 0% |
| implicit | 5% | 5% | 5% | 5% | 5% |
| false_alarm | n/a | n/a | n/a | n/a | n/a |
| ALL | 1% | 1% | 1% | 1% | 1% |

**Committed-leak rate (private segments that were ever committed, even if retracted later; shows what the hold buffer buys; lower is better)**

| case type | C@hold=0s | C@hold=5s | C@hold=15s | C@hold=30s | C@hold=60s |
|---|---|---|---|---|---|
| explicit_start_end | 0% | 0% | 0% | 0% | 0% |
| explicit_start_implicit_end | 0% | 0% | 0% | 0% | 0% |
| retroactive | 53% | 47% | 0% | 0% | 0% |
| implicit | 5% | 5% | 5% | 5% | 5% |
| false_alarm | n/a | n/a | n/a | n/a | n/a |
| ALL | 11% | 10% | 1% | 1% | 1% |

**Over-redaction (public segments missing, lower is better)**

| case type | C@hold=0s | C@hold=5s | C@hold=15s | C@hold=30s | C@hold=60s |
|---|---|---|---|---|---|
| explicit_start_end | 0% | 0% | 0% | 0% | 0% |
| explicit_start_implicit_end | 0% | 0% | 0% | 0% | 0% |
| retroactive | 0% | 0% | 0% | 0% | 0% |
| implicit | 7% | 7% | 7% | 7% | 7% |
| false_alarm | 6% | 6% | 6% | 6% | 6% |
| ALL | 3% | 3% | 3% | 3% | 3% |

**Summary usefulness (public facts present, higher is better)**

| case type | C@hold=0s | C@hold=5s | C@hold=15s | C@hold=30s | C@hold=60s |
|---|---|---|---|---|---|
| explicit_start_end | 100% | 100% | 100% | 100% | 100% |
| explicit_start_implicit_end | 100% | 100% | 100% | 100% | 100% |
| retroactive | 100% | 100% | 100% | 100% | 100% |
| implicit | 94% | 94% | 94% | 94% | 94% |
| false_alarm | 98% | 98% | 98% | 98% | 98% |
| ALL | 98% | 98% | 98% | 98% | 98% |

**Item-level leak rate (items with any leak / items with private content)**

| system | item leak |
|---|---|
| C@hold=0s | 3% |
| C@hold=5s | 3% |
| C@hold=15s | 3% |
| C@hold=30s | 3% |
| C@hold=60s | 3% |

_n=47 synthetic items; early evidence only. B-stub is a heuristic stand-in, not an LLM._