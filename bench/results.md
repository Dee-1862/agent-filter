**Leak rate (private segments reaching final notes, lower is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 13% | 13% | 0% |
| explicit_start_implicit_end | 13% | 13% | 0% |
| retroactive | 13% | 47% | 0% |
| implicit | 43% | 43% | 5% |
| false_alarm | n/a | n/a | n/a |
| ALL | 21% | 27% | 1% |

**Committed-leak rate (private segments that were ever committed, even if retracted later; shows what the hold buffer buys; lower is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 13% | 13% | 0% |
| explicit_start_implicit_end | 13% | 13% | 0% |
| retroactive | 13% | 47% | 0% |
| implicit | 43% | 43% | 5% |
| false_alarm | n/a | n/a | n/a |
| ALL | 21% | 27% | 1% |

**Over-redaction (public segments missing, lower is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 0% | 9% | 0% |
| explicit_start_implicit_end | 55% | 8% | 0% |
| retroactive | 34% | 6% | 0% |
| implicit | 5% | 5% | 7% |
| false_alarm | 70% | 42% | 6% |
| ALL | 37% | 17% | 3% |

**Summary usefulness (public facts present, higher is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 100% | 91% | 100% |
| explicit_start_implicit_end | 57% | 97% | 100% |
| retroactive | 68% | 92% | 100% |
| implicit | 94% | 94% | 94% |
| false_alarm | 35% | 62% | 98% |
| ALL | 69% | 87% | 98% |

**Item-level leak rate (items with any leak / items with private content)**

| system | item leak |
|---|---|
| A | 30% |
| B-stub | 38% |
| C | 3% |

_n=47 synthetic items; early evidence only. B-stub is a heuristic stand-in, not an LLM._