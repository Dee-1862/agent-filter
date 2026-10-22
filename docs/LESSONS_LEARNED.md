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

## 2026-10-22 · L-001 · Verify cited numbers before they reach slides
- Area: process
- What happened: The source plan quotes leak rates from ConfAIde (39% / 57%) and PrivacyLens (25.68% / 38.69%) and legal and survey claims. None were checked when the PRD was written.
- Why it happened: The PRD was built from a pasted plan, not from the primary sources.
- What we do now / next time: Re-check each figure against its paper (and the lawsuit and survey claims against their sources) before they appear in slides. Record the checked value and link in this file.
- Related: C-001
