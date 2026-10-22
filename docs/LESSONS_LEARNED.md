# Lessons Learned

Append-only. Newest entries at the top. Record what surprised us, what failed, what worked and what we would do differently. Link to the change in [CHANGES.md](CHANGES.md) or the PRD addendum it relates to.

**Entry format**

```
## YYYY-MM-DD · L-### · <short title>
- Area: asr | hold-buffer | cue-detector | state-machine | benchmark | eval | demo | process
- What happened:
- Why it happened (root cause):
- What we do now / next time:
- Related: C-### / A-### / Q-##
```

---

## 2026-10-22 · L-003 · Portfolio alignment does not require a cloud integration
- Area: process
- What happened: Ketch's Permission Vault and enforcement language fit the product, but its public docs describe a server-side platform and hosted API path, with no verified offline local deployment.
- Why it happened (root cause): The project requires meeting content and consent metadata to remain on controlled local machines.
- What we do now / next time: Build a local permission ledger and use Ketch's concepts as an explicitly labeled analogy. Do not present it as an integration or send data to Ketch without a later owner decision.
- Related: C-004 / A-004

## 2026-10-22 · L-002 · Live transcript needs a policy delay
- Area: demo
- What happened: Displaying raw ASR text immediately could reveal HR or other sensitive speech before local checks finish, even if the final notes are later clean.
- Why it happened (root cause): Content classification requires a brief period of processing after speech is captured.
- What we do now / next time: Show recording and processing states immediately; show per-speaker words only after a local policy pass. Measure and disclose the resulting latency. Do not claim that retrospective deletion reverses what viewers already saw.
- Related: C-003 / A-002 / A-003

## 2026-10-22 · L-001 · Verify cited numbers before they reach slides
- Area: process
- What happened: The source plan quotes leak rates from ConfAIde (39% / 57%) and PrivacyLens (25.68% / 38.69%) and legal and survey claims. None were checked when the PRD was written.
- Why it happened: The PRD was built from a pasted plan, not from the primary sources.
- What we do now / next time: Re-check each figure against its paper (and the lawsuit and survey claims against their sources) before they appear in slides. Record the checked value and link in this file.
- Related: C-001
