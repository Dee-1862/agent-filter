**Leak rate (private segments reaching notes, lower is better)**

| case type | C@hold=0s | C@hold=30s |
|---|---|---|
| explicit_start_end | 28% | 28% |
| explicit_start_implicit_end | 50% | 50% |
| retroactive | 50% | 50% |
| implicit | 52% | 52% |
| false_alarm | n/a | n/a |
| ALL | 45% | 45% |

**Over-redaction (public segments missing, lower is better)**

| case type | C@hold=0s | C@hold=30s |
|---|---|---|
| explicit_start_end | 4% | 4% |
| explicit_start_implicit_end | 0% | 0% |
| retroactive | 2% | 2% |
| implicit | 7% | 7% |
| false_alarm | 34% | 34% |
| ALL | 12% | 12% |

**Summary usefulness (public facts present, higher is better)**

| case type | C@hold=0s | C@hold=30s |
|---|---|---|
| explicit_start_end | 97% | 97% |
| explicit_start_implicit_end | 100% | 100% |
| retroactive | 97% | 97% |
| implicit | 91% | 91% |
| false_alarm | 69% | 69% |
| ALL | 90% | 90% |

**Item-level leak rate (items with any leak / items with private content)**

| system | item leak |
|---|---|
| C@hold=0s | 72% |
| C@hold=30s | 72% |

_n=40 synthetic items; early evidence only. B-stub is a heuristic stand-in, not an LLM._