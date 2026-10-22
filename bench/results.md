**Leak rate (private segments reaching notes, lower is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 0% | 0% | 28% |
| explicit_start_implicit_end | 0% | 0% | 50% |
| retroactive | 8% | 50% | 50% |
| implicit | 43% | 43% | 52% |
| false_alarm | n/a | n/a | n/a |
| ALL | 14% | 21% | 45% |

**Over-redaction (public segments missing, lower is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 0% | 11% | 4% |
| explicit_start_implicit_end | 61% | 9% | 0% |
| retroactive | 38% | 8% | 2% |
| implicit | 5% | 5% | 7% |
| false_alarm | 72% | 45% | 34% |
| ALL | 38% | 18% | 12% |

**Summary usefulness (public facts present, higher is better)**

| case type | A | B-stub | C |
|---|---|---|---|
| explicit_start_end | 100% | 90% | 97% |
| explicit_start_implicit_end | 52% | 97% | 100% |
| retroactive | 66% | 91% | 97% |
| implicit | 94% | 94% | 91% |
| false_alarm | 31% | 56% | 69% |
| ALL | 68% | 85% | 90% |

**Item-level leak rate (items with any leak / items with private content)**

| system | item leak |
|---|---|
| A | 22% |
| B-stub | 31% |
| C | 72% |

_n=40 synthetic items; early evidence only. B-stub is a heuristic stand-in, not an LLM._