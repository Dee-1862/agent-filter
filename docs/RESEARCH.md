# RESEARCH: literature and evidence base for the OTR meeting agent

Status: living document. First edition = merge R-001, 2026-10-22 (judge/editor pass over two adversarial researcher drafts plus two critiques).

## How to update this file

- Part A (Evidence base, sections 2-8) is **corrected in place only with a matching entry in the Update log (section 9)** saying what changed and why. Never silently edit a number.
- New findings go in as new rows/papers plus a dated, **append-only** Update log entry `R-00N`. Do not delete old log entries.
- Every claim carries a confidence tag. Tags are about what the *judge (R-001)* could re-check:
  - **[verified-in-source]** = the judge re-opened the primary source (PDF text layer, arXiv HTML, patent page, article) and saw the value/sentence. Table cells were read from `pdftotext -raw` output or fetched HTML.
  - **[abstract-only]** = only the abstract/landing page was seen by anyone.
  - **[secondhand]** = news, blog, search snippet, OR a primary source that two researchers read but the judge did not re-open. Suffix `(2R)` = two researchers independently report the same value; `(1R)` = one researcher only. This is a deliberate downgrade: `(2R)` is good evidence, but not re-checked by the judge.
- "Our calc" = computed locally (Python/SciPy) on stated counts.
- PRD references: Part 1 (frozen) and 2.5-2.7. PRD open questions Q1-Q9 exist; this file's new questions are numbered **Q10+**.

---

## 1. Bottom line (<=12 lines)

1. **Hypothesis (structure beats prompting) has support, but weaker and more conditional than PRD 1.4 implies.** Supporting: PrivacyLens (prompt barely moves action leakage: GPT-4 LRh 27.23 -> 25.68), CI-Work (GPT-5 prompt defence still >20% violation), AirGapAgent (remove-before-generate beats instruct-the-generator, adversarial setting), PiSAs/MuPPET (architecture helps, LLM judgment is the bottleneck).
2. **Strongest evidence against:** on newer models, CI-style/CoT prompting cuts leakage a lot. 1-2-3 Check (GPT-4o, ConfAIde Tier 4 summaries): single agent 23.0% leak -> 2.0% with CoT, but omitted-public 12.0% -> 32.5% (composite worse, 26.3 -> 34.0). PrivacyChecker (extract-then-judge prompting) cuts PrivacyLens leak 33.06% -> 8.32% (GPT-4o). So a naive one-pass B is a strawman; the test must be **C vs B+ at matched information and delay, judged on leak AND omission**.
3. **A free lunch is not available:** leak-only metrics reward over-redaction. Always report the pair (leak, omit-public) and the composite.
4. **Our local LLM is the weak link.** Qwen2.5-7B leaks 50.3% on PrivacyLens baseline, 33.7% after RL (CI-RL Table 3, 2R). The implicit-class result will be bounded by the local model, not by the state machine.
5. **Novelty (careful wording):** we found **no prior published evaluation** (benchmark, leak metric) of spoken off-the-record cues, scope-end, or retroactive requests in streaming meeting transcription. We do **not** claim no prior work: the Zoom patent US 11,974,074 B2 *claims* keyword-triggered off-the-record requests (dependent claims 10-11, verified) and erasure from a recording (claims 4-5); Amazon "privacy mode" patents describe retroactive utterance deletion (secondhand). Closest published systems: Trustera (live PII redaction), Bemula (text-memory forget requests; best system passes <=1.5%).
6. **Changes to our own claims:** (a) ConfAIde 39%/57% = Tier 4 **meeting-summary** "Leaks Secret", mean of 10 runs, with a privacy instruction already in the prompt (worst case 80/85; leak-or-omit 42/74); action items are 29/38. (b) PrivacyLens 25.68/38.69 = **helpfulness-adjusted (LRh)** under the privacy-enhancing prompt; raw LR 24.54/39.15. (c) The survey does not show "most people aren't asked": 34.7% always asked, 36.5% sometimes, 25.1% never, 3.6% found out afterward (n=167 exposed; law-firm-commissioned). (d) The 20 ConfAIde items are the *whole* Tier 4 (5 secrets x 4 public types), explicit-in-context, not "implicit".
7. **Track-identity opt-out** is a good engineering choice (avoids voiceprints, matches PRD 1.5) but is **not "zero leak by construction"** (paraphrase by others, mic bleed, content already buffered).
8. **With ~40 items** only large effects are detectable (30% vs 10% unpaired needs ~62/arm). Use Wilson intervals, exact McNemar, cluster counts; claim "early evidence" only.

---

## 2. Verified facts table (numbers planned for PRD 1.4 / slides)

"Judge" column: Y = judge re-checked in primary source this pass.

| # | Claim | Exact value | Source + location | Judge | Tag |
|---|---|---|---|---|---|
| F1 | ConfAIde headline | GPT-4 39%, ChatGPT 57% | arXiv 2310.17884 abstract; Intro: "flow information to inappropriate actors 39% and 57% of the time in Tier 4, even though they are directly instructed to preserve privacy" (researcher-quoted Intro; the numbers match Table 4) | Y (table) | [verified-in-source] |
| F2 | Which task is 39/57 | **Summary** block, row "Leaks Secret" = 0.39 / 0.57 (mean of 10 runs) | Table 4, Summary block (printed after the "Act. Item" block in `pdftotext -raw`); Sec. 4.4: "This leakage is higher in the meeting summary task compared to the personal action item generation task." | Y | [verified-in-source] |
| F3 | Action-item block | Leaks Secret 0.29 / 0.38; Omits Public 0.76 / 0.89; Leak-or-Omit 0.89 / 0.96 | Table 4, Act. Item block | Y | [verified-in-source] |
| F4 | Summary block, other rows | Worst case 0.80 / 0.85; Omits Public 0.10 / 0.27; Leak-or-Omit 0.42 / 0.74 (GPT-4 / ChatGPT) | Table 4 | Y | [verified-in-source] |
| F5 | Effect of the privacy instruction (our own extraction) | Without instruction (Table 11 caption: "We are not instructing the models to preserve privacy"), summary Leaks Secret: GPT-4 0.68, ChatGPT 0.66 (worst case 1.00 / 0.95); action items 0.38 / 0.51. With instruction (Table 4): 0.39 / 0.57. So the instruction *does* help (GPT-4 summary 0.68 -> 0.39) but leaves substantial leakage. Column order read from the header row of the extraction; Table 11 is for an alternative scenario set per caption wording, treat as indicative | Table 11 vs Table 4 | Y (text extraction) | [verified-in-source], interpret with care |
| F6 | CoT on ConfAIde (2023 models) | Tier 4 Leaks Secret GPT-4 0.39 -> 0.40, ChatGPT 0.57 -> 0.61 | Table 5; Sec. 4.5 "CoT ... in fact makes leakage more severe" (generic "step by step" prompt, GPT-4/ChatGPT) | partial (Table 5 header seen; values per 2R) | [secondhand (2R)] |
| F7 | Tier 4 size/construction | 20 transcripts, factorial 5 secrets x 4 public-info types; X is the subject of the secret, joins later; neither mentioned again | Sec. 3.4 | Y | [verified-in-source] |
| F8 | String-match miss | 16 of 200 GPT-4 action-item responses leaked but missed by exact match; 0 false positives | App. B.4 | N | [secondhand (2R)] |
| F9 | PrivacyLens headline | GPT-4 25.68%, Llama-3-70B 38.69% | Abstract (lines 34, 126 of PDF text) | Y | [verified-in-source] |
| F10 | PrivacyLens metric identity | **LRh** (helpfulness-adjusted) under privacy-enhancing prompt. GPT-4 row: basic probing 97.57, LR 26.37, LRh 27.23, help 2.60; enhanced probing 98.99, LR 24.54, LRh 25.68, help 2.61. Llama-3-70B: basic 94.32 / 36.51 / 38.04 / 2.53; enhanced 98.58 / 39.15 / 38.69 / 2.54. (First four numbers = basic prompt, last four = privacy-enhancing, consistent with the abstract) | Table 2 | Y | [verified-in-source] |
| F11 | Prompt effect on PrivacyLens | GPT-4 LRh 27.23 -> 25.68 (-1.55); Llama-3-70B 38.04 -> 38.69 (+0.65) | Table 2 | Y | [verified-in-source] |
| F12 | PrivacyLens scale | 493 seeds/vignettes/trajectories | Sec. 3-4 (researchers); 1,479 probing questions not located by anyone | N | [secondhand (2R)] for 493; 1,479 unverified |
| F13 | PrivacyLens judge validation | Few-shot Mistral-7B leak judge, 153 pairs from 50 actions, Fleiss kappa 0.82, acc 0.92; helpfulness judge agreement 0.56 (a *agreement* figure; do not call it kappa) | Sec. 4 | N | [secondhand (2R)] |
| F14 | 1-2-3 Check (GPT-4o), leak / omit-public / leak-or-omit % | Single 23.0 / 12.0 / 26.3; Single+CoT 2.0 / 32.5 / 34.0; 3-agent Annotate Private 5.0 / 20.0 / 24.5; 3-agent Public Only 15.0 / 9.0 / 23.5; 3-agent Annotate Private w/o transcript 8.5 / 10.0 / **17.5** (best composite) | arXiv 2508.07667 Table 2 (HTML) | Y | [verified-in-source] |
| F15 | 1-2-3 Check (LLaMA-3.1-70B) | Single 29.5 / 23.5 / 48.5; Single+CoT 3.0 / 27.5 / 29.5; 3-agent Public Only 3.0 / 19.5 / **20.5**; 3-agent Annotate Private 24.0 / 23.5 / 42.0 | same | Y | [verified-in-source] |
| F16 | "18%" in 1-2-3 Check abstract | 23.0 -> 5.0 = 18 **absolute points** vs non-CoT single agent. vs CoT single agent leak is already 2.0; pipeline wins only on composite | Table 2 | Y (by arithmetic on F14) | [verified-in-source] |
| F17 | 1-2-3 Check limitation | Overhead impractical for "tight latency constraints, such as live customer support or streaming meeting transcripts" | Limitations | Y | [verified-in-source] |
| F18 | PrivacyChecker | PrivacyLens LR GPT-4o 33.06 -> 8.32 (help 2.69 -> 2.45; LRh 33.56 -> 9.22); DeepSeek-R1 36.08 -> 7.30 (help 2.58 -> 2.35; LRh 37.21 -> 8.06) | arXiv 2509.17488 Table 1 + abstract | Y | [verified-in-source] |
| F19 | Zoom patent | US 11,974,074 B2, filed 2022-04-29, granted 2024-04-30, inventors Shane P. Springer and Alexander Waibel. **Claim 1:** request to begin an off-the-record period; prevent the stream from being included in the recording. **Claims 10-11:** identify keywords indicating the off-the-record request from the audio stream; speech recognition on the audio. **Claims 4-5:** erase the stream from a recording already captured / responsive to the request. The word "retroactive" is **not** in the claims; the description says "the retroactive off-the-record option may allow a participant to remove content from the recording retroactively" and keywords such as "off-the-record" or "confidential" | Google Patents page, claims section (fetched via summarizer; description read in R-001 and by A/B) | Y (claims, via summarizer; formal claim scope/legal effect not assessed) | [verified-in-source] |
| F20 | Bemula | Xie et al., arXiv 2610.18052 (13 Oct 2026): 50 multi-session dialogues, 135 forget requests (6 types), 1,742 test questions, each dialogue has a no-request control; 5 suites (storage, removal, preservation, relearning, extraction); 6 memory systems x 3 backbones; "no system passes more than 1.5% of forget requests end to end", most pass none | abstract | Y | [abstract-only] |
| F21 | Whisper-Streaming latency | "3.3 seconds latency on average" (English, European Parliament); Sec. 5: with 1 s MinChunkSize avg latency 3.3 s EN / 4.4 s DE / 4.8 s CS, WER 2% higher than offline for EN/DE, 6% for CS. Table 1 (one doc, 0.1 s chunk): A40 no VAD WER 5.8+-0.9, latency 2.85+-0.45 s; A40 VAD 5.2 / 3.12+-0.36. Hardware: NVIDIA A40 GPU; **no laptop figure** | arXiv 2307.14743 abstract, Sec. 5, Table 1 | Y | [verified-in-source] |
| F22 | Streaming Sortformer RTF, limit | RTF 0.005 (10 s), 0.093 (1.04 s), 0.180 (0.32 s); designed for up to 4 speakers; latency = input buffer only | arXiv 2507.18446 Table 2 (judge saw a jumbled extraction with these values); text limitations | Y (RTF, limit) | [verified-in-source] |
| F23 | Streaming Sortformer DER (with post-processing, DIHARD III "all") | 19.02 (10 s) / 18.97 (1.04 s) / 19.32 (0.32 s); without PP 19.89 (1.04 s), 20.25 (0.32 s). CALLHOME-part2 "all": 10.09 / 10.79 / 11.50 (B's earlier 11.22/12.40/13.64 was the 4-speaker column and is withdrawn). The judge's own fetch returned a table without column headers (rows 13.67/13.32/13.43 with PP), so could not be mapped | Table 1 | N | [secondhand (2R)] |
| F24 | Survey | Kolmogorov Law (commissioner) / Pollfish, fielded 2026-07-08, n=500 employed US adults, +-4.4%. 33.4% say an AI notetaker was in their meetings; 22.4% could not tell whether recorded. Among the 167 exposed: always asked 34.7%, sometimes 36.5%, never 25.1%, found out afterward 3.6% (65.3% "not always" = derived); +-7.6% for n=167. 18.8% (of 500) discovered after the fact a meeting was recorded without knowledge | krdo.com / Stacker article, 2026-07-16 | Y | [verified-in-source] (article); instrument not seen; not peer-reviewed |
| F25 | Wilson/McNemar/power numbers | see section 6 | our calc | Y | [verified-in-source] (recomputed) |

---

## 3. Evidence by theme

Format per paper: citation + URL; claim; number; what it means for our pipeline part; tag. Tag shown after judge downgrade. Items repeated from section 2 are summarised.

### 3.1 Leakage and contextual integrity (CI)

**P1. ConfAIde (Mireshghallah et al., ICLR 2024).** https://arxiv.org/abs/2310.17884
- Claim: LLM-human privacy-expectation correlation falls with tier; Tier 4 meeting assistants leak and omit; CoT (generic) did not help 2023 models.
- Numbers: F1-F8. GPT-4 correlation 0.8 (Tier 1) -> 0.1 (Tier 3) per Intro (2R).
- Means for us: PRD 1.4 wording must change (F2). OTR-Bench's 20 ConfAIde items = whole Tier 4, clustered by secret, secret announced in-context. Use their three metrics (Leak, Omit-Public, Leak-or-Omit) and 10-run mean/worst-case for stochastic stages.
- Tag: [verified-in-source] (Table 4, Sec. 3.4, Sec. 4.4); App. B.4 and Table 5 values [secondhand (2R)].

**P2. PrivacyLens (Shao et al., NeurIPS 2024 D&B).** https://arxiv.org/abs/2409.00138
- Claim: models that answer privacy-norm probes correctly (GPT-4 ~99%) still leak in action (~25%); privacy-enhancing prompt does not significantly improve action-based evaluation.
- Numbers: F9-F13. Agent-action benchmark (email/messenger), not transcript summarisation: indirect evidence for meetings.
- Means for us: adopt LRh-style (leak among useful outputs) reporting; judge-validation protocol (>=100 hand-labelled pairs, kappa + accuracy).
- Tag: [verified-in-source] (Table 2, abstract); judge protocol [secondhand (2R)].

**P3. 1-2-3 Check (W. Li, Sun, Guan, Zhou, Sap; CMU).** https://arxiv.org/abs/2508.07667 (v3, Feb 2026). Venue disputed (A: IASEAI'26; B: earlier LLMSEC 2025 workshop version): **unverified**, cite as arXiv only.
- Claim: Extractor -> Checker -> Executor reduces ConfAIde Tier 4 leakage; upstream detection errors cascade.
- Numbers: F14-F17.
- Means for us: closest published structure-vs-prompt comparison on our scenario; supplies the strong baseline (single agent + CoT) our B lacks; per-stage Leak_s / Public_s / Q_s metric = our per-stage logging model. Staged LLM pipelines compete with our state machine, they are not a baseline.
- Tag: [verified-in-source].

**P4. PrivacyChecker / PrivacyLens-Live (Wang, Yu et al., Microsoft; Findings EMNLP 2025).** https://arxiv.org/abs/2509.17488
- Claim: model-agnostic extract-flow (sender, recipient, subject, data type, transmission principle) -> judge -> drop/abstract; also a live MCP/A2A variant.
- Numbers: F18. Ablation: verbalising flows is what helps (GPT-4o without verbalisation 11.36 vs 8.32 per B, 1R; Qwen3-14B-NT 30.63 vs 15.91, 1R). Model labelled private info sensitive 98.0% yet leaked 33.1% (1R). Live variant leakage rises with tools 6.7 -> 16.7 for 2 -> 3 tools (1R; ~150 + 36 cases, small).
- Means for us: the "LLM context check" should emit an explicit CI tuple with `audience = all readers of the notes`; static JSONL evaluation likely under-states streaming risk.
- Tag: [verified-in-source] for Table 1 GPT-4o and DeepSeek-R1 only; rest [secondhand (1R)].

**P5. CI-RL (Lan, Inan, Abdelnabi, ..., Sim; NeurIPS 2025 per search listing).** https://arxiv.org/abs/2506.04245
- Claim: prompt CI reasoning + RL on ~700 synthetic examples lowers PrivacyLens leakage.
- Numbers (Table 3, LR %: base -> CI-CoT -> CI-RL): Qwen2.5-7B 50.3 -> 44.8 -> 33.7; Qwen2.5-14B 52.9 -> 42.8 -> 33.9; Mistral-7B 47.9 -> 28.8 -> 31.2; Llama-3.1-8B 18.2 -> 21.3 -> 18.5 (low only because unhelpful, helpfulness 1.05; adjusted ALR 38.9 -> 31.5 -> 29.4). Frontier, CI-CoT only: Claude 3.7 Sonnet 30.4 -> 23.1; Claude 3.7 S-Thinking 32.0 -> 20.1; Gemini 2.5 Flash 29.0 -> 19.7; Gemini 2.5 Pro 37.3 -> 25.3. "Up to 40%" not located as a single row (relative vs absolute unknown).
- Means for us: our local qwen2.5 3B/7B inherits a ~50% baseline leak; report >=2 LLM sizes (local + one stronger, labelled non-local upper bound).
- Tag: [secondhand (2R)].

**P6. CI-Work (Fu, Qin, Zhang, Lin, Wutschitz, Sim, Rajmohan, Zhang; ACL 2026 Industry, pp. 1483-1508).** https://aclanthology.org/2026.acl-industry.103/ ; arXiv 2604.21308
- Claim: enterprise retrieval (incl. meeting transcripts), violation rates 15.8-50.9%, leakage up to 26.7%; utility correlates with violations; scale/reasoning do not fix it; synthetic data.
- Numbers (Table 2, GPT-5, leak / violation / conveyance %): none 11.21 / 27.83 / 93.04; Prompt Defense 8.96 / 21.31 / 81.01; CI-CoT 8.95 / 22.13 / 84.90.
- Means for us: add a dense-context condition; adopt "conveyance" as the utility twin.
- Tag: [secondhand (2R)].

**P7. AirGapAgent (Bagdasarian et al., CCS 2024).** https://arxiv.org/abs/2405.05175
- Claim: data minimisation before the agent sees data beats instruction; hijacking drops a prompted Gemini Ultra agent's protection 94% -> 45% while AirGapAgent keeps 97%.
- Means for us: strongest published analogue to "removal before generation" (hold buffer + committed-only summariser input). Adversarial setting, not meeting speech.
- Tag: [secondhand (2R)] (abstract text).

**P8. CaMeL (Debenedetti et al.).** https://arxiv.org/abs/2503.18813 -- 77% of AgentDojo tasks with provable security vs 84% undefended. Analogy only: guarantees for the deterministic path (explicit cues, scope), LLM for judgment. Prompt injection, not privacy norms. [abstract-only]

**P9. MuPPET (arXiv 2606.23217), PiSAs (arXiv 2607.05318), PrivacyAlign (arXiv 2606.21710).** Multi-party leakage exceeds one-to-one estimates; party tracking unsolved; system design helps but "incorrect LLM judgments remain the main bottleneck"; PrivacyAlign: 1,350 samples, 3,516 annotations, 599 annotators, human-explanation-conditioned judges more reliable. Do not cite model leak rates seen in snippets. Means: audience = everyone who reads the notes; few-shot judge with human explanations. [abstract-only] (A and B each opened abstracts)

**P10. Leaky Thoughts (Green et al., EMNLP 2025).** https://arxiv.org/abs/2506.15674 -- reasoning traces contain sensitive data. Means: audit log stores IDs/hashes, never redacted text or reasoning; add a test grepping all outputs/logs for planted secrets. [abstract-only]

**P11. Dou et al., Reducing Privacy Risks in Online Self-Disclosures (ACL 2024).** https://arxiv.org/abs/2311.09538 -- 19-category taxonomy, 4.8K spans, detector >65% partial span F1, abstraction task, 82% of HCI participants positive. Means: implicit-class ceiling reminder; abstraction as intermediate output. [secondhand (1R)]

### 3.2 Streaming ASR

**P12. Whisper-Streaming / LocalAgreement (Machacek, Dabre, Bojar; IJCNLP-AACL 2023 demo, venue from memory).** https://arxiv.org/abs/2307.14743. F21. Means: confirmed text is ~3-5 s behind speech on a server GPU (laptop unmeasured); a 30-60 s hold is a policy number, not an ASR number. Count hold from confirmation; log ASR delay and hold delay separately. [verified-in-source]

**P13. CUNI IWSLT 2025 / SimulStreaming (Machacek, Polak).** https://arxiv.org/abs/2506.17077. Table 7 (English ACL6060 dev; chunk -> WER% / latency ms; computation-unaware): 0.05 s -> 14.22 / 494; 0.15 -> 13.33 / 596; 0.25 -> 13.10 / 754; 0.5 -> 13.06 / 1262; 2.0 -> 12.69 / 2143. ~1.5 WER points for 0.5 -> 2.1 s. Does not answer laptop speed. [secondhand (2R)]

**P14. DSM-ASR (Zeghidour et al., Kyutai).** https://arxiv.org/abs/2509.08753 -- 2.6B decoder-only, 2.5 s delay, 6.4% WER average on OpenASR short-form (leaderboard best quoted 6.1%), delay conditionable. Laptop feasibility unexamined. Fallback only. [secondhand (1R)]

**P15. WhisperRT / CarelessWhisper (Krichli, Raj, Keshet).** https://arxiv.org/abs/2508.12301 -- LoRA causal encoder, chunk <300 ms; notes Whisper-Streaming pads to 30 s every step. No numbers. [abstract-only]

**P16. Careless Whisper (Koenecke et al., FAccT 2024).** https://arxiv.org/abs/2402.08021 -- ~1% of transcriptions contained entire hallucinated phrases; 38% of hallucinations include explicit harms; associated with longer non-vocal durations (A's reading). Means: OFF periods create silence; gate with VAD; add "hallucinated cue on silence" to the false-alarm class. The extension to our muted-track design is an inference, untested; mid-2023 Whisper. [secondhand (2R)] (abstract quote agreed by both)

**P17. Streaming disfluency/repair: Chen et al. "Teaching BERT to Wait" (NAACL 2022, arXiv 2205.00620); STIR (Hough, Purver, arXiv 1408.6788).** Emit-now vs wait trade-off; "strike that" is also a repair marker. No corpus numbers on repair vs retraction. Means: type-3 benchmark needs repair-vs-retraction pairs and PENDING_CONFIRM. [abstract-only]/[secondhand (1R)]

### 3.3 Diarization (live path should not need it)

**P18. Streaming Sortformer (Medennikov et al., NVIDIA).** https://arxiv.org/abs/2507.18446. F22-F23. Max 4 speakers; DER ~19% on DIHARD III means ~1 in 5 frames misattributed on hard audio. Means: LiveKit tracks give identity; keep diarization for mixed/import path only; score scope ownership with oracle AND diarized labels.

**P19. DiariZen (Han et al., BUT).** https://arxiv.org/abs/2409.09408 -- offline; DER AMI 15.4, AISHELL-4 11.7, AliMeeting 17.6 (macro 14.9). Means: post-hoc labelling of imported recordings. [secondhand (1R)]

**P20. pyannote community-1 model card (HF).** DER 3.1 -> community-1: AMI IHM 18.8 -> 17.0; DIHARD3 21.4 -> 20.2; AMI SDM 22.7 -> 19.9; VoxConverse 11.2 -> 11.2. CC-BY-4.0, gated; **no streaming mode**. A's earlier suggestion it is a streaming option was wrong. [secondhand (1R)]

**P21. Latency of online diarizers (Aperdannier et al., arXiv 2407.04293).** DIART pyannote pairing 0.057 s latency, DER 44.86 on a small retrained setup (not representative); UIS-RNN-SML latency grows 0.34 -> 10.3 s. Means: diarize for labels, never gate on it. [secondhand (1R)]

**P22. Powerset loss (Plaquet, Bredin, arXiv 2310.13025); NOTSOFAR-1 (arXiv 2501.17304).** Overlap is the failure that matters for "whose OFF is it"; NOTSOFAR-1 tcpWER best single-channel 22.2%, multi-channel 10.8% (our setup is closer to close-talk). No paper found comparing per-track vs mixed diarization for meetings. [abstract-only]; NOTSOFAR [secondhand (1R)]

### 3.4 Opt-out, unlearning, forgetting

**P23. OrthoGrad (Shamsian et al., arXiv 2503.02312).** Whisper-Tiny + LibriSpeech, WER %, mean of 5 speakers: original retain 9.99 / unlearn 11.12 / speaker-heldout 10.06 / test 11.08; OrthoGrad 12.11 / 96.24 / 98.53 / 13.98; NegGrad+ test 85.90; SCRUB 100.00; GDR-GMA 32.52. Model-level forgetting works only for a seen speaker, tiny model, and costs test WER; wrong tool for a runtime session opt-out. [secondhand (2R)]

**P24. UnSLU-BENCH (Koudounas et al., Interspeech 2025); TruS (arXiv 2601.20481).** Evaluation vocabulary (efficacy/utility/efficiency); TTS opt-out as inference-time control (not ASR evidence). [abstract-only]

**P25. Bemula.** F20. Closest published evaluation of "forget what I said": measures removal AND preservation AND extraction after removal, with a no-request control dialogue. Means: borrow the control-dialogue trick and the three-way scoring for OTR-Bench type 3; derived artifacts (summaries) must be regenerated. Text chat memory, not speech. [abstract-only]

**P26. Model-unlearning literature (arXiv 2402.15159, 2508.12220, 2510.25117).** About removing training-data influence from weights: not our problem (we do not train on transcripts). [secondhand (1R)]

### 3.5 Detection of cues and PII; closest systems; patents

**P27. Zoom patent US 11,974,074 B2** (F19). Prior art for explicit keyword-triggered off-the-record and erasure. Governance point: retroactive removal is host-controlled/optional in the description (who may retract whose speech is Q-Q13). Continuation US 12,587,614 seen only in a search result. Amazon-style "privacy mode based on speaker identifier" (e.g. US 12,243,532, scanned PDF) and headset patent US 7,136,684: [secondhand (1R)]; Amazon's retroactive-utterance deletion description NOT read. Tag Zoom: [verified-in-source]; others [secondhand].

**P28. Trustera (Gouvea et al., Interactions LLC, arXiv 2303.09438).** First functional real-time spoken-PII redaction system (ASR -> NLU -> audio mute), thousands of agents. PII only; no user-signalled scope or retroactive request. Means: run Presidio over the hold-window, not per segment (spoken identifiers split across chunks). A read the PDF intro, B the abstract. [secondhand (2R)]

**P29. Beyond Clean Text (Harrison, Manzelli; NeurIPS 2026 workshop).** PII detectors on ASR transcripts WER 3.17% vs 17.49%; "architecture, not ASR quality alone, is the stronger predictor"; 545-clip benchmark. Means: evaluate PII/cue stages on ASR output. [abstract-only]

**P30. DialogPII (arXiv 2606.30312).** Synthetic dialogues -> TTS -> Whisper, labels projected; recipe for OTR-Bench-ASR. [abstract-only]

**Gap:** no paper found on detecting "off the record"-style confidentiality requests as speech acts. A medRxiv snippet (GPT-3.5 sensitivity 97%, specificity 18% on adolescent notes) and KIT's access-control study are snippets only [secondhand (1R)]; the specificity warning is a plausible risk for our false-alarm class, not an established result.

### 3.6 Consent, legal, survey

All court items are allegations, not findings.

**P31. Brewer v. Otter.ai (N.D. Cal., Aug 2025).** Alleged recording without consent of all participants, training on recordings; ECPA and CIPA (OECD incident page opened by A; NPR fetch timed out). Case no. 5:25-cv-06911-EKL, consolidation 2025-10-22 and a partial denial of motion to dismiss on 2026-08-13 come only from a BuildBetter blog citing a third source: **unverified**. [secondhand]

**P32. Cruz v. Fireflies.AI (C.D. Ill., Dec 2025); Fricker (N.D. Ill., Mar 2026).** Alleged BIPA violation via "speaker recognition" voiceprints of non-users. Article (dataprivacyandsecurityinsider, 2025-12-24) says "an Illinois federal court"; courts/dates/damages from the blog or snippets. Supports PRD non-goal (no voiceprints): diarization embeddings are voiceprints under the plaintiff's theory. [secondhand]

**P33. Kolmogorov Law / Pollfish survey.** F24. Law-firm-commissioned, online, self-reported. No peer-reviewed notetaker-consent user study found (a gap, not a negative finding). [verified-in-source] (article)

**Consent law:** Cal. Penal Code 632 text and the all-party-consent state list could not be fetched (HTTP 403) and come from a blog: not verified.

### 3.7 Evaluation methodology and statistics

**P34. Miller, Adding Error Bars to Evals (arXiv 2411.00640).** Clustered SE can be "over 3X larger than naive" (Table 4 caption); report cluster count with n; paired differences; power analysis. [secondhand (2R)]

**P35. Bowyer, Aitchison, Ivanova, Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints (ICML 2025, arXiv 2503.01747).** CLT intervals poorly calibrated at small N; Wilson and Bayesian intervals reach nominal coverage; bootstrap poorly calibrated. B's "92.5% coverage at N=100 clustered" could not be found by A: **dropped**. [secondhand (2R)]

**P36. LLM-as-judge (Zheng et al., arXiv 2306.05685).** Search snippet only (>80% agreement on pairwise chat preference with GPT-4). Not evidence for a 3B-7B local leak judge. [secondhand (1R)]

---

## 4. Design changes ranked

Ranked by (expected effect on the validity or the headline) / effort. S = <1 h, M = 1-4 h, L = >4 h.

| Rank | Change | Files | Expected effect | Effort |
|---|---|---|---|---|
| 1 | **Fair baselines.** Add B+ = CI-tuple extract-then-judge (or CI-CoT) prompt (P3, P4, P5). Run B and B+ in two modes: (i) offline hindsight, (ii) causal with the same lag as C. Primary claim = C vs best B+ in causal mode at matched delay | `bench/systems.py`, `bench/run_eval.py`, `otr/llm.py` | Makes the hypothesis testable; removes strawman and hindsight confounds. May shrink or reverse C's advantage: that is information | M |
| 2 | **Leak AND omission together.** Report Leak, Omit-Public, Leak-or-Omit per ConfAIde Table 4 and conveyance per CI-Work; helpfulness-adjusted leak; leak-vs-omit scatter; 10-run (or k>=5) mean and worst case for stochastic stages | `bench/metrics.py`, `bench/plot.py`, `bench/run_eval.py` | Stops the primary metric rewarding over-redaction (CoT: 2.0% leak but 32.5% omitted) | S-M |
| 3 | **Per-stage leak logging** after PII, cue, state machine, LLM check (Leak_s, Public_s, Q_s as in 1-2-3 Check) | `otr/pipeline.py`, `bench/metrics.py` | Localises the known first-run problem (C 45% vs A 14% per WORK_SPLIT) to a stage; I1/I3/I6 diagnosis | M |
| 4 | **Cue matching on unconfirmed hypothesis** (flip to PENDING on a hypothesis hit; commit OFF only on confirmed text); count hold from confirmation; define hold relative to speech time; log ASR delay and hold delay | `otr/cue_detector.py`, `otr/state_machine.py`, `otr/hold_buffer.py`, `otr/ingest/stt.py` | Gains ~1-3 s on cue reaction (estimate from F21, not measured); makes P95 end-to-end delay reportable | M |
| 5 | **VAD gating** of OFF-period silence before ASR; hallucinated-cue-on-silence false-alarm cases | `otr/ingest/stt.py`, `otr/ingest/livekit_source.py`, `bench/` | Removes P16 failure mode (fabricated text/cues) | S-M |
| 6 | **Gold private spans for all 40 items + paraphrase-aware judge + validation set** (>=100 hand-labelled (output, span) pairs, kappa + accuracy; 3-5 explained examples per case type in the judge prompt) | `bench/build_bench.py`, `bench/metrics.py`, `bench/otr_bench.jsonl` | Removes judge error from the headline (string match missed 8% in ConfAIde) | M |
| 7 | **ASR-noise benchmark via TTS -> Whisper** on the 40 snippets (plus cue-corruption variants: "of the record", dropped negation, "strike back"); report cue recall vs WER; per-condition tag (per-track vs mixed) | `bench/` (new builder), `otr/ingest/replay_source.py`, `otr/ingest/stt.py` | Cue recall is capped by ASR recall; clean-text results overstate. DialogPII recipe is unverified at the dataset level | M-L |
| 8 | **Presidio over the hold-window**, with a test for a phone number split across two Segments | `otr/pii.py`, `otr/hold_buffer.py` | Catches split identifiers (Trustera motivation; no number) | S |
| 9 | **Air-gap invariant tests:** summariser input built only from committed segments; no `[REDACTED: topic]` markers; audit log holds IDs/hashes only; grep-for-planted-secrets test across outputs and logs; no embeddings written to disk | `otr/pipeline.py`, `otr/state_machine.py`, `tests/` | Privacy of the privacy layer (P7, P10, P32); cheap to prove | S-M |
| 10 | **Removal cascades with provenance and regeneration** (summary sentence -> segment IDs; regenerate, not string-edit); control item per type-3 case (same item without the retraction cue); post-removal extraction test | `otr/pipeline.py`, `bench/` | Bemula-style scoring: removal + preservation + extraction | M |
| 11 | **Abstraction output mode** ("[health information]") as a 4th system or ablation in PENDING_CONFIRM | `otr/state_machine.py`, `otr/llm.py`, `bench/systems.py` | Keeps summary usefulness up vs delete (P4, P11); topic-leak risk of the label itself must be tested | M |
| 12 | **Track-identity opt-out** (drop that participant's track / identity from LiveKit, no voiceprints) | `otr/ingest/livekit_source.py`, `otr/ingest/diarize.py` | Exact for *that speaker's own track after the drop*. **Not** "zero leak by construction": other participants may repeat/paraphrase; bleed into other mics; content already in the hold buffer; mid-meeting opt-out timing; PRD 1.5 already excludes secondhand disclosure for v1. Benchmark should still include these cases | S (design) / M (tests) |
| 13 | **Two LLM sizes** (local 3B/7B + one stronger upper bound labelled non-local); implicit class restricted to a closed list with keyword-gated confirmation if the 7B proves too weak | `otr/llm.py`, `bench/run_eval.py` | Separates "structure helps" from "LLM too weak" (P5) | M |
| 14 | **Dense-context condition** (long transcript, several distractor private items) and live streaming mode with real ticks (I2) | `bench/`, `demo/live_session.py` | Static per-snippet benchmarks hide density and streaming effects (P4, P6) | L |
| 15 | **Consent roll call + visible recording indicator** in demo narrative; state "local only, no training use, not legal compliance" | `demo/server.py`, docs | Legal-risk story (P31, P32); suppression does not substitute for consent to record | S |
| 16 | **Laptop real-time-factor measurement** for whisper_streaming / SimulStreaming on the target machine | `otr/ingest/stt.py`, scripts | All cited latencies are server-GPU or computation-unaware | S |

---

## 5. Benchmark composition notes (OTR-Bench)

- Relabel the 20 ConfAIde items **"contextual-confidential"**: explicit-in-context, 5x4 grid, cluster by secret (5 clusters). True implicit items (health/salary/HR with no cue) must come from the QMSum/AMI half or new items.
- Cluster QMSum/AMI-based items by source meeting; report cluster counts next to n.
- Add: repair-vs-retraction pairs for "strike that"; false cue ("the movie *Off the Record*"); hallucinated cue on silence; speaker-ownership cases (B retracts A's words; A's OFF vs B's reply); cross-segment PII; paraphrase-by-others cases (honest limit of track opt-out); per-item no-cue control for type 3.
- Tag every item with source condition (per-track vs mixed) and ASR condition (clean text vs TTS->Whisper).
- Hand-label gold spans for all 40 items (WORK_SPLIT currently says ~10).

---

## 6. How to report results honestly with ~40 items

**Unit:** the item. Outcome = leaked (1/0): any gold private span recoverable from the output by the validated judge. Span-level counts are secondary and need item-clustered inference.

**Step 1: per-system rate with a Wilson 95% interval** (not +-1.96 sqrt(p(1-p)/n)). Wilson centre = (p + z^2/2n)/(1 + z^2/n); half-width = z sqrt(p(1-p)/n + z^2/4n^2)/(1 + z^2/n); z = 1.96. Recomputed values (n = 40), [verified-in-source] (our calc):

| k/40 | Wilson 95% |
|---|---|
| 0 | 0.0 - 8.8% (Clopper-Pearson upper also 8.8%; write "0/40, upper bound 8.8%", never "0% leakage") |
| 2 | 1.4 - 16.5% |
| 5 | 5.5 - 26.1% |
| 6 | 7.1 - 29.1% |
| 12 | 18.1 - 45.4% |
| 20 | 35.2 - 64.8% |

Per-type cells (n = 4-8): intervals ~40-60 points wide; report k/n and say "descriptive only".

**Step 2: paired comparison, exact McNemar.** Same 40 items for both systems. b = B leaks and C does not; c = C leaks and B does not. Under H0, b ~ Binomial(b+c, 0.5), two-sided exact. Report b, c, paired risk difference (b - c)/n, and an exact CI.

Worked example (invented counts, **not our data**; re-checked by the judge): B leaks 12/40 (30.0%, Wilson 18.1-45.4); C leaks 5/40 (12.5%, 5.5-26.1); b = 9, c = 2, both-leak = 3, neither = 26 (9+2+3+26 = 40).
- Exact McNemar p = 2 x P(X >= 9 | n = 11, p = 0.5) = **0.0654** (not significant at 0.05). Re-computed.
- Risk difference = (9 - 2)/40 = **17.5 points**.
- Conditional exact CI for the discordant proportion b/(b+c) = 9/11: Clopper-Pearson [0.482, 0.977], i.e. odds ratio b/c in [0.93, 42.5], includes 1 (our calc).
- Paired percentile bootstrap (20,000 draws over 9 x +1, 2 x -1, 29 x 0) gives [2.5, 32.5] points, excluding zero although the exact test does not: this is the small-n anti-conservatism Bowyer et al. warn about. **Do not headline the bootstrap.**
- Honest sentence: "C leaked on 5/40 items (12.5%, 95% Wilson CI 5.5-26.1) vs 12/40 (30.0%, 18.1-45.4) for B+; paired difference 17.5 points; exact McNemar p = 0.065; early evidence, not significant at 0.05."

**Power:** unpaired two-proportion test, 30% vs 10%, alpha 0.05, power 80%: 61.6, so **62 items per arm** (our calc). 40 items detect only very large effects; paired designs help but depend on discordance (here 11/40 discordant).

**Step 3: clustering.** Cluster by secret (5 Tier-4 clusters) and by source meeting. Report cluster count next to n. Use a cluster bootstrap or cluster-level sign test as a *sensitivity* analysis only (with 5 clusters it is very coarse). Miller: clustered SE can be >3x naive.

**Step 4: stochastic runs.** k >= 5 samples per item at fixed temperature; item-level mean then average; report worst-case too. Runs reduce sampling noise, not item-selection noise: k x 40 is not 200 independent trials.

**Step 5: pre-specify.** One primary comparison: C vs B+ (causal), item-level leak, exact McNemar. One co-primary utility: omit-public. Everything per-type is exploratory. Show the full leak-vs-omit table for A, B, B+, C and the hold-length sweep; do not hide A or B+ where they win (current WORK_SPLIT table: A leaks less than C).

**Step 6: judge error.** Report judge sensitivity/specificity on the hand-labelled set; show leak rate under "judge says leak" and under human-labelled subset. Local-judge reliability unknown until measured (PrivacyLens: leak kappa 0.82 vs helpfulness 0.56 agreement, 2R).

**Step 7: language.** "early evidence", "in this 40-item, partly synthetic set". Say how many items were hand-checked and that insertions are LLM-generated.

**What our data CAN support:** large within-set differences with exact paired tests; descriptive per-type counts; existence proofs (a specific cue type is/is not handled); latency/delay distributions (continuous, more informative per item); failure-mode taxonomy via per-stage logging.
**What it CANNOT support:** generalisation beyond the set; any "outperforms" without the paired p and CI; per-type rankings (n = 4-8); a claim that structure, rather than the LLM stage, caused a gain unless the ablation (C without LLM, C-with-flows vs C-plain) shows it; legal-compliance claims; real-meeting retraction behaviour.

---

## 7. Open questions and could-not-verify

### 7.1 Open questions (Q10+; PRD Q1-Q9 unchanged)

- **Q10.** What is B+ (CI-CoT per Lan et al.; extract-flows-then-judge per PrivacyChecker; three-agent per 1-2-3 Check) and does it run with hindsight or causal-with-lag? Decides testability. Recommendation: B+ = PrivacyChecker-style flow extraction, both modes.
- **Q11.** Retraction delay: how long after a sentence do people retract it ("strike that", "forget what I said")? No corpus measurement found; ASR confirm is ~3-5 s on server GPU, so 30 vs 60 s hold is a guess. Options: mine AMI/QMSum for repair/retraction phrases; a 10-person scripted study. Hold sweep (F5) should be plotted against assumed delay distributions until measured.
- **Q12.** Cue recall as a function of ASR WER and hallucination: how often are "off the record"/"strike that" mis-transcribed, and does fuzzy matching on the hypothesis stream fix it?
- **Q13.** Who owns a privacy signal? Zoom's description makes retroactive removal host-controlled/optional. With per-participant tracks: can B retract A's words; does A's OFF suppress B's replies? How does the benchmark label this?
- **Q14.** How to define and score "by meaning" retroactive targets separately from leak rate; how often is "strike that" a repair, not a retraction (no corpus numbers found)?
- **Q15.** Is "implicit" in OTR-Bench really implicit, and how do we label truth without circularity with the LLM that inserted the spans?
- **Q16.** Is the local 3B/7B model good enough for the CI-tuple check (7B baselines leak ~50% on PrivacyLens), or must the implicit class be a closed list with keyword-gated confirmation?
- **Q17.** Accept a local judge for the primary metric or require hand-labelled gold spans for all 40 items (cheaper; recommended)?
- **Q18.** Consent boundary: suppression does not substitute for consent to record. Is a consent roll call in scope for the demo narrative? (Not legal advice.)

### 7.2 Could not verify (judge pass)

- ConfAIde App. B.4 (16/200) and Table 5 values, PrivacyLens judge kappa details, 493/1,479 counts: seen only by researchers (or not located).
- Streaming Sortformer DER by dataset column: judge's fetch had no column headers; relies on A's rendered-table read and B's correction.
- CI-RL Table 3, CI-Work Table 2, SimulStreaming Table 7, OrthoGrad Table 2, pyannote model card, DiariZen, NOTSOFAR, DSM-ASR, WhisperRT, Dou et al., Aperdannier: researcher-read only.
- Zoom patent: claims read via a summarising fetch; formal claim scope and the continuation US 12,587,614 not read. Amazon patent text (scanned) not read.
- Bemula: abstract only; per-type failure breakdown unknown.
- 1-2-3 Check venue (IASEAI'26 vs LLMSEC workshop) unresolved.
- CI-RL "up to 40%" relative vs absolute; CI-RL ConfAIde Tier 4 results.
- Otter 2025-10-22 consolidation and 2026-08-13 ruling; Fireflies court/date/damages; Fricker; all court docket records; Cal. Penal Code 632 text; all-party-consent state list.
- Survey instrument (only the Stacker/law-firm article).
- Any peer-reviewed notetaker-consent user study; per-track vs mixed diarization comparison; any evaluation of retroactive redaction in streaming speech; disfluency/repair corpus numbers for "strike that".
- Laptop-level real-time factors for any streaming ASR.
- Bowyer et al. "92.5% coverage at N=100" (dropped from this file).
- PrivacyAlign/CIMemories/Schneier snippet numbers (not cited).
- Retraction delay (Q11).

---

## 8. Dispute log (A vs B)

| # | Dispute | A said | B said | Resolution (judge) | Basis |
|---|---|---|---|---|---|
| D1 | Which ConfAIde Tier 4 task is 39%/57%? | Summary | Action-item (round 1; B withdrew in round 2) | **Summary.** Action items are 0.29/0.38 | Judge read `pdftotext -raw` Table 4: "Act. Item" block first (0.29/0.38), "Summary" block second (0.39/0.57); Sec. 4.4 sentence agrees. [verified-in-source] |
| D2 | Is "CoT does not help" still valid? | Stated as current guidance in P1 and top-5 #2 | "Superseded" by 2025 work | **Both partly wrong.** 2023 result (generic CoT, GPT-4/ChatGPT) stands as history; CI-style CoT on GPT-4o cuts Tier 4 leak 23.0 -> 2.0 but omission 12.0 -> 32.5 and composite worsens 26.3 -> 34.0. Wording: "generic CoT did not help 2023 models; CI-aware prompting cuts leakage on newer models at a large omission cost; judge on the composite." | F6, F14 |
| D3 | Novelty: "no prior work" on off-the-record/retroactive? | Claimed novel/unsupported by prior evaluation | Patents contradict "no prior work" | **Use "no prior published evaluation", not "no prior work".** Zoom claims 10-11 (keyword detection via speech recognition) and 4-5 (erasure) are in the claims; "retroactive" appears only in the description. Neither draft had read the claims; judge did (via summarizer fetch). | F19. [verified-in-source] |
| D4 | Track-drop opt-out = "zero leak by construction"? | Yes (P17, top-5 #3) | Overclaim | **Overclaim.** Exact only for that speaker's own track after the drop. Phrase accordingly; keep cases in benchmark | Engineering argument; no source supports the strong claim. PRD 1.5 already excludes secondhand disclosure. |
| D5 | Does the survey support "most people aren't asked"? | Supports PRD 1.1 weakly (as industry evidence) | "Unverified"; later: not what it shows | **Weaker than stated.** Only 34.7% always asked; 36.5% sometimes; 25.1% never; 3.6% afterward (n=167). "Most are not *always* asked (65.3%)" is arithmetically true but misleading. PRD should cite the figures, label as law-firm-commissioned. B's round-1 "no survey found" was wrong; A's "supports the PRD sentence" is too generous | F24, article re-read |
| D6 | CALLHOME-part2 "all" DER | (A: not extracted) | Round 1: 11.22/12.40/13.64; round 2 withdrew -> 10.09/10.79/11.50 | Adopt 10.09/10.79/11.50 with `[secondhand (2R)]`; judge could not map columns | F23 |
| D7 | pyannote 4/community-1 as a usable online diarizer? | Listed (secondhand) | Model card: no streaming mode | **Not streaming.** Whole-file pipeline, gated | P20 |
| D8 | 1-2-3 Check venue | IASEAI'26 | LLMSEC 2025 workshop earlier version; v3 page names no venue | Unresolved; cite as arXiv | page names none |
| D9 | PrivacyLens helpfulness figure 0.56 | not stated | "kappa" | Call it "agreement"; text cut off | A's critique of B |
| D10 | Strength of B's "strawman baseline" | Agrees (Q5) | Main objection | **Accepted** (design change 1); "superseded" wording rejected per D2 | F14, F18 |
| D11 | Bowyer et al. 92.5% clustered coverage at N=100 | could not find | cited | **Dropped** | not found in extraction |
| D12 | Whether CI-RL "up to 40%" | unverified | not a single row; ~36% relative for Qwen2.5-14B | Unresolved | P5 |
| D13 | Tier 4 "implicit"? | Missed originally | Explicit-in-context | **B right**; relabel (Sec. 5) | Sec. 3.4 text re-read by judge |

---

## 9. Update log (append-only)

### R-001 | 2026-10-22 | Merge by judge/editor
- Merged `docs/research/draft_a.md` (now in `docs/archive/research/`), `draft_b.md`, `critique_of_a.md`, `critique_of_b.md` into this file. Inputs untouched.
- Judge re-checked in primary sources: ConfAIde Table 4 / Sec. 3.4 / Sec. 4.4 / Table 11 (PDF text); PrivacyLens Table 2 (PDF text); 1-2-3 Check Table 2 + limitation (HTML); PrivacyChecker Table 1 (HTML); Zoom US 11,974,074 B2 claims 1, 4, 5, 10, 11 and description (Google Patents); Bemula abstract; Whisper-Streaming abstract/Sec. 5/Table 1 (PDF text); Streaming Sortformer RTF table + limit (partial, DER unmapped); Kolmogorov/Pollfish article; Wilson, exact McNemar, bootstrap, CP and power numbers (Python/SciPy).
- Changes vs drafts: (1) ConfAIde 39/57 settled as summary; added Table 11 evidence that the privacy instruction cuts GPT-4 summary leak 0.68 -> 0.39 without eliminating it (new, from judge). (2) Zoom patent upgraded: keyword detection and erasure are in the dependent claims, "retroactive" is description-only (neither draft had read the claims). (3) "Zero leak by construction" removed. (4) Survey claim reworded to actual figures. (5) Researcher `[verified-in-source]` items not re-opened by the judge are **downgraded to `[secondhand (2R)/(1R)]`**; abstract-only unchanged. (6) Bowyer 92.5% claim dropped. (7) B's CALLHOME correction adopted but marked unverified by judge. (8) Questions renumbered Q10+.
- Not done: no new topic searches beyond spot-checks; no legal docket checks; no laptop RTF measurements.

### Next research passes (checklist; add dated entries when done)
- [ ] New privacy benchmarks: CI/leakage benchmarks for agents and multi-party settings (MuPPET, PiSAs, PrivacyAlign follow-ups; ConfAIde/PrivacyLens successors); check licences/format for reuse in OTR-Bench.
- [ ] Streaming diarization and ASR: new online diarizers (Sortformer releases, DiariZen online), streaming Whisper variants, laptop RTF numbers; hallucination-on-silence follow-ups to Careless Whisper.
- [ ] Meeting-assistant litigation: dockets for Brewer/In re Otter.AI, Cruz and Fricker v. Fireflies; Cal. Penal Code 632 and all-party-consent list from primary text; any new BIPA/CIPA rulings.
- [ ] Spoken-cue datasets and studies: corpora with "off the record"/"strike that"/retraction speech acts; repair-vs-retraction frequency (Q11, Q14); peer-reviewed notetaker-consent user studies.
- [ ] Patent follow-up: read Zoom continuation US 12,587,614, Amazon "privacy mode" patents (OCR the scans), assess claim scope with counsel if the project goes public.
- [ ] Re-verify unresolved table values (Sortformer DER columns, CI-RL "up to 40%", 1-2-3 Check venue, PrivacyLens 1,479).
- [ ] Re-check Bemula once an extended version or code release exists; borrow its control-dialogue protocol.
