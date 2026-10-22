# Research draft A: literature for the OTR meeting agent

Author: Researcher A. Date of search: 2026-10-22. Scope: PRD 1.1-1.7, 2.5-2.6, WORK_SPLIT.md.

Confidence tags: **[verified-in-source]** = I downloaded the paper PDF or opened the publisher page and read the text/table quoted. **[abstract-only]** = I saw only the abstract or a landing page. **[secondhand]** = news, law-firm blog, or search-result summary; I did not read the primary document.

Caveat on tables: I extracted PDFs with `pdftotext -layout`. Where a table came out interleaved I rendered the PDF page to an image and read it (ConfAIde Table 4, 1-2-3 Check Table 2, CI-RL Table 3, Streaming Sortformer Table 1). PrivacyLens Table 2 is the one table I could not render-verify; it is flagged. Revision 2 (after cross-checking draft_b.md; see critique_of_b.md) fixed the ConfAIde caveat, resolved the 1-2-3 Check effect size, and added B's better points.

---

## 0. Check of PRD 1.4 claims against the papers

### 0.1 ConfAIde (arXiv 2310.17884; ICLR 2024 spotlight)

PRD says: "GPT-4 and ChatGPT leak ... (reported 39% and 57%)". **Confirmed, with precision on which task.**

- Abstract (v2): "even the most capable models such as GPT-4 and ChatGPT reveal private information in contexts that humans would not, 39% and 57% of the time, respectively".
- Introduction: "GPT-4 and ChatGPT reveal secrets 22% and 93% of the time in Tier 3, and flow information to inappropriate actors 39% and 57% of the time in Tier 4, even though they are directly instructed to preserve privacy."
- **Table 4 (PDF page 8, rendered and read visually; lower is better).** Two blocks with rotated row labels. The **"Act. Item" block comes first, the "Summary" block second.**

| Block | Metric | GPT-4 | ChatGPT |
|---|---|---|---|
| Summary | Leaks Secret (Worst Case) | 0.80 | 0.85 |
| Summary | **Leaks Secret (mean of 10 runs)** | **0.39** | **0.57** |
| Summary | Omits Public Information | 0.10 | 0.27 |
| Summary | Leaks Secret or Omits Info. | 0.42 | 0.74 |
| Act. Item | Leaks Secret (Worst Case) | 0.80 | 0.85 |
| Act. Item | Leaks Secret | 0.29 | 0.38 |
| Act. Item | Omits Public Information | 0.76 | 0.89 |
| Act. Item | Leaks Secret or Omits Info. | 0.89 | 0.96 |

  So 39/57 is the **meeting-summary** leak rate. This matches Sec. 4.4: "This leakage is higher in the meeting summary task compared to the personal action item generation task." (Draft B read the two blocks the other way round; see critique_of_b.md.)
- Table 5: CoT does not help (Tier 4 Leaks Secret GPT-4 0.39 -> 0.40; ChatGPT 0.57 -> 0.61). Sec. 4.5: "using chain of thought (CoT) does not improve leakage, in fact it makes the leakage more severe." The prompt was a generic "Take a deep breath and work on this step by step", on GPT-4/ChatGPT.
- **Tier 4 size and construction (Sec. 3.4):** "20 transcripts ... by iterating through five secrets ... and four public information types". Three people discuss a secret about a fourth person X, say X should remain unaware, then X joins. So the 20 ConfAIde items in OTR-Bench are the **whole tier**, form a 5x4 grid (cluster by secret), and the secret is **announced as confidential in context** (explicit-in-context, not implicit-from-content).
- **Leak metric caveat (App. B.4):** in all 200 GPT-4 action-item responses the authors found 16 leaks missed by exact string match (e.g. "move to VISTA" vs "transition to the VISTA project") and no string-match false positives. Exact string match under-counts leaks (about 8% of responses in that check).
- Corrections to add to the PRD: (a) 39/57 are the Tier 4 summary leak, mean over 10 runs; worst-case 80/85; (b) the privacy instruction was already in the prompt; (c) report the paper's composite "Leaks Secret or Omits Info." (0.42 / 0.74) next to leak rate; (d) Tier 4 = 20 clustered, explicit-in-context items.

### 0.2 PrivacyLens (arXiv 2409.00138; NeurIPS 2024 Datasets and Benchmarks)

PRD says: "25.68% for GPT-4, 38.69% for Llama-3-70B" with privacy-enhancing instructions. **Confirmed with a metric precision.**

- Abstract: "state-of-the-art LMs, like GPT-4 and Llama-3-70B, leak sensitive information in 25.68% and 38.69% of cases, even when prompted with privacy-enhancing instructions."
- Table 2 defines LR = leakage rate and **LRh = leakage rate adjusted to cases with positive helpfulness**. From the (interleaved) table, the 25.68 and 38.69 figures are the **LRh** column under the privacy-enhancing prompt; the unadjusted LR in the same rows reads 24.54 (GPT-4) and 39.15 (Llama-3-70B). The row-to-model alignment in my extraction is garbled, so treat the LR values as probable, but the abstract and Sec. 1 ("GPT-4 still leaks information in 25.68% of cases ... even with privacy-enhancing prompt engineering") confirm the headline.
- Sec. 5 text: with the **basic** prompt GPT-4 leaks 27.23% (LRh), so the privacy prompt buys roughly 1.5 points. Probing accuracy is near-perfect (GPT-4 about 99%) while action-level leakage is about 25%: the judgment-action gap.
- Scale: 493 seeds, 493 vignettes, 493 trajectories, 1,479 probing questions.

### 0.3 Corrections to carry into docs/PRD.md 1.4 / L-001

1. ConfAIde figures are correct; state they are Tier 4 summary leakage averaged over 10 runs, and add the worst-case 80/85, the 0.42/0.74 leak-or-omit composite and that Tier 4 is 20 transcripts.
2. PrivacyLens figures are correct; state they are the helpfulness-adjusted rate (LRh) under the privacy-enhancing prompt, 493 cases.
3. Label the ConfAIde 20 as "contextual-confidential" (secret announced in context, one 5x4 grid), not "implicit"; true implicit items must come from elsewhere.
4. Neither paper evaluates streaming audio, explicit "off the record" cues, or retroactive requests (see Section 7).

---

## 1. Contextual integrity and privacy leakage in LLMs and agents

### P1. ConfAIde: "Can LLMs Keep a Secret?" (Mireshghallah, Kim, Zhou, Tsvetkov, Sap, Shokri, Choi)
- URL: https://arxiv.org/abs/2310.17884 (PDF read). ICLR 2024.
- Claim: LLMs often disclose in contexts where humans would not; leakage gets worse in the higher, more realistic tiers; prompting and CoT do not fix it.
- Numbers: see 0.1. Also: GPT-4's correlation with human privacy expectations drops from 0.8 (Tier 1) to 0.1 (Tier 3) (Introduction).
- Relevance: Tier 4 is our meeting-summary scenario (20 transcripts only). The failure mode they describe is structural: the summary is addressed to all attendees, so the model cannot reason that an excluded person is among them (Sec. 4.4). Our committed notes have the same property: the "audience" is everyone who can read the notes.
- Design implication (benchmark + state machine): report the paper's three metrics (Leaks Secret, Omits Public, Leaks-or-Omits) for systems A/B/C, and add the 10-run worst case, since leaks are stochastic for LLM-based systems. The 2023 CoT result was a generic prompt on GPT-4/ChatGPT and is not the last word (see P4, P5: CI-specific reasoning prompts do help newer models); use a structured CI-tuple prompt, not a generic "think step by step".
- Confidence: [verified-in-source]

### P2. PrivacyLens (Shao, Li, Shi, Liu, Yang)
- URL: https://arxiv.org/abs/2409.00138 (PDF read). NeurIPS 2024 D&B.
- Claim: models that answer privacy-norm questions correctly still leak when acting as agents; privacy-enhancing prompts help little.
- Numbers: see 0.2.
- Relevance: supports the PRD thesis that prompting alone is insufficient. Also supplies the leak-judging design: an LLM judge checks whether the agent's final action reveals the sensitive item, plus a separate helpfulness score (0-3) so leakage can be adjusted to useful outputs only.
- Design implication (benchmark): adopt LRh-style reporting. A system that deletes everything has 0% leak; reporting leak only over outputs that keep the public items (our "summary usefulness") prevents that. Resolves part of PRD Q4: use string match for exact secrets plus an LLM judge for paraphrased leaks, as PrivacyLens does.
- Confidence: [verified-in-source]

### P3. Privacy in Action: PrivacyChecker and PrivacyLens-Live (Wang, Yu, Liu, Qin, Zhang, Lin, Zhang, Rajmohan; Microsoft)
- URL: https://arxiv.org/abs/2509.17488 (PDF read). EMNLP 2025 Findings (per arXiv page).
- Claim: a model-agnostic CI module that extracts each information flow (sender, subject, recipient, data type, transmission principle) and judges its appropriateness cuts leakage; the live MCP/A2A version of PrivacyLens exposes higher risk than the static one.
- Numbers: abstract "privacy leakage from 36.08% to 7.30% on DeepSeek-R1 and from 33.06% to 8.32% on GPT-4o"; Table 1 (PrivacyLens leak rate, GPT-4o): helpfulness 2.69 -> 2.45. The other Table 1 rows did not extract cleanly. The ablation that matters: verbalising the flows (Table 2) is what helps.
- Relevance: a drop-in design for our LLM context check (stage 3). It also shows that static evaluation under-states risk, which matters because OTR-Bench is static JSONL.
- Design implication (cue detector / implicit check): make the implicit-sensitivity prompt output a CI tuple with an explicit `recipient = notes readers` and `transmission_principle = persisted meeting notes`, then decide. (benchmark) Add a live/streaming run mode in the harness (the I2 sweep bug in WORK_SPLIT is the static-harness problem in miniature).
- Confidence: [verified-in-source] for the GPT-4o row; other rows not aligned.

### P4. 1-2-3 Check: Enhancing Contextual Privacy in LLM via Multi-Agent Reasoning (W. Li, Sun, Guan, Zhou, Sap; CMU)
- URL: https://arxiv.org/abs/2508.07667 (PDF v3 read; Table 2 rendered). IASEAI'26.
- Claim: Extractor -> Checker -> Executor agents reduce ConfAIde Tier 4 meeting-summary leakage; ablation over information-flow topologies shows "upstream detection mistakes cascade into downstream leakage".
- Numbers (Table 2, GPT-4o, Leaks Secret / Omits Public / Leaks-or-Omits, %): single agent 23.0 / 12.0 / 26.3; **single agent + CoT 2.0 / 32.5 / 34.0**; three agents "Annotate Private" 5.0 / 20.0 / 24.5; three agents Annotate Private without transcript 8.5 / 10.0 / **17.5** (best composite). LLaMA-3.1-70B: single 29.5 / 23.5 / 48.5; single + CoT 3.0 / 27.5 / 29.5; three agents Public Only 3.0 / 19.5 / **20.5**.
- Reading of the abstract's "18% on ConfAIde": 23.0 -> 5.0 is **18 absolute points versus the non-CoT single agent**. It is not a win over single-agent CoT on leakage (2.0); the pipeline wins on the composite (CoT's composite 34.0 is worse than the plain prompt's 26.3). (Draft B surfaced this.)
- Limitations text: overhead "may be impractical" for "streaming meeting transcripts".
- Metrics defined: Leak_s, Public_s per stage, Q_s = (100 - Leak_s) + Public_s in [0, 200].
- Relevance: closest published pipeline-vs-prompt comparison on our scenario, without time, streaming or retroactive cues. It also supplies the **strong prompting baseline** our B arm lacks (CI-style CoT).
- Design implication (benchmark + pipeline): (1) add B+ = CI-aware CoT / extract-then-judge prompt and judge it on leak AND omission; (2) log per-stage leakage (PII, cue, state machine, LLM check) to diagnose I1; (3) cite as prior art - our novelty is time and retroaction, not decomposition.
- Confidence: [verified-in-source]

### P5. Contextual Integrity in LLMs via Reasoning and Reinforcement Learning (Lan, Inan, Abdelnabi, Kulkarni, Wutschitz, Shokri, Brinton, Sim)
- URL: https://arxiv.org/abs/2506.04245 (PDF v4 read). NeurIPS 2025 (per search listing).
- Claim: RL on about 700 synthetic examples teaches CI reasoning that transfers to PrivacyLens; also evaluated on ConfAIde.
- Numbers (Table 3, PrivacyLens, rendered; LR %, baseline -> + CI-CoT -> + CI-RL): Qwen2.5-7B-IT **50.3 -> 44.8 -> 33.7**; Qwen2.5-14B 52.9 -> 42.8 -> 33.9; Mistral-7B 47.9 -> 28.8 -> 31.2; Llama-3.1-8B 18.2 -> 21.3 -> 18.5 (baseline is low because it is unhelpful: helpfulness 1.05, adjusted rate ALR 38.9 -> 31.5 -> 29.4). Frontier with CI-CoT only: Claude 3.7 S-T 32.0 -> 20.1; Gemini 2.5 Pro 37.3 -> 25.3. Sec. 1: "by up to 40%" (relative or absolute not checked). ConfAIde: only Tiers 1-2 human-correlation numbers seen (Table 5).
- Relevance: our local LLM is a 3B-7B Ollama model (qwen2.5). A 7B baseline leaks about half the time on PrivacyLens, and even after RL 7B-14B models still leak 31-34%. The implicit check in C inherits that ceiling; report at least two LLM sizes.
- Design implication (LLM context check): out of scope for 3 hours (no training), but log as future work F6: fine-tune or distill the context check on synthetic CI data. Near term: few-shot CI-tuple prompt (see P3).
- Confidence: [verified-in-source] for Table 3; ConfAIde Tier 4 result not seen.

### P6. CI-Work: Benchmarking Contextual Integrity in Enterprise LLM Agents (Fu, Qin, Zhang, Lin, Wutschitz, Sim, Rajmohan, Zhang; Microsoft)
- URL: https://arxiv.org/abs/2604.21308 (PDF read, April 2026); ACL 2026 Industry Track, pp. 1483-1508 (https://aclanthology.org/2026.acl-industry.103/ opened).
- Claim: in dense enterprise retrieval, "violation rates range from 15.8%-50.9%, with leakage reaching up to 26.7%"; "higher task utility often correlates with increased privacy violations"; bigger models or more reasoning do not fix it.
- Relevance: enterprise inputs "from emails to meeting transcripts". The utility-privacy tension is the same trade-off we pay with the hold buffer and over-redaction.
- Design implication (benchmark): include a dense-context condition (long transcript with several distractor private items), because per-snippet 40-item benchmarks hide density effects. Conclusion "move toward context-centric architectures" supports our structural thesis rhetorically.
- Extra number (Table 2, GPT-5, leak / violation / conveyance %): no defence 11.21 / 27.83 / 93.04; Prompt Defense 8.96 / 21.31 / 81.01; CI-CoT 8.95 / 22.13 / 84.90. Prompt-level mitigation still leaves a >20% violation rate and costs conveyance.
- Confidence: [verified-in-source] for Table 2 (text extraction); synthetic data, per its own disclaimer.

### P7. Dou et al., Reducing Privacy Risks in Online Self-Disclosures with Language Models
- URL: https://arxiv.org/abs/2311.09538 (PDF v3 read). ACL 2024.
- Claim: 19-category self-disclosure taxonomy, 4.8K annotated spans, fine-tuned detector with "over 65% partial span F1", plus an "abstraction" task ("Im 16F" -> "I'm a teenage girl"). HCI study: "82% of participants viewing the model positively".
- Relevance: the nearest published implicit-sensitive-content detector with span-level labels and a user study. Social-media text, not speech, and 65% span F1 is a ceiling reminder for the implicit class.
- Design implication (state machine, PENDING_CONFIRM): offer abstraction as an intermediate output ("[health information]" or "a personal matter") instead of delete-or-keep. It keeps summary usefulness up and is a candidate fourth system or an ablation.
- Confidence: [verified-in-source] (abstract); dataset access is restricted.

---

## 2. Streaming and simultaneous ASR

### P8. Turning Whisper into Real-Time Transcription System (Macháček, Dabre, Bojar)
- URL: https://arxiv.org/abs/2307.14743 (PDF read). IJCNLP-AACL 2023 demo (venue from my memory, not checked in the PDF).
- Claim: LocalAgreement confirms the longest common prefix of consecutive hypotheses; Whisper-Streaming reaches "3.3 seconds latency on average for English ASR on the European Parliament" (abstract).
- Numbers (Sec. 5): "with 1 second MinChunkSize, the average latency is 3.3 seconds for English, 4.4 seconds for German and 4.8 seconds for Czech, while the WER is by 2% higher than in the offline mode for English and German, and by 6% higher for Czech". Table 1 (one document, 10 runs, 0.1 s chunk): A40 no VAD WER 5.8 +/- 0.9, latency 2.85 +/- 0.45 s; L40 with VAD WER 5.0, latency 3.96 s. Server GPUs (A40/L40), fluent single-speaker parliament speech; no laptop figure.
- Relevance: this is PRD's "confirmed text" emit point. The confirm delay (seconds) is small relative to a 30-60 s hold buffer, so ASR confirmation latency is not the bottleneck; the hold buffer is.
- Design implication (hold buffer / ingest): run the cue regex on both the unconfirmed hypothesis and the confirmed text; a cue ("off the record") caught from the hypothesis a few seconds earlier lets the state machine flip before the neighbouring words are confirmed. Hold time must be counted from confirmation, so effective delay = ASR confirm delay + hold.
- Confidence: [verified-in-source]

### P9. CUNI IWSLT 2025 submission, source of SimulStreaming (Macháček, Polák)
- URL: https://arxiv.org/abs/2506.17077 (PDF read). IWSLT 2025.
- Claim: Whisper + AlignAtt policy in a Whisper-Streaming-style interface ("We name the implementation SimulStreaming"); proposes a latency measure (ASR Latency with Continuous Levenshtein Alignment).
- Numbers: Table 7 (ACL6060 English dev, computationally-unaware, ms): chunk 0.05 s -> 14.22% WER at 494 ms; chunk 0.25 -> 13.10% WER at 754 ms; chunk 0.5 -> 13.06% at 1262 ms; chunk 2.0 -> 12.69% at 2143 ms. Whisper large (1.6B) + EuroLLM 9B is stated to need "feasible hardware resources" for real time.
- Relevance: quantifies the latency-accuracy curve. Going from about 0.5 s to 2.1 s latency buys about 1.5 points of WER.
- Design implication (Q1 in PRD 2.6): choose the low-latency operating point; extra ASR delay is better spent in the hold buffer, where it can also be used for privacy. Note the hardware caveat: these numbers are computation-unaware, so they do not answer "fast enough on the target laptop"; that needs a real-time-factor measurement on the team machine.
- Confidence: [verified-in-source] for Table 7; no single standalone SimulStreaming paper was found, so cite the IWSLT paper plus the repo.

### P10. Streaming Sequence-to-Sequence Learning with Delayed Streams Modeling (Zeghidour et al., Kyutai)
- URL: https://arxiv.org/abs/2509.08753 (PDF read).
- Claim: decoder-only streaming ASR/TTS; DSM-ASR (2.6B) with a 2.5 s delay averages 6.4% WER on the OpenASR Leaderboard short-form set (leaderboard best quoted as 6.1%) and is "the only streaming model among top ASR systems"; delay can be conditioned at inference.
- Relevance: a streaming-native alternative to Whisper-style re-decoding, with a controllable delay. 2.6B on a laptop is not established.
- Design implication (ingest / Q1): optional fallback if Whisper-Streaming is too slow; the delay knob maps onto the same trade-off as the hold-buffer sweep (F5). Not required for the 3-hour plan.
- Confidence: [verified-in-source] for 6.4% and the 2.5 s default; laptop feasibility not examined.

### P11. WhisperRT (formerly "CarelessWhisper"): Turning Whisper into a Causal Streaming Model (Krichli, Raj, Keshet)
- URL: https://arxiv.org/abs/2508.12301 (PDF v2 read; title changed between versions).
- Claim: LoRA-fine-tuned causal encoder gives low-latency streaming; "experiments on low-latency chunk sizes (less than 300 msec)" show it beats non-fine-tuned streaming approaches "in most cases". Notes that Whisper-Streaming and Simul-Whisper "require padding inputs to 30 seconds at every step".
- Relevance: confirms the efficiency weakness of the LocalAgreement approach on CPU/laptop hardware. No numbers extracted.
- Design implication: if Q1 fails, there are three alternatives (SimulStreaming, DSM, WhisperRT). Do not build around any single one.
- Confidence: [abstract-only]

### P12. Careless Whisper: Speech-to-Text Hallucination Harms (Koenecke, Choi, Mei, Schellmann, Sloane)
- URL: https://arxiv.org/abs/2402.08021 (PDF read). ACM FAccT 2024.
- Claim (abstract): "roughly 1% of audio transcriptions contained entire hallucinated phrases or sentences", "38% of hallucinations include explicit harms"; hallucinations are more frequent for speakers with longer non-vocal durations (aphasia vs control).
- Relevance: our design explicitly creates silence in the stream (OFF-state suppression, muted tracks). Hallucination on silence can fabricate text, including a fake cue ("off the record") or fabricated private-sounding content. The study used mid-2023 Whisper; newer versions may differ (a news article quotes the lead author to that effect; not in the paper).
- Design implication (ingest + cue detector): VAD-gate audio before ASR; require cue detection to run on speech-active segments with ASR confidence; never let OFF-period silence reach the ASR. Add hallucination-injected silence cases to the false-alarm class.
- Confidence: [verified-in-source]

---

## 3. Speaker diarization (streaming, multi-speaker, per-track vs mixed)

### P13. Streaming Sortformer: Speaker Cache-Based Online Speaker Diarization with Arrival-Time Ordering (Medennikov, Park, et al., NVIDIA)
- URL: https://arxiv.org/abs/2507.18446 (PDF read). arXiv July 2025 (venue not checked).
- Claim: Arrival-Order Speaker Cache stores frame embeddings per speaker in arrival order; online diarization at 0.32 s to 1.04 s declared input latency (Table 2: RTF 0.093 at 1.04 s and 0.180 at 0.32 s on an RTX 6000 Ada GPU).
- Numbers (Table 1, rendered; DER %, with post-processing): DIHARD III "all" 19.02 (10 s), 18.97 (1.04 s), 19.32 (0.32 s); CALLHOME-part2 "all" 10.09 / 10.79 / 11.50. Without post-processing, DIHARD III all 19.89 (1.04 s), 20.25 (0.32 s). Same-latency comparators at 1 s: LS-EEND 19.61, EEND-GLA-Large 20.73 (DIHARD III all). The model has "a constraint of 4 speakers by design".
- Relevance: the strongest published online diarizer for mixed audio. Needs a GPU for the quoted RTF, and caps at 4 speakers.
- Design implication (ingest, WORK_SPLIT task 6): this is only a fallback path; with LiveKit we have per-participant tracks, so speaker identity is known from the track and diarization is not needed for the live demo. Keep pyannote/Sortformer for the mixed-audio import path.
- Confidence: [verified-in-source]. DER about 19% on DIHARD III means roughly one frame in five misattributed on hard audio, so scope ownership should be scored with oracle and with diarized labels.

### P14. Leveraging Self-Supervised Learning for Speaker Diarization (Han, Landini, Rohdin, Silnova, Diez, Burget; BUT; the DiariZen paper)
- URL: https://arxiv.org/abs/2409.09408 (PDF read). Code: https://github.com/BUTSpeechFIT/DiariZen (named in the abstract).
- Claim: WavLM + Conformer local EEND in the pyannote pipeline beats the Pyannote baseline on far-field AMI, AISHELL-4, AliMeeting.
- Numbers: Table (100% data, collar 0 s) DER: AMI 15.4, AISHELL-4 11.7, AliMeeting 17.6, macro 14.9. Text: relative DER reductions vs Pyannote3 of 26.6%, 15.8%, 22.8% on AMI, AISHELL-4, AliMeeting.
- Relevance: best open offline/batch diarizer for meeting audio; offline, so not for the live path.
- Design implication (ingest): use only to post-hoc label imported recordings (QMSum/AMI) or compare against per-track labels. Note it's a toolkit result from 2024; I did not verify the newer DiariZen releases.
- Confidence: [verified-in-source]

### P15. Powerset multi-class cross entropy loss for neural speaker diarization (Plaquet, Bredin)
- URL: https://arxiv.org/abs/2310.13025 (PDF read). Venue (Interspeech 2023) from memory, not checked in the PDF.
- Claim: replacing multi-label with powerset classification improves overlapped-speech handling and removes the detection threshold hyperparameter; this is the basis of pyannote.audio 3.x segmentation.
- Relevance: explains why overlap (two people speaking, one saying "off the record") is the diarization failure that matters for scope ownership.
- Design implication (state machine): overlapping speech means a cue spoken by A may be attributed to B in mixed-audio mode, so "whose OFF is it" is ambiguous; per-track input avoids this.
- Confidence: [abstract-only] for the claim; pyannote 4/community-1 is only known to me from a search result (secondhand: the pyannote Hugging Face page lists community-1, CC-BY-4.0, access gated).

### P16. Summary of the NOTSOFAR-1 Challenge (Abramovski, Vinnikov, Shaer, Kanda, Wang, Ivry, Krupka; Microsoft)
- URL: https://arxiv.org/abs/2501.17304 (PDF v2 read).
- Claim: 315 real meetings, 30 rooms, best systems pipeline diarization + separation + ASR.
- Numbers (Tables 2 and 3, NOTSOFAR-1 eval): tcpWER of the best single-channel system 22.2%, baseline 45.8%; best multi-channel 10.8%, baseline 85.3%. tcpWER penalises diarization errors as well as word errors.
- Relevance: gives a realistic ceiling on mixed far-field meeting attribution. The gap between 10.8% and 22.2% shows how much the mic setup matters. Our target setting (individual LiveKit tracks) is closest to the close-talk (AMI IHM) condition, not NOTSOFAR.
- Design implication (benchmark): tag each benchmark transcript with its source condition (per-track vs mixed) and report leak by condition. I found no recent paper that directly compares per-participant-track vs mixed-audio diarization for meetings; the only items I saw are older (headset crosstalk, NIST RT-04S, secondhand through a search summary) and I cannot cite them as verified. The practical risk with per-track audio is crosstalk bleed from loudspeakers or nearby mics, which is not covered here.
- Confidence: [verified-in-source] for tables; per-track-vs-mixed comparison [not found].

---

## 4. Selective redaction, unlearning, speaker-level opt-out

### P17. Go Beyond Your Means: Unlearning with Per-Sample Gradient Orthogonalization (OrthoGrad; Shamsian, Shaar, Navon, Chechik, Fetaya)
- URL: https://arxiv.org/abs/2503.02312 (PDF v2 read; "Under Review" on arXiv).
- Claim: includes an ASR speaker-unlearning benchmark: Whisper-Tiny + LibriSpeech, forget one speaker, LoRA.
- Numbers (Table 2, WER %, mean of 5 speakers): Original: retain 9.99, unlearn 11.12, held-out audio of the same speaker 10.06, test 11.08. OrthoGrad: retain 12.11, unlearn 96.24, speaker-heldout 98.53, test 13.98. NegGrad+ and SCRUB wreck test WER (85.90, 100.00); GDR-GMA test 32.52.
- Relevance: shows model-level speaker forgetting is feasible but costs general accuracy (test WER 11.08 -> 13.98) and was tested on a tiny model and an audiobook corpus, with the speaker in the training set.
- Design implication (F2 "speaker-level opt-out"): unlearning is the wrong tool for runtime consent. A meeting opt-out is a session decision and can be enforced exactly by dropping that participant's LiveKit track (or masking that speaker's segments), with zero leak by construction and no model change. Reserve unlearning for "remove me from the model" requests, which is a different requirement.
- Confidence: [verified-in-source]

### P18. "Alexa, can you forget me?" Machine Unlearning Benchmark in Spoken Language Understanding (UnSLU-BENCH; Koudounas, Savelli, Giobergia, Baralis)
- URL: https://www.isca-archive.org/interspeech_2025/koudounas25c_interspeech.html (page read). Interspeech 2025, pp. 1768-1772.
- Claim: first SLU unlearning benchmark, four datasets / four languages, eight methods, speaker-level removal as the right-to-be-forgotten proxy, with a combined efficacy-utility-efficiency metric.
- Relevance: gives the evaluation vocabulary (efficacy, utility, efficiency) if we ever claim speaker-level forgetting.
- Confidence: [abstract-only]; per-method results not seen.

### P19. Erasing Your Voice Before It's Heard: Training-free Speaker Unlearning for Zero-shot TTS (TruS; Lee, Shin, Lee)
- URL: https://arxiv.org/abs/2601.20481 (PDF read, January 2026).
- Claim: inference-time activation steering suppresses generation of opt-out speakers, including unseen ones.
- Relevance: it is about synthesis, not recognition. Included only because it shows the field framing speaker opt-out as inference-time control rather than retraining, which matches our gate-at-runtime approach. Do not cite as ASR evidence.
- Design implication: none directly; supports the argument in P17 that opt-out should be an inference-time control.
- Confidence: [abstract-only]

---

## 5. PII and sensitive-content detection in speech and transcripts

### P20. Beyond Clean Text: A Benchmark for PII/PHI Detection Robustness to ASR Transcription Error (Harrison, Manzelli)
- URL: https://neurips.cc/virtual/2026/177010 (poster page read; NeurIPS 2026 workshop "Privacy in the Era of Large Opaque Models"). I did not find or open an arXiv version.
- Claim: tests three open-source detectors (zero-shot NER, generative tagging, fixed-taxonomy classification) on ground-truth text vs transcripts from two ASR systems with WER 3.17% and 17.49%; "architecture, not ASR quality alone, is the stronger predictor"; releases a 545-clip benchmark.
- Relevance: Presidio-style PII rules and our LLM checks will both see ASR-noisy text.
- Design implication (benchmark + Presidio stage): evaluate PII detection on ASR output, not on the clean strings in OTR-Bench; add a noisy-ASR variant of the benchmark (see Section 9).
- Confidence: [abstract-only]

### P21. DialogPII: A multilingual dataset of synthetic dialog transcripts to detect personal information (Roller et al., 16 authors)
- URL: https://arxiv.org/abs/2606.30312 (landing page read, June 2026).
- Claim: synthetic LLM-generated dialogues, converted with TTS, transcribed with Whisper, annotated by projection + manual correction; 8 scenarios, 19 entity types, 11 languages. The method (TTS then ASR) is the reusable idea.
- Relevance: a recipe for building audio-realistic benchmark data cheaply, with ASR errors included.
- Design implication (benchmark): create OTR-Bench-ASR by running the 40 text snippets through TTS + Whisper, keeping the same labels via alignment. Number of dialogs not stated on the page.
- Confidence: [abstract-only]

### Gap: speech-act detection of "off the record"-style cues
I searched for work on detecting explicit confidentiality requests ("off the record", "don't write this down", "strike that") as speech acts and found none. Related but not the same: KIT's "Can a Large Language Model Keep My Secrets? A Study on LLM-Controlled Agents" (ACL SRW 2025; seen only as a search result, secondhand) on access-control requests; a medRxiv study of GPT-3.5 on confidential content in adolescent notes (sensitivity 97%, specificity 18%, from the search snippet, secondhand). Neither addresses spoken scope-setting. I therefore treat the cue detector and retroactive removal as novel, unsupported by prior evaluation, and the specificity warning (high recall, low specificity for LLM confidentiality flags) as a plausible risk for our false-alarm class, not an established result.

---

## 6. Meeting-assistant consent, legal and user-study evidence

All items in this section are news or law-firm summaries; treat claims as allegations, not findings.

### P22. Brewer v. Otter.ai (N.D. Cal., filed Aug. 2025)
- URLs opened: https://oecd.ai/en/incidents/2025-08-16-0b41 (read); NPR article https://www.npr.org/2025/08/15/g-s1-83087/otter-ai-transcription-class-action-lawsuit (fetch timed out; content known only from a search-result summary).
- Claim (as alleged): Otter Notetaker recorded conversations without consent from all participants, including non-users, and used recordings to train its AI; statutes cited are ECPA and the California Invasion of Privacy Act (OECD page). Case number 5:25-cv-06911-EKL (N.D. Cal., Judge Eumi K. Lee), consolidation on 2025-10-22 and a partial denial of Otter's motion to dismiss on 2026-08-13 appear only in a law-adjacent blog (https://blog.buildbetter.ai/ai-notetaker-lawsuits-2026-how-to-record-meetings-legally/, opened) that cites a third source and no docket; treat the 2026 ruling as unverified (draft B found the same blog).
- Relevance: the headline harm is the non-user participant who never agreed. A local, bot-less design is outside this fact pattern but participants still have not consented to being transcribed.
- Design implication (demo / consent): a visible "recording" indicator and a consent roll call (F3) are the minimum story for the slides; state "local only, no training use".
- Confidence: [secondhand]

### P23. Cruz v. Fireflies.AI Corp. (C.D. Ill., Dec. 2025)
- URL: https://www.dataprivacyandsecurityinsider.com/2025/12/lawsuit-alleges-fireflies-ai-corp-illegally-collects-biometric-data-from-virtual-meetings/ (read).
- Claim (as alleged): Fireflies' "speaker recognition" generates voiceprints of every participant, including non-users, in violation of the Illinois BIPA (no notice, written consent or published retention policy). Court/date (C.D. Ill., 2025-12-18; a second suit, Fricker, N.D. Ill., March 2026) come from the same blog, not the article, which says only "an Illinois federal court".
- Relevance: directly supports PRD non-goal "no speaker identification or voiceprints". Diarization by embedding clustering is the technique accused here.
- Design implication (ingest): in the LiveKit path, derive speaker labels from track/participant identity (no embeddings). If mixed-audio diarization is added, use clustering only for session-local labels, store no embeddings, and say so.
- Confidence: [secondhand]

### P24. Kolmogorov Law / Pollfish survey on AI notetakers (July 2026)
- URL: https://krdo.com/stacker-business-economy/2026/07/16/ai-notetakers-have-sat-in-on-1-in-3-us-workers-meetings-but-only-a-third-say-they-were-asked-first/ (read).
- Claim: 500 employed U.S. adults, fielded July 8, 2026. 33.4% say an AI notetaker has been in their meetings. Among the 167 exposed: 34.7% always asked, 36.5% sometimes, 25.1% never asked, 3.6% found out afterward. Margin about 4.4% (full sample), 7.6% (subsample).
- Caveats: commissioned by a law firm, not peer-reviewed, self-reported. I found no peer-reviewed user study (arXiv, CHI) of notetaker consent through search; that is a gap, not a negative finding.
- Relevance: supports the PRD 1.1 sentence "surveys showing most people aren't asked before a notetaker joins", but only as industry evidence ("65.3% inconsistent or absent" is derived from 167 respondents).
- Design implication (PRD 1.9 / slides): cite it as an industry survey with sample size; do not call it a study.
- Confidence: [verified-in-source] (the article), but the underlying survey instrument not seen.

### Additional prior art absorbed from draft B (each re-opened by me)

### P25. Trustera: A Live Conversation Redaction System (Gouvea, Dadgar, Jalalvand, ... Stern; Interactions LLC)
- URL: https://arxiv.org/abs/2303.09438 (PDF read, March 2023).
- Claim: "the first functional system that redacts personally identifiable information (PII) in real-time spoken conversations"; audio masking starts when the customer begins speaking a PII entity (payment card, SSN) and is "used by thousands of agents".
- Relevance: the closest published live-redaction pipeline (ASR -> NLU -> audio mute). PII only; no user-signalled scope, no retroactive request, no implicit sensitivity.
- Design implication (hold buffer, otr/pii.py): run Presidio over the hold-buffer window, not per segment, so identifiers split across segments are caught; cite as prior art for the live-redaction shape. Our novelty claim must read "among the papers I found".
- Confidence: [verified-in-source] (abstract and introduction); latency/accuracy numbers not read.

### P26. AirGapAgent: Protecting Privacy-Conscious Conversational Agents (Bagdasarian et al.)
- URL: https://arxiv.org/abs/2405.05175 (PDF read). CCS 2024.
- Claim (abstract text): a single-query hijacking attack "reduces its ability to protect user data from 94% to 45%" for a prompted Gemini Ultra agent, "while an AirGapAgent achieves 97% protection". Data minimisation before the agent sees the data beats instruction.
- Relevance: the strongest published analogue to "removal before generation beats instruction to the generator" (our hold buffer + committed-only summariser input). It is about adversarial hijacking, not meeting speech.
- Design implication (pipeline): make the air-gap an invariant and test it: summariser input is built only from committed segments; no "[REDACTED: topic]" markers that leak the topic.
- Confidence: [verified-in-source] (abstract); body not read.

### P27. Defeating Prompt Injections by Design (CaMeL; Debenedetti et al.)
- URL: https://arxiv.org/abs/2503.18813 (abstract read). "solving 77% of tasks with provable security (compared to 84% with an undefended system) in AgentDojo".
- Relevance, by analogy only: deterministic guarantees where possible, LLM only where judgment is unavoidable. Our guarantees hold for explicit cues and scope, not for "is this sentence sensitive?".
- Confidence: [abstract-only]

### P28. Multi-party and multi-user CI benchmarks: MuPPET, PiSAs, PrivacyAlign
- URLs (abstract pages opened): https://arxiv.org/abs/2606.23217 (MuPPET: models "leak far more in group settings than one-to-one tests suggest"; party-tracking unsolved); https://arxiv.org/abs/2607.05318 (PiSAs: system design improves CI compliance but "incorrect LLM judgments remain the main bottleneck"); https://arxiv.org/abs/2606.21710 (PrivacyAlign: 1,350 samples, 3,516 annotations, 599 annotators; LLM judges conditioned on human annotations and explanations are more reliable).
- Relevance: audience tracking (who reads the notes) is the open problem for multi-party; LLM judge reliability is open. No numbers used.
- Design implication (benchmark): give the leak judge 3-5 human-labelled examples with explanations per case type; check whether MuPPET data is reusable for implicit items (licence not checked).
- Confidence: [abstract-only]

### P29. Leaky Thoughts: Large Reasoning Models Are Not Private Thinkers (Green, Gubri, Puerto, Yun, Oh)
- URL: https://arxiv.org/abs/2506.15674 (PDF header and abstract only). EMNLP 2025 (per B; not checked by me).
- Claim: reasoning traces frequently contain sensitive user data.
- Design implication (audit log): store span IDs and hashes, never redacted text or model reasoning; add a test that greps all outputs and logs for planted secrets.
- Confidence: [abstract-only]

### P30. Statistics for small evals: Miller (arXiv 2411.00640) and Bowyer et al. (arXiv 2503.01747)
- URLs: https://arxiv.org/abs/2411.00640 (PDF read; Table 4 caption: clustered standard errors "can be over 3X larger than naive standard errors"; recommends cluster counts next to question counts and paired comparisons); https://arxiv.org/abs/2503.01747 (PDF read; CLT and bootstrap intervals poorly calibrated at small N; Bayesian and Wilson intervals reach nominal coverage; ICML 2025).
- Relevance: 40 items, 20 in a 5x4 grid.
- Design implication (benchmark reporting; recomputed by me and matching B): Wilson 95% intervals (0/40 -> 0.0-8.8%; 2/40 -> 1.4-16.5%; 5/40 -> 5.5-26.1%; 12/40 -> 18.1-45.4%), exact McNemar for paired system comparison (b=9, c=2 gives p = 0.065), cluster counts reported, about 62 items per arm to detect 30% vs 10% unpaired. Do not headline a percentile bootstrap at n=40 (it gives [2.5, 32.5] points for that same example although the exact test is not significant).
- Confidence: [verified-in-source]; numbers marked "recomputed" are mine.

---

## 7. Gaps the literature does not cover (our contribution zone)

1. Retroactive requests ("strike that"): no benchmark or system in the papers above (searches limited; absence of evidence, not proof).
2. Time: no paper has a hold/commit delay. Streaming ASR work (P8-P11) treats latency as a cost, never as a safety budget.
3. Scope over time: ConfAIde Tier 4 secrets are static per scenario; no scope with explicit or implicit end.
4. Speaker ownership of a privacy signal: not studied.
5. Spoken-cue detection under ASR errors: not studied (P20 is closest, for PII).
6. "Strike that" as repair vs retraction (disfluency/repair literature, claimed by draft B, abstract-level only; I did not verify it).

---

## 8. Top 5 design changes this suggests

1. **Fair baselines and matched information (P4, P5, P3).** Add B+ = CI-tuple extract-then-judge or CI-CoT prompt. Run B and B+ both with hindsight (offline) and causal-with-lag, so retroactive cases are not trivially easy for B. Claim only "C vs best of B+ at matched delay". A plain CoT prompt reached 2.0% Tier 4 leak on GPT-4o but omitted 32.5% of public content; judge on the composite.
2. **Per-stage leak logging with leak and omission together (P4, P1, P2, P6).** Leak_s, Public_s, Leaks-or-Omits after each stage; 10-run worst case for stochastic LLM stages; helpfulness-adjusted leak; abstraction as a fourth output mode (P7).
3. **Track identity, not voiceprints; opt-out by dropping the track (P17, P23).** Zero leak by construction, avoids the BIPA fact pattern, and replaces F2's unlearning idea (model-level forgetting cost test WER 11.08 -> 13.98 and was tested on a speaker seen in training).
4. **Front-end robustness (P8, P12, P20, P25).** VAD-gate silence before ASR; run cue regex on the hypothesis plus confirmed text; count hold time from confirmation; run Presidio on the hold window; add an ASR-noise benchmark condition.
5. **Privacy-of-the-privacy-layer invariants (P26, P29).** Summariser sees committed segments only (air gap, no topic markers); audit log holds IDs/hashes, never redacted text or reasoning; removal cascades to every derived artifact with provenance and regeneration; no embeddings persisted.

## 9. New open questions for PRD 2.6

- **Q5.** What is B+ and does it run with hindsight or causal lag? This decides whether the hypothesis is testable (draft B's strongest objection; I agree).
- **Q6.** Is an OFF scope owned by the speaker or by the room, and how does the benchmark label that with per-track input?
- **Q7.** Cue recall as a function of ASR WER and hallucination: how often is "off the record" or "strike that" mis-transcribed, and does fuzzy matching on the hypothesis stream fix it?
- **Q8.** How do we define and score "by meaning" retroactive targets, separately from leak rate; how often is "strike that" a repair, not a retraction?
- **Q9.** Is the local 3B/7B model good enough for the CI-tuple check (7B baselines leak about 50% on PrivacyLens), or must the implicit class be restricted to a closed list with keyword-gated confirmation? Also: what is the empirical delay between a sentence and its retraction, which should set the 30 s vs 60 s hold (nothing measured in the literature I found)?

## 10. Benchmark ideas

- Label the 20 ConfAIde items "contextual-confidential", cluster by secret, and add true-implicit items from elsewhere.
- OTR-Bench-ASR: the 40 snippets through TTS then Whisper (DialogPII recipe, P21), plus cue-corruption variants.
- Per-stage Leak_s / Public_s / Q_s; leak vs omission scatter; 10-run worst case; judge validation on at least 100 hand-labelled (output, span) pairs, reporting kappa and accuracy (PrivacyLens protocol: 153 pairs, kappa 0.82, accuracy 0.92 for a Mistral-7B few-shot judge).
- Gold private spans for all 40 items, paraphrase-aware judging (string match missed 16/200 in ConfAIde).
- Dense-context condition (P6); silence-hallucination and false-cue cases; retraction-vs-repair pairs; speaker-ownership cases; live streaming mode with real ticks (I2); abstraction variant.
- Report with Wilson intervals, exact McNemar, cluster counts (P30).

## 11. What I could not verify

- PrivacyLens Table 2 raw LR values (24.54 / 39.15): only the abstract's 25.68 / 38.69 (adjusted) is confirmed by two sources; the raw column comes from the same garbled extraction in both drafts.
- Whether CI-RL's "up to 40%" is relative or absolute; ConfAIde Tier 4 results of CI-RL; PrivacyChecker rows other than GPT-4o (and DeepSeek-R1 from the abstract).
- pyannote 4 / community-1 claims (vendor page via search only); newer DiariZen releases; offline Sortformer (arXiv 2409.06656) claims.
- Any peer-reviewed user study of notetaker consent; any paper on per-track vs mixed diarization for meetings; any prior work on retroactive redaction or spoken privacy-cue speech acts; the disfluency/repair literature draft B cites.
- Primary court records for Brewer v. Otter.ai and the Fireflies suits (no docket seen; the 2026 ruling and Fricker suit are single-blog claims). Cal. Penal Code 632 text.
- Peer-review status of CI-RL (NeurIPS 2025 per search listing), Beyond Clean Text and DialogPII (no proceedings version checked); venues for Whisper-Streaming (IJCNLP-AACL 2023) and the powerset paper (Interspeech 2023) are from memory.
- Laptop-level real-time factors for Whisper-Streaming, SimulStreaming, DSM-ASR: the cited numbers are server-GPU or computation-unaware.
- Whether Bowyer et al.'s claim of 92.5% CLT coverage at N=100 (clustered) holds: draft B's number; I could not find it in the text.
