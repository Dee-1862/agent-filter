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

## 2026-10-22 · L-014 · Renumbering after a merge left stale cross-references
- Area: process
- What happened: After the merge with Lance's branch the Docs Keeper's C-/L-numbers shifted (C-003..C-006 became C-008..C-011), but the "Related:" lines in L-005..L-008 still pointed at the old numbers. Two PRD addenda are also titled A-001.
- Why it happened (root cause): IDs were renumbered in headings only.
- What we do now / next time: when IDs are renumbered, grep every `C-0`, `L-0`, `A-0` reference. Fixed in this pass. Do not renumber the duplicate A-001; continue at A-007.
- Related: C-017

## 2026-10-22 · L-013 · Two sides rewrote demo/server.py in parallel
- Area: process
- What happened: The runtime/demo agent refactored `demo/server.py` around `StreamRunner` while Lance's branch added per-person consent in `demo/live_session.py`. The result is two `--source` modes (`livekit`, `livekit-stream`) that are not one design (C-013).
- Why it happened (root cause): both sides edited the same entry point; the "touch only owned files" rule was not enforced.
- What we do now / next time: one owner per file; for shared entry points, agree a short written interface first. Reconciliation is still open.
- Related: C-013, WORK_SPLIT rule 5

## 2026-10-22 · L-012 · A heredoc halved backslashes and corrupted a regex
- Area: process
- What happened: A regex written through a shell heredoc lost half its backslashes and silently matched the wrong text.
- Why it happened (root cause): shell expansion of backslashes in an unquoted heredoc.
- What we do now / next time: write code with the file tools, or quote the heredoc delimiter, and unit-test cue regexes.
- Related: C-012
- Note: reported by the coordinator, not observed by the Docs Keeper.

## 2026-10-22 · L-011 · `/tmp` differs between Git Bash and Windows Python
- Area: process
- What happened: In pass 1 a file written to `/tmp/ch.txt` from Git Bash was not found by Python (`FileNotFoundError: [Errno 2] No such file or directory: '/tmp/ch.txt'`). It worked after passing `$(cygpath -w /tmp/ch.txt)`.
- Why it happened (root cause): Git Bash maps `/tmp` into its own tree; native Windows Python does not see it.
- What we do now / next time: use a real Windows path (the scratchpad) or `cygpath -w` when a shell and Python share a file.
- Related: C-017

## 2026-10-22 · L-010 · Literature numbers meant something different from what the PRD assumed
- Area: process
- What happened: `docs/RESEARCH.md` section 1 item 6 finds that ConfAIde 39%/57% is the Tier 4 meeting-summary "Leaks Secret" rate (action items are 29%/38%), that PrivacyLens 25.68%/38.69% is the helpfulness-adjusted rate, and that the survey gives 34.7% always asked, 36.5% sometimes, 25.1% never, 3.6% found out afterward (n=167, law-firm-commissioned), not "most people aren't asked". The coordinator reports the summary-vs-action-item ambiguity was settled by reading the paper's table image.
- Why it happened (root cause): see L-001; the figures came from a pasted plan.
- What we do now / next time: use the corrected wording (A-007) before any slide; keep L-001 open until a second person re-checks each figure.
- Related: L-001, A-007, C-015

## 2026-10-22 · L-009 · Tuned-on-dev numbers are not a result: 1% leak on dev vs 53% on a fresh check
- Area: eval
- What happened: After the engine hardening C leaks 1% on the 47-item set (`bench/results.md`, 13:00). `bench/README.md` states the cue heuristics were developed while reading those items, and that a separate 9-item check written afterwards (not committed) gave C a 53% leak, equal to A's 53%, before the gaps it exposed were fixed.
- Why it happened (root cause): the benchmark authors and the rule authors are the same people, and the rules were written while reading the items.
- What we do now / next time: never report dev-set numbers as the finding. Write and freeze a held-out set before tuning, commit it, and report both. Until then every number in PRD 2.5 carries "dev-set tuned, synthetic, no LLM". The 9-item check is not in the repo, so its numbers cannot be audited.
- Related: L-005, C-012, R-003

## 2026-10-22 · L-008 · Imported symbol removed by a refactor breaks a sibling-owned test
- Area: process
- What happened: `demo/server.py` was refactored (`parse_script` replaced by `load_script_segments`) while `tests/test_demo.py` still does `from demo.server import create_app, parse_script`. `OTR_NO_PRESIDIO=1 python -m pytest tests -q` then errored at collection (seen at 12:41 and 12:42), hiding all 33 tests behind one error.
- Why it happened (root cause): the test file is owned by Person 1 but was not updated in the same change; one collection error aborts the whole run.
- What we do now / next time: when removing or renaming a public name, grep `tests/` in the same change. Run `pytest --ignore` or `--continue-on-collection-errors` when judging other areas.
- Related: C-008, I5

## 2026-10-22 · L-007 · A bench test failed only while a sibling agent was mid-write
- Area: process
- What happened: Per the Docs Keeper brief, a bench test failed during parallel editing and passed on rerun. In this pass the engine files (`otr/cue_detector.py` at 12:32 and again 12:41) changed during the session, so a single test run is a snapshot, not a verdict.
- Why it happened (root cause): several agents edit one working tree with no isolation.
- What we do now / next time: record the timestamp with every test result; rerun once before reporting a failure; prefer separate branches or worktrees (WORK_SPLIT rule 5).
- Related: C-010
- Note: the original failing test was reported to the Docs Keeper, not observed by it; the cue_detector timestamps are observed.

## 2026-10-22 · L-006 · Blanket `taskkill /IM python.exe` risks killing other agents' runs
- Area: process
- What happened: A demo/runtime agent was reported to have used `taskkill /IM python.exe` to stop its server, which would also kill every other agent's pytest or eval process on the machine.
- Why it happened (root cause): stopping a server by image name instead of by PID or port.
- What we do now / next time: stop only the PID you started (record it, or find it by listening port). Never kill by image name on a shared machine.
- Related: C-008
- Note: reported, not observed by the Docs Keeper.

## 2026-10-22 · L-005 · First eval: structure leaked more than rules, until heuristics are fixed
- Area: eval
- What happened: First run (`bench/results.md`, 12:32, 40 synthetic items, no LLM): C leaked 45% vs A 14% and B-stub 21%; item-level 72% vs 22% / 31%. C over-redacted least (12% vs 38% / 18%). Hold sweep gave identical numbers at 0 s and 30 s (`bench/results_sweep.md`).
- Why it happened (root cause): hypothesised in WORK_SPLIT I1/I2 (implicit-end heuristic closes scope early; harness ticks only at segment starts). Not yet confirmed by a fix and rerun.
- What we do now / next time: do not quote these numbers as a result; fix I1, rerun, and log every run in PRD 2.5. Also note the A and B-stub systems are cheap keyword heuristics, so a small benchmark written by the same team can favour them.
- Related: C-009, I1, I2

## 2026-10-22 · L-004 · Hold full utterances before shared text
- Area: asr
- What happened: The initial streaming chunker emitted confirmed word prefixes before an utterance ended. A later sensitive phrase could change the meaning of an earlier prefix already eligible for display.
- Why it happened (root cause): Transcription confidence and privacy approval are different decisions.
- What we do now / next time: Live capture emits text only when an utterance closes, then waits for local policy and the hold timer. Test long uninterrupted speech separately because the chunker still closes at 20 seconds.
- Related: C-007 / A-002 / A-003

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
