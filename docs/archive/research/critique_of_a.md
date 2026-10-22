# Critique of draft A (by Researcher B, round 2)

Method: re-opened sources myself. PDFs were text-extracted with `pdftotext` (both `-layout` and `-raw`); arXiv/HTML/model-card pages were fetched. Verdicts: **confirmed**, **wrong**, **overclaim** (true core, unsupported extension), **unverifiable** (I could not check).

## Summary table

| # | A's claim | Verdict |
|---|---|---|
| 1 | 39%/57% is the meeting-SUMMARY "Leaks Secret" rate (ConfAIde Table 4); action items are 0.29/0.38 | **Confirmed. B's round-1 reading was wrong.** |
| 2 | CoT does not help (Table 5: 0.39->0.40, 0.57->0.61) | **Confirmed for the 2023 models tested; superseded by 2025 work** (see 1-2-3 Check). A states it as current fact in P1 and top-5 #2. |
| 3 | PrivacyLens: 25.68/38.69 are LRh; basic prompt GPT-4 is 27.23 | **Confirmed** (clean `-raw` table); raw LR 24.54 / 39.15 also confirmed |
| 4 | Per-track identity / dropping a track gives "exact zero leak by construction" | **Overclaim** |
| 5 | OrthoGrad Whisper-Tiny WER 11.08 -> 13.98 | **Confirmed** (Table 2) |
| 6 | Whisper hallucination about 1% of transcriptions, 38% of those harmful | **Confirmed** (abstract); A's "silence/non-vocal duration" extension is plausible but not re-checked by me |
| 7 | "No prior work on retroactive redaction or off-the-record cue detection" | **Wrong as stated** (patents and one benchmark found); true only for published evaluations of the speech case |
| 8 | Streaming Sortformer numbers (RTF 0.093 / 0.180; 4-speaker limit; latencies 0.32-1.04 s) | **Confirmed**; A did not extract DER (B did) |
| 9 | pyannote 4 / community-1 claims | **Partly confirmed**: model exists and is modestly better than 3.1; not a streaming model. A's own tag (secondhand) was honest |
| 10 | SimulStreaming Table 7 numbers | **Confirmed** |
| 11 | Kolmogorov Law/Pollfish survey numbers | **Confirmed** |
| 12 | CI-Work is arXiv 2604.21308, abstract numbers | **Confirmed** (also ACL 2026 Industry Track, pp. 1483-1508) |
| 13 | 1-2-3 Check "IASEAI'26"; "18% / 19%" absolute or relative unknown | **Unverifiable venue**; 18% is **absolute points** (23.0 -> 5.0, Table 2, GPT-4o, three agents Annotate Private) |
| 14 | CI-RL "up to 40%" and ConfAIde Table 5 (Tier 1-2) | **Unverifiable** by me; the PrivacyLens table does not show a clean 40% row |

## Details

### 1. ConfAIde Table 4 (the disputed one): A is right, B was wrong
- Source: https://arxiv.org/pdf/2310.17884, Table 4 and Sec. 4.4, extracted with `pdftotext -raw`.
- Exact rows: header `Act. Item` followed by `Leaks Secret (Worst Case) 0.80 0.85 0.75 0.85 0.90 0.75`, `Leaks Secret 0.29 0.38 0.28 0.54 0.43 0.21`, `Omits Public Information 0.76 0.89 ...`, `Leaks Secret or Omits Info. 0.89 0.96 ...`; then header `Summary` followed by `Leaks Secret (Worst Case) 0.80 0.85 0.55 0.70 0.85 0.75`, **`Leaks Secret 0.39 0.57 0.09 0.28 0.35 0.21`**, `Omits Public Information 0.10 0.27 0.64 0.42 0.73 0.77`, `Leaks Secret or Omits Info. 0.42 0.74 0.68 0.65 0.92 0.87`. Columns: GPT-4, ChatGPT, InstructGPT, Mixtral, Llama2 Chat, Llama 2.
- Independent text check (Sec. 4.4): "This leakage is higher in the meeting summary task compared to the personal action item generation task." 0.39 > 0.29, so 0.39 belongs to summaries. Table 5 (Tier 4, w/o CoT 0.39 / 0.57 / 0.10 / 0.27 / 0.42 / 0.74) matches the Summary block.
- Why B erred: with `-layout`, the "Summary / Act. Item" labels floated to different lines than the numeric blocks and I assigned them in the wrong order. A used the prose to disambiguate (as A said) and got it right. B's round-1 follow-on claims (omission and composite numbers per task) were also swapped and are fixed in draft_b.md.
- What A's reading adds that B should keep: the privacy-protecting instruction was already in the prompt (Introduction: "even though they are directly instructed to preserve privacy").

### 2. CoT claim: confirmed as history, stale as guidance
- Table 5 values are as A quotes. But 1-2-3 Check (https://arxiv.org/html/2508.07667, Table 2, GPT-4o) reports single agent 23.0% leak vs single agent + CoT **2.0%** leak (omit-public 12.0% -> 32.5%). So "do not rely on a longer prompt" (A, P1 design implication and top-5 #2) rests on a 2023 result and is contradicted for GPT-4o by a 2026 paper. The accurate statement: CoT lowers leak sharply on newer models but at a large conveyance cost. A did cite 1-2-3 Check (P4) but did not reconcile it with P1.

### 3. PrivacyLens
- https://arxiv.org/pdf/2409.00138 Table 2 via `pdftotext -raw`: `GPT-4 97.57 26.37 27.23 2.60 98.99 24.54 25.68 2.61` (basic-prompt probing, LR, LRh, helpfulness; then privacy-enhancing probing, LR, LRh, helpfulness) and `Llama-3-70B-Instruct 94.32 36.51 38.04 2.53 98.58 39.15 38.69 2.54`. So A's 27.23 (basic LRh), 25.68 (enhanced LRh), 24.54 and 39.15 (raw LR) are all right. A flagged these as probable because of its garbled `-layout` extraction; the `-raw` extraction removes the doubt.
- A's "1,479 probing questions" and "493 seeds" are consistent with the paper's 493 seeds (3 probing questions per trajectory); I did not locate the 1,479 literal.

### 4. "Dropping the track gives exact zero leak by construction" (A, P17 and top-5 #3): overclaim
- True core: if a participant's own audio stream is never transcribed, none of that stream's words enter the pipeline.
- Not covered: (a) other participants repeating or paraphrasing the opted-out person; (b) acoustic bleed of that person into other microphones or the room (A mentions bleed only for diarization, P16); (c) content already in the hold buffer before the opt-out; (d) the opt-out being announced mid-meeting; (e) the stated threat model is "words spoken by the opted-out speaker", not "information about them". The claim should read "zero leak of that speaker's own track after the drop", and the benchmark should still contain cases (a)-(c). No source supports "zero by construction"; it is an engineering argument, not a finding.
- The related claim that OrthoGrad shows unlearning is the wrong tool for runtime consent is reasonable and supported (OrthoGrad Table 2: test WER 11.08 -> 13.98, Whisper-Tiny, speaker in training data).

### 5. OrthoGrad
- https://arxiv.org/pdf/2503.02312 Table 2: `Original 9.99 / 11.12 / 10.06 / 11.08`, `OrthoGrad 12.11 / 96.24 / 98.53 / 13.98` (Wretain / Wunlearn / Wspeaker / Wtest), mean over 5 speakers, WER clipped at 100. Matches A. A's description "ASR speaker-unlearning benchmark" is fair; setup is Whisper-Tiny + LibriSpeech with LoRA.

### 6. Whisper hallucination
- https://arxiv.org/abs/2402.08021 abstract: "roughly 1% of audio transcriptions contained entire hallucinated phrases or sentences" and "38% of hallucinations include explicit harms". A's wording "38% of those harmful" is right.
- A's inference that OFF-state silence could provoke hallucination: the abstract links hallucinations to speakers with longer non-vocal durations (A's reading); the inference to our muted-track design is A's, plausible but untested. Good design advice (VAD gating), not a result.

### 7. "No prior work on retroactive redaction or off-the-record cue detection": wrong as stated
Counterexamples found with new searches:
- **Zoom patent US 11,974,074 B2**, *Providing off-the-record functionality during virtual meetings* (filed Apr 29 2022, granted Apr 30 2024; inventors Shane P. Springer, Alexander Waibel): https://patents.google.com/patent/US11974074B2/en. Description/examples (I read the first ~100k of ~231k characters; not the formal claims) include: off-the-record period with start/end; host approve/deny/limit; **retroactive erasing of earlier streams from the recording** (Example 4) with a quick-replay prompt (Example 19); and **identifying keywords such as "off-the-record" from the audio stream via speech recognition** (Examples 10-11). A continuation US 12,587,614 exists (search result only).
- Amazon-style "Privacy mode based on speaker identifier" patents (e.g. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12243532): per search-result text, retroactive privacy of the last utterance with server-side deletion. Scanned PDFs, unreadable by me; secondhand.
- **Bemula**, *Can Agents Forget When Asked? A Benchmark for Memory Unlearning in LLM Agents*, arXiv:2610.18052 (13 Oct 2026), https://arxiv.org/abs/2610.18052: 135 forget requests in 50 dialogues; "no system passed more than 1.5% of forget requests end to end". Text, not speech, but a directly relevant evaluation of "forget what I said" that A's gap list (Section 7) and "Gap" paragraph (Section 5) miss.
- What survives of A's claim: I found no *published evaluation* (benchmark, leak metric) of spoken privacy cues, scope or retroactive requests in streaming meeting transcription. The correct novelty statement is "evaluation and the combination with implicit sensitivity and scope-end detection", not "the idea". A's Section 7 items 1 and 3 should be reworded accordingly.

### 8. Streaming Sortformer
- https://arxiv.org/html/2507.18446: Table 2 RTF 0.005 (10 s), 0.093 (1.04 s), 0.180 (0.32 s); max four speakers "by design". A is right. A did not extract DER; B did (DIHARD III all: 19.02 / 18.97 / 19.32 at 10 s / 1.04 s / 0.32 s with post-processing). B's own round-1 CALLHOME "all" values were wrong (4-speaker column) and are corrected in draft_b.md: 10.09 / 10.79 / 11.50. A's "RTX 6000 Ada GPU" hardware detail I did not re-check.

### 9. pyannote 4.0 / community-1
- https://huggingface.co/pyannote/speaker-diarization-community-1 model card: DER (no collar, overlap kept) 3.1 -> community-1 -> precision-2: AMI IHM 18.8 -> 17.0 -> 12.9; DIHARD 3 21.4 -> 20.2 -> 14.7; AMI SDM 22.7 -> 19.9 -> 15.6; VoxConverse 11.2 -> 11.2 -> 8.5; CC-BY-4.0, gated; no streaming mode described. A's wording "pyannote 4 / community-1 claims (only a vendor page seen via search)" was cautious and fine; any suggestion it is usable for the live path would be wrong.

### 10. SimulStreaming Table 7
- https://arxiv.org/pdf/2506.17077 Table 7 (English ACL6060 dev): chunk 0.05 s -> WER 14.22, latency 494 ms; 0.25 -> 13.10 / 754; 0.5 (frame 20) -> 13.06 / 1262; 2.0 -> 12.69 / 2143. A is right. Computation-unaware latency, as A notes.

### 11-12. Survey and CI-Work
- Kolmogorov Law / Pollfish (https://krdo.com/stacker-business-economy/2026/07/16/ai-notetakers-have-sat-in-on-1-in-3-us-workers-meetings-but-only-a-third-say-they-were-asked-first/): n = 500, fielded July 8, 2026; 33.4% notetaker present; of 167 exposed, 34.7% always asked, 36.5% sometimes, 25.1% never, 3.6% afterward; margin +/-4.4% and about +/-7.6%. Matches A exactly. This corrects B's round-1 "no survey found". Note it does not show "most are not asked": about 35% were always asked.
- CI-Work: arXiv 2604.21308v1 (23 Apr 2026) exists and the abstract quotes match; ACL 2026 Industry Track version confirmed by B (https://aclanthology.org/2026.acl-industry.103.pdf). A had both unopened; B opened them. A's note "Table 2 GPT-5 defence results" is not in A; B has them (prompt defence leaves violation rate above 20%).

### 13-14. Unverifiable
- 1-2-3 Check venue "IASEAI'26": the arXiv page I opened (v3, 25 Feb 2026) names no venue.
- CI-RL "up to 40%": the PrivacyLens table I read has no single 40% row (closest Qwen2.5-14B 52.9 -> 33.9, about 36% relative). A's Table 5 (ConfAIde Tier 1-2) was beyond the part I read.
- Dou et al. (arXiv 2311.09538), DiariZen (2409.09408), NOTSOFAR-1 (2501.17304), DSM-ASR (2509.08753), WhisperRT (2508.12301), DialogPII, Beyond Clean Text, TruS, UnSLU-BENCH: not re-opened; treat A's tags as stated.

## Other criticisms of A

1. **Internal inconsistency:** P1 says CoT hurts and top-5 #2 says avoid long CoT, while P4 (1-2-3 Check) shows CoT cutting GPT-4o leakage to 2.0%. Needs one reconciled statement including the omit penalty.
2. **Baseline strength not addressed:** A treats "structure vs one prompt" as the PRD's question but never asks whether B is a strawman (B's main objection). A's top-5 has no stronger prompting baseline and no hindsight-vs-causal control.
3. **No statistics for 40 items:** A's methodology sections list metrics but give no interval method, power, or clustering; with 40 items and a 5 x 4 factorial Tier 4, this is the largest gap in A for the stated goal.
4. **Tier 4 items called "implicit"?** A does not notice that Tier 4 secrets are announced as confidential within the dialogue (explicit-in-context), so using them as the "implicit" class is questionable.
5. **Strengths worth keeping (absorbed into draft_b.md):** VAD gating before ASR and cue matching on the hypothesis stream; OTR-Bench-ASR via TTS then Whisper; per-stage leak logging; speaker/scope ownership as an open question; OrthoGrad and SimulStreaming Table 7 numbers; the Kolmogorov survey; the pyannote model card (B verified).
