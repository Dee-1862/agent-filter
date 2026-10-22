**Leak rate (private segments reaching final notes, lower is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 0% | 0% | 28% |
| explicit_start_implicit_end | 0% | 0% | 55% |
| retroactive | 8% | 50% | 17% |
| implicit | 43% | 43% | 52% |
| false_alarm | n/a | n/a | n/a |
| ALL | 14% | 21% | 41% |

**Committed-leak rate (private segments that were ever committed, even if retracted later; shows what the hold buffer buys; lower is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 0% | 0% | 28% |
| explicit_start_implicit_end | 0% | 0% | 55% |
| retroactive | 8% | 50% | 17% |
| implicit | 43% | 43% | 52% |
| false_alarm | n/a | n/a | n/a |
| ALL | 14% | 21% | 41% |

**Over-redaction (public segments missing, lower is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 0% | 11% | 11% |
| explicit_start_implicit_end | 61% | 9% | 0% |
| retroactive | 38% | 8% | 5% |
| implicit | 5% | 5% | 5% |
| false_alarm | 72% | 45% | 34% |
| ALL | 38% | 18% | 13% |

**Summary usefulness (public facts present, higher is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 100% | 90% | 90% |
| explicit_start_implicit_end | 52% | 97% | 100% |
| retroactive | 66% | 91% | 94% |
| implicit | 94% | 94% | 94% |
| false_alarm | 31% | 56% | 69% |
| ALL | 68% | 85% | 89% |

**Item-level leak rate (items with any leak / items with private content)**

| system | item leak |
|---|---|
| A | 22% |
| B-stub | 31% |
| C | 59% |

_n=40 synthetic items; early evidence only. B-stub is a heuristic stand-in, not an LLM._