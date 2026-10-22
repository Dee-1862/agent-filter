# Research draft A: literature for the OTR meeting agent

Author: Researcher A. Date of search: 2026-10-22. Scope: PRD 1.1-1.7, 2.5-2.6, WORK_SPLIT.md.

Confidence tags: **[verified-in-source]** = I downloaded the paper PDF or opened the publisher page and read the text/table quoted. **[abstract-only]** = I saw only the abstract or a landing page. **[secondhand]** = news, law-firm blog, or search-result summary; I did not read the primary document.

Caveat on tables: I extracted PDFs with `pdftotext -layout`. Some multi-row tables came out interleaved (PrivacyLens Table 2, Streaming Sortformer Table 1). Where that happened I say so and give only what the surrounding prose also supports.

---

## 0. Check of PRD 1.4 claims against the papers

### 0.1 ConfAIde (arXiv 2310.17884; ICLR 2024 spotlight)

PRD says: "GPT-4 and ChatGPT leak ... (reported 39% and 57%)". **Confirmed, with one precision.**

- Abstract (v2, read in PDF): "even the most capable models such as GPT-4 and ChatGPT reveal private information in contexts that humans would not, 39% and 57% of the time, respectively".
- Introduction (PDF text): "GPT-4 and ChatGPT reveal secrets 22% and 93% of the time in Tier 3, and flow information to inappropriate actors 39% and 57% of the time in Tier 4, even though they are directly instructed to preserve privacy."
- Table 4 (Tier 4, models as meeting assistants, lower is better), the block I attribute to the **meeting summary** task (the PDF layout puts the column label oddly; I infer summary vs action item from Sec. 4.4's statement "This leakage is higher in the meeting summary task compared to the personal action item generation task"):

| Metric (Summary block) | GPT-4 | ChatGPT |
|---|---|---|
| Leaks Secret (Worst Case) | 0.80 | 0.85 |
| Leaks Secret (average over 10 runs) | 0.39 | 0.57 |
| Omits Public Information | 0.10 | 0.27 |
| Leaks Secret or Omits Info. | 0.42 | 0.74 |

  The other block (personal action items): Leaks Secret 0.29 / 0.38; Omits Public 0.76 / 0.89; Leaks or Omits 0.89 / 0.96.
- Table 5: chain-of-thought does not help. Tier 4 Leaks Secret GPT-4 0.39 (no CoT) vs 0.40 (CoT); ChatGPT 0.57 vs 0.61. Sec. 4.5: "using chain of thought (CoT) does not improve leakage, in fact it makes the leakage more severe."
- Corrections to add to the PRD: (a) 39%/57% are averages over 10 runs; the worst-case-over-10-runs leak is 80%/85%; (b) the privacy-protecting instruction was already in the prompt; (c) the paper's own composite "Leaks Secret or Omits Info." (0.42 / 0.74 for summaries) is the exact analogue of our leak + over-redaction pair and should be reported alongside leak rate.

### 0.2 PrivacyLens (arXiv 2409.00138; NeurIPS 2024 Datasets and Benchmarks)

PRD says: "25.68% for GPT-4, 38.69% for Llama-3-70B" with privacy-enhancing instructions. **Confirmed with a metric precision.**

- Abstract: "state-of-the-art LMs, like GPT-4 and Llama-3-70B, leak sensitive information in 25.68% and 38.69% of cases, even when prompted with privacy-enhancing instructions."
- Table 2 defines LR = leakage rate and **LRh = leakage rate adjusted to cases with positive helpfulness**. From the (interleaved) table, the 25.68 and 38.69 figures are the **LRh** column under the privacy-enhancing prompt; the unadjusted LR in the same rows reads 24.54 (GPT-4) and 39.15 (Llama-3-70B). The row-to-model alignment in my extraction is garbled, so treat the LR values as probable, but the abstract and Sec. 1 ("GPT-4 still leaks information in 25.68% of cases ... even with privacy-enhancing prompt engineering") confirm the headline.
- Sec. 5 text: with the **basic** prompt GPT-4 leaks 27.23% (LRh), so the privacy prompt buys roughly 1.5 points. Probing accuracy is near-perfect (GPT-4 about 99%) while action-level leakage is about 25%: the judgment-action gap.
- Scale: 493 seeds, 493 vignettes, 493 trajectories, 1,479 probing questions.

### 0.3 Corrections to carry into docs/PRD.md 1.4 / L-001

1. ConfAIde figures are correct; state they are Tier 4 summary leakage averaged over 10 runs, and add the worst-case 80/85 and the 0.42/0.74 leak-or-omit composite.
2. PrivacyLens figures are correct; state they are the helpfulness-adjusted rate (LRh) under the privacy-enhancing prompt, 493 cases.
3. Neither paper evaluates streaming audio, explicit "off the record" cues, or retroactive requests (see Section 7).

---

## 1. Contextual integrity and privacy leakage in LLMs and agents

### P1. ConfAIde: "Can LLMs Keep a Secret?" (Mireshghallah, Kim, Zhou, Tsvetkov, Sap, Shokri, Choi)
- URL: https://arxiv.org/abs/2310.17884 (PDF read). ICLR 2024.
- Claim: LLMs often disclose in contexts where humans would not; leakage gets worse in the higher, more realistic tiers; prompting and CoT do not fix it.
- Numbers: see 0.1. Also: GPT-4's correlation with human privacy expectations drops from 0.8 (Tier 1) to 0.1 (Tier 3) (Introduction).
- Relevance: Tier 4 is our meeting-summary scenario. The failure mode they describe is structural: the summary is addressed to all attendees, so the model cannot reason that an excluded person is among them (Sec. 4.4). Our committed notes have the same property: the "audience" is everyone who can read the notes.
- Design implication (benchmark + state machine): report the paper's three metrics (Leaks Secret, Omits Public, Leaks-or-Omits) for systems A/B/C, and add the 10-run worst case, since leaks are stochastic for LLM-based systems. For the cue detector, since CoT "makes it worse", do not rely on a longer prompt for the implicit check; use a structured, narrow classification.
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
- Numbers (abstract): "privacy leakage from 36.08% to 7.30% on DeepSeek-R1 and from 33.06% to 8.32% on GPT-4o". Which leakage metric and benchmark version these are I did not trace in the body; treat as the authors' headline.
- Relevance: a drop-in design for our LLM context check (stage 3). It also shows that static evaluation under-states risk, which matters because OTR-Bench is static JSONL.
- Design implication (cue detector / implicit check): make the implicit-sensitivity prompt output a CI tuple with an explicit `recipient = notes readers` and `transmission_principle = persisted meeting notes`, then decide. (benchmark) Add a live/streaming run mode in the harness (the I2 sweep bug in WORK_SPLIT is the static-harness problem in miniature).
- Confidence: [verified-in-source] for abstract numbers; body details not checked.

### P4. 1-2-3 Check: Enhancing Contextual Privacy in LLM via Multi-Agent Reasoning (W. Li, Sun, Guan, Zhou, Sap; CMU)
- URL: https://arxiv.org/abs/2508.07667 (PDF v3 read). IASEAI'26.
- Claim: decomposing privacy handling into Extractor -> Checker -> Executor reduces ConfAIde meeting-summary leakage; the ablation over information-flow topologies shows "upstream detection mistakes cascade into downstream leakage".
- Numbers (abstract): "reduces private information leakage (18% on ConfAIde and 19% on PrivacyLens using GPT-4o) while preserving the fidelity of public content". I did not verify whether 18%/19% are absolute points or relative.
- Metrics defined in Sec. 4: Leak_s (percent of transcripts still containing any private info after stage s), Public_s, and composite Q_s = (100 - Leak_s) + Public_s in [0, 200].
- Relevance: it is a published ConfAIde Tier 4 pipeline-vs-single-agent comparison, i.e. the closest prior art to our hypothesis (structure beats one prompt), but without time, streaming, or retroactive cues.
- Design implication (benchmark + pipeline): log per-stage leakage after (1) PII, (2) cue detector, (3) state machine, (4) LLM check. This directly diagnoses I1 (implicit-end heuristic): if the state machine drops spans the cue detector had right, it shows in Leak_s. Cite as prior art in the Related Work slide; our novelty is time and retroaction, not decomposition.
- Confidence: [verified-in-source] (abstract + metric definitions); effect size definition not verified.

### P5. Contextual Integrity in LLMs via Reasoning and Reinforcement Learning (Lan, Inan, Abdelnabi, Kulkarni, Wutschitz, Shokri, Brinton, Sim)
- URL: https://arxiv.org/abs/2506.04245 (PDF v4 read). NeurIPS 2025 (per search listing).
- Claim: RL on about 700 synthetic examples teaches CI reasoning that transfers to PrivacyLens; also evaluated on ConfAIde.
- Numbers: Sec. 1 says leakage on PrivacyLens is reduced "by up to 40%" (relative vs absolute not checked); on ConfAIde the paper reports improved human-correlation for Tiers 1-2 with Qwen2.5-7B (Table 5), no Tier 4 number checked.
- Relevance: our local LLM is a 3B-7B Ollama model (qwen2.5). This is evidence that a 7B model's CI behavior is trainable, and that explicit CI reasoning in the prompt is the first step they take.
- Design implication (LLM context check): out of scope for 3 hours (no training), but log as future work F6: fine-tune or distill the context check on synthetic CI data. Near term: few-shot CI-tuple prompt (see P3).
- Confidence: [abstract-only] plus partial body (Sec. 1 line and Table 5 seen).

### P6. CI-Work: Benchmarking Contextual Integrity in Enterprise LLM Agents (Fu, Qin, Zhang, Lin, Wutschitz, Sim, Rajmohan, Zhang; Microsoft)
- URL: https://arxiv.org/abs/2604.21308 (PDF read, April 2026). The search listing shows an ACL 2026 Industry Track version; I did not open that page.
- Claim: in dense enterprise retrieval, "violation rates range from 15.8%-50.9%, with leakage reaching up to 26.7%"; "higher task utility often correlates with increased privacy violations"; bigger models or more reasoning do not fix it.
- Relevance: enterprise inputs "from emails to meeting transcripts". The utility-privacy tension is the same trade-off we pay with the hold buffer and over-redaction.
- Design implication (benchmark): include a dense-context condition (long transcript with several distractor private items), because per-snippet 40-item benchmarks hide density effects. Conclusion "move toward context-centric architectures" supports our structural thesis rhetorically.
- Confidence: [abstract-only] (abstract read in PDF, no tables checked)

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
- Findings from the text: latency measured is roughly twice the chunk size; VAD helps most for speech with pauses; WER differences between VAD settings are small.
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
- Numbers: Table 1 DER rows were interleaved in extraction; the text says "Even with a very low latency of 0.32 seconds, the model continues to deliver highly competitive performance", and the model "has a constraint of 4 speakers by design".
- Relevance: the strongest published online diarizer for mixed audio. Needs a GPU for the quoted RTF, and caps at 4 speakers.
- Design implication (ingest, WORK_SPLIT task 6): this is only a fallback path; with LiveKit we have per-participant tracks, so speaker identity is known from the track and diarization is not needed for the live demo. Keep pyannote/Sortformer for the mixed-audio import path.
- Confidence: [verified-in-source] for design and latency/RTF; DER values not extracted.

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
- Claim (as alleged): Otter Notetaker recorded conversations without consent from all participants, including non-users, and used recordings to train its AI; statutes cited are ECPA and the California Invasion of Privacy Act (OECD page); case number 5:25-cv-06911 and Judge Eumi K. Lee come from a search summary, not from a document I read.
- Relevance: the headline harm is the non-user participant who never agreed. A local, bot-less design is outside this fact pattern but participants still have not consented to being transcribed.
- Design implication (demo / consent): a visible "recording" indicator and a consent roll call (F3) are the minimum story for the slides; state "local only, no training use".
- Confidence: [secondhand]

### P23. Cruz v. Fireflies.AI Corp. (C.D. Ill., Dec. 2025)
- URL: https://www.dataprivacyandsecurityinsider.com/2025/12/lawsuit-alleges-fireflies-ai-corp-illegally-collects-biometric-data-from-virtual-meetings/ (read).
- Claim (as alleged): Fireflies' "speaker recognition" generates voiceprints of every participant, including non-users, in violation of the Illinois BIPA (no notice, written consent or published retention policy). Court and docket come from a search summary (Central District of Illinois, Springfield), not the article, which says only "an Illinois federal court".
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

---

## 7. Gaps the literature does not cover (our contribution zone)

1. Retroactive requests ("strike that"): no benchmark or system in the papers above. All CI work handles a single static prompt.
2. Time: no paper has a hold/commit delay. Streaming ASR work (P8-P11) treats latency as a cost to minimise, never as a safety budget.
3. Scope (state over time): ConfAIde Tier 4 secrets are static per scenario; no "until further notice" scope with explicit or implicit end.
4. Speaker ownership of a privacy signal: not studied.
5. Spoken-cue detection under ASR errors: not studied (P20 is closest, for PII).

---

## 8. Top 5 design changes this suggests

1. **Per-stage leak logging and a stage-error cascade test (P4).** Record leak after each stage (PII, cue, state machine, LLM check) and report Q_s-style composites. This will show whether I1 (implicit end too early) comes from the heuristic or from upstream cue misses, and gives the Related Work claim "structure helps only if early stages are accurate".
2. **Make the implicit check a CI-tuple classifier with the notes as the recipient (P2, P3, P5).** Prompt for sender / subject / recipient / data type / transmission principle, not "is this private?". Do not use long CoT (P1: no help, slightly worse).
3. **Use track identity, not voiceprints, and enforce speaker opt-out by dropping the track (P17, P23).** This gives exact zero leak for opted-out speakers, avoids the BIPA fact pattern, and replaces F2's "target-speaker unlearning" with a stronger, cheaper mechanism. Keep unlearning as a separate future item.
4. **Gate ASR with VAD and run cues on hypothesis plus confirmed text (P8, P12).** Silence in OFF periods must not reach Whisper (hallucination), and cue detection should not wait for confirmation. Count hold time from confirmation.
5. **Report leak with helpfulness adjustment and the worst case over runs (P1, P2).** Add LRh-style leak over outputs that keep the public items, the 10-run worst-case, and an abstraction output option (P7) alongside delete, so the "redact everything" strategy cannot win.

## 9. New open questions for PRD 2.6

- **Q5.** Is an OFF scope owned by the speaker who opened it, or by the room? With per-track input, should A's "off the record" suppress B's replies, and how does the benchmark label that?
- **Q6.** How often is the cue phrase itself mis-transcribed or hallucinated at the WER of our chosen model (cue recall as a function of WER)? Do we need fuzzy cue matching on the hypothesis stream?
- **Q7.** Does the privacy layer itself leak: the hold buffer, the audit log, and PENDING prompts contain the private text. What is the retention and display policy for suppressed text?
- **Q8.** What is the ground-truth rule for "by meaning" retroactive targets (which earlier span does "forget what I said about the layoffs" refer to), and how is resolution accuracy scored separately from leak rate?
- **Q9.** Can a 3B/7B local model do the CI-tuple check with acceptable false-alarm rate, or must the implicit class be limited to a closed list (health, salary, HR) with keyword-gated LLM confirmation?

## 10. Benchmark ideas

- **OTR-Bench-ASR:** pass the 40 text snippets through TTS then Whisper (recipe of P21) and compare to clean-text leak rates (P20 motivation).
- **Per-stage Leak_s and Q_s** (P4) as columns in the results log (PRD 2.5).
- **LRh-style adjusted leak** and 10-run worst case (P1, P2); plus the Leaks-or-Omits composite.
- **Dense-context condition** (P6): the same private item embedded in a long transcript with distractors.
- **Silence-hallucination and false-cue cases** (P12): a muted period followed by speech; the phrase "off the record" in a quoted title; "strike that" as an ordinary correction (I6 in WORK_SPLIT).
- **Speaker-ownership cases** (Q5): A opens a scope, B speaks; A leaves; per-speaker labels needed.
- **Live/streaming mode** (P3): feed segments in real time; sweep hold seconds in the replay with proper ticks (I2).
- **Abstraction variant** (P7) as a fourth output mode, scored for leak and usefulness.

## 11. What I could not verify

- Exact PrivacyLens row-to-model alignment in Table 2 (garbled extraction). The 25.68 / 38.69 values are as stated in the abstract and match the helpfulness-adjusted column; I did not confirm the LR values 24.54 / 39.15 against a clean table.
- ConfAIde Table 4: summary-vs-action-item block assignment is inferred from the paper's prose, not from a clean table header.
- Whether the 18% / 19% (1-2-3 Check) and "up to 40%" (CI-RL) reductions are absolute or relative; PrivacyChecker's leakage metric/benchmark behind 36.08 -> 7.30 and 33.06 -> 8.32.
- Streaming Sortformer DER numbers (table interleaved); pyannote 4 / community-1 and Precision-2 claims (only a vendor page seen via search); newer DiariZen releases; whether Sortformer offline paper (arXiv 2409.06656, ICML 2025) claims, which I saw only in search results.
- Any peer-reviewed user study of notetaker consent; any 2024-2026 paper on per-participant-track vs mixed diarization; any prior work on retroactive redaction or explicit privacy-cue speech acts.
- Case status and docket details for Brewer v. Otter.ai (NPR fetch timed out; case number and judge are search-summary only) and Cruz v. Fireflies (court identification is search-summary only).
- Peer-review status of CI-Work (listing says ACL 2026 Industry Track; not opened), CI-RL's NeurIPS 2025 acceptance (search listing), and Beyond Clean Text / DialogPII (no arXiv or proceedings version checked).
- Laptop-level real-time factors for Whisper-Streaming, SimulStreaming, DSM-ASR: the cited numbers are computation-unaware or GPU-based.
