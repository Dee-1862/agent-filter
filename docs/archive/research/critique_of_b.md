# Critique of draft_b.md (by Researcher A, round 2)

Method: re-opened the primary sources myself. PDFs were downloaded and text-extracted; where a table extracted badly I rendered the PDF page to an image and read the table visually. Verdicts: **confirmed** = I saw the same value in the source; **wrong** = the source says something different; **unverifiable** = I could not reach a primary source. Numbers I computed myself are marked "recomputed".

## 1. The disputed ConfAIde Tier 4 claim (settled)

| Claim | Verdict |
|---|---|
| B: "39%/57% is the ACTION-ITEM task; summary is 0.29/0.38" | **WRONG** (B's mapping is inverted). |
| A (draft_a, round 1): "39%/57% is the meeting-SUMMARY Leaks Secret rate" | **Confirmed**. In round 1 I had inferred this from prose; I have now verified it from the rendered table. |
| B: "Tier 4 is only 20 transcripts, 5 secrets x 4 public-info types, so the 20 ConfAIde items in OTR-Bench are the whole tier" | **Confirmed** (A had missed it). |
| B: secrets are announced as confidential inside the dialogue (not implicit) | **Confirmed** |
| B: 16 of 200 GPT-4 action-item responses leaked but were missed by exact string match; no string-match false positives | **Confirmed** |
| B: Table 5 CoT 0.39->0.40 (GPT-4), 0.57->0.61 (ChatGPT) | **Confirmed** (also in A) |

Evidence. arXiv 2310.17884, PDF page 8, Table 4, rendered image. Caption: "Overview of metric values for Tier 4, where models are used as AI meeting assistants generating meeting summary and personal action items. Lower is better for all metrics." The table has two blocks with a rotated row label on the left. The **first block is labelled "Act. Item"**, the **second block is labelled "Summary"**:

- Act. Item block: Leaks Secret (Worst Case) 0.80 / 0.85 (GPT-4 / ChatGPT); **Leaks Secret 0.29 / 0.38**; Omits Public Information 0.76 / 0.89; Leaks Secret or Omits Info. 0.89 / 0.96.
- Summary block: Leaks Secret (Worst Case) 0.80 / 0.85; **Leaks Secret 0.39 / 0.57**; Omits Public Information 0.10 / 0.27; Leaks Secret or Omits Info. 0.42 / 0.74.

This agrees with Sec. 4.4: "This leakage is higher in the meeting summary task compared to the personal action item generation task." B's reading contradicts that sentence (it would make action items leak more). B was probably misled by the `pdftotext` layout, which prints the two blocks without their rotated labels. Section 3.4 (same PDF): "We generate 20 transcripts also in a factorial manner, by iterating through five secrets ... and four public information types". Appendix B.4: "a thorough manual review of all 200 GPT-4 responses for the action item generation task ... 16 instances where private information was leaked, yet not detected by exact string matching". Table 12 note: Tier 4 is 20 transcripts (the per-tier count table says "20 transcripts").

URL: https://arxiv.org/pdf/2310.17884 (Table 4, Sec. 3.4, Sec. 4.4, App. B.4).

Consequence for the PRD: the PRD's wording "Tier 4 (meeting summarization and action items)" is fine; 39/57 is the summary figure. B's other inference, that 20 Tier-4 items are the whole tier, a 5x4 grid, and explicit-in-context rather than implicit, is correct and should go into RESEARCH.md.

## 2. B's other load-bearing claims

| # | B's claim | Verdict | Evidence |
|---|---|---|---|
| 1 | 1-2-3 Check Table 2, GPT-4o: single agent 23.0 / 12.0 / 26.3 | **Confirmed** | https://arxiv.org/pdf/2508.07667, p.6, Table 2 (rendered). Columns: Leaks Secret, Omits Public, Leaks or Omits. |
| 2 | ... single agent + CoT 2.0 / 32.5 / 34.0 | **Confirmed** | same table: "Single Agent (CoT) 2.0 +/- 0.9, 32.5 +/- 7.0, 34.0 +/- 6.9". B's headline "23.0% -> 2.0% with omission 12.0% -> 32.5%" is accurate. Note the CoT composite (34.0) is worse than the plain single agent (26.3). |
| 3 | Three agents Annotate Private 5.0 / 20.0 / 24.5; best composite 17.5 (w/o transcript, 8.5 / 10.0) | **Confirmed** | same table. LLaMA-3.1-70B rows (29.5/23.5/48.5, CoT 3.0/27.5/29.5, three-agent Public Only 3.0/19.5/20.5) also match. |
| 4 | The task in 1-2-3 Check is meeting summaries (ConfAIde Tier 4) | **Confirmed** | Sec. 4 text refers to "meeting summary" generation; abstract says "summarizing meetings". |
| 5 | 1-2-3 Check limitations say overhead may be impractical for streaming meeting transcripts | **Confirmed** | text lines: "applications with tight latency constraints, such as live customer support or streaming meeting transcripts. This overhead may be impractical". |
| 6 | PrivacyChecker GPT-4o 33.06 -> 8.32 (helpfulness 2.69 -> 2.45) | **Confirmed** | https://arxiv.org/pdf/2509.17488, Table 1 (row for GPT-4o; the extraction mislabels one row as GPT-4.5 but the appendix row "GPT-4o 97.97% 33.06% 33.56% 2.69" and the later table "PrivacyChecker GPT-4o 8.32 9.22 2.45" fix the model). DeepSeek-R1 36.08 -> 7.30 per abstract. Other rows (GPT-4.5, o1, Qwen3) I could not align because of the garbled extraction: unverifiable by me. |
| 7 | Whisper-Streaming about 3.3 s latency | **Confirmed**, with scope | https://arxiv.org/pdf/2307.14743, abstract and Sec. 5: "with 1 second MinChunkSize, the average latency is 3.3 seconds for English, 4.4 seconds for German and 4.8 seconds for Czech, while the WER is by 2% higher than in the offline mode for English and German, and by 6% higher for Czech". B's Table 1 numbers (A40 off: WER 5.8 +/- 0.9, 2.85 +/- 0.45 s; L40 on 5.0 / 3.96 s) also match. Server GPU (A40/L40), parliament speech; no laptop figure, as B says. |
| 8 | McNemar worked example: b=9, c=2, p = 0.065, risk difference 17.5 points | **Confirmed** (recomputed) | Exact two-sided binomial: 2 x P(X>=9 | n=11, 0.5) = 0.0654. (9-2)/40 = 17.5. B's Wilson intervals are correct (recomputed: 12/40 -> 18.1-45.4; 5/40 -> 5.5-26.1; 0/40 -> 0.0-8.8; 2/40 -> 1.4-16.5; 6/40 -> 7.1-29.1; 20/40 -> 35.2-64.8). One caution: B's "3 items leaked in both" implies 29 items neither leaks, so 40 = 9+2+3+26; fine. |
| 9 | Paired percentile bootstrap gives [2.5, 32.5] points, excluding zero although the exact test does not | **Confirmed** (recomputed) | Resampling the 40 paired outcomes (9 x +1, 2 x -1, 29 x 0) with 20,000 draws gives 95% percentile interval [2.5, 32.5]; the bootstrap puts about 1.7% of mass at <= 0. B's point (percentile bootstrap anti-conservative at small n) is consistent with https://arxiv.org/abs/2503.01747 (Bowyer et al.: CLT and bootstrap poorly calibrated at small N; Bayes/Wilson good). B's specific claim that the CLT interval gave 92.5% coverage at N=100 in the clustered setting: unverifiable by me (the string "92.5" does not appear in the extracted text). |
| 10 | Power: about 62 items per system to detect 30% vs 10% (alpha 0.05, 80% power) | **Confirmed** (recomputed) | Normal-approximation two-proportion formula gives 61.6 per arm, so 62. Note this is per arm, unpaired; B says "per system", which is the same. B's remark that a paired design needs fewer is true but its size depends on discordance. |
| 11 | CI-RL: Qwen2.5-7B LR 50.3 -> 44.8 -> 33.7 | **Confirmed** | https://arxiv.org/pdf/2506.04245, Table 3 (rendered). LR columns: Mistral-7B 47.9/28.8/31.2; Qwen2.5-7B 50.3/44.8/33.7; Llama-3.1-8B 18.2/21.3/18.5; Qwen2.5-14B 52.9/42.8/33.9. Frontier rows also match (Claude 3.7 S-T 32.0 -> 20.1; Gemini 2.5 Pro 37.3 -> 25.3). **Omission by B:** the Llama-3.1-8B "no gain" is because its baseline LR is low only because it is unhelpful (helpfulness 1.05; its adjusted rate ALR is 38.9 -> 31.5 -> 29.4). Do not read 18.2 as "good". |
| 12 | PrivacyLens judge: Mistral-7B few-shot, kappa 0.82, accuracy 0.92, 153 pairs from 50 actions; helpfulness agreement 0.56 | **Confirmed** | https://arxiv.org/pdf/2409.00138, Sec. 4 text. (The 0.56 is described as agreement with human binary label; B calls it kappa, the extracted text cuts off after "0.56 with", so label as "agreement", not kappa.) |
| 13 | PrivacyLens: 25.68 = GPT-4 LRh, 38.69 = Llama-3-70B LRh; raw LR 24.54 / 39.15 | **Confirmed** (agrees with A) | Table 2 as extracted; the abstract and Sec. 1 text agree. Both drafts read the same garbled table the same way, so this is not independent verification of the raw-LR column. |
| 14 | CI-Work Table 2 (GPT-5): no defence 11.21 / 27.83 / 93.04; Prompt Defense 8.96 / 21.31 / 81.01; CI-CoT 8.95 / 22.13 / 84.90 | **Confirmed** | https://arxiv.org/pdf/2604.21308 text lines for Table 2; venue and pages (ACL 2026 Industry Track, pp. 1483-1508) confirmed at https://aclanthology.org/2026.acl-industry.103/ (A had only the arXiv version). |
| 15 | Streaming Sortformer DIHARD III "all": 19.02 (10 s) / 18.97 (1.04 s) / 19.32 (0.32 s) with post-processing; 19.89 / 20.25 without; RTF 0.005 / 0.093 / 0.180; 4-speaker limit | **Confirmed** | https://arxiv.org/pdf/2507.18446, Table 1 and Table 2 (rendered). |
| 16 | "CALLHOME-part2 all-speakers: 11.22 (10 s) / 12.40 (1.04 s) / 13.64 (0.32 s)" | **WRONG (mislabelled column)** | In the rendered Table 1 these three numbers are the **4-speaker** column. The "all" column for Streaming Sortformer-AOSC with post-processing is **10.09 / 10.79 / 11.50** (10 s / 1.04 s / 0.32 s). |
| 17 | AirGapAgent 94% -> 45% under attack, 97% protection | **Confirmed** | https://arxiv.org/pdf/2405.05175 abstract text: "reduces its ability to protect user data from 94% to 45%, while an AirGapAgent achieves 97% protection". |
| 18 | CaMeL: 77% of AgentDojo tasks with provable security vs 84% undefended | **Confirmed** | https://arxiv.org/pdf/2503.18813 abstract. |
| 19 | Trustera: first functional real-time spoken PII redaction system, thousands of agents | **Confirmed** (abstract) | https://arxiv.org/pdf/2303.09438. It mutes audio sent to the agent when PCI begins; no retroactive requests. |
| 20 | Miller: clustered SEs can be 3x larger than naive | **Confirmed** | https://arxiv.org/pdf/2411.00640 Table 4 caption: "clustered standard errors can be over 3X larger than naive standard errors". |
| 21 | MuPPET, PiSAs, PrivacyAlign abstract-level claims | **Confirmed** (abstract pages opened) | https://arxiv.org/abs/2606.23217 ; https://arxiv.org/abs/2607.05318 (PiSAs: "incorrect LLM judgments remain the main bottleneck"); https://arxiv.org/abs/2606.21710 (1,350 samples, 3,516 annotations, 599 annotators). B was right not to cite the model-level leak rates it saw only in a snippet. |
| 22 | Otter: consolidation Oct 22 2025; partial denial of motion to dismiss Aug 13 2026; Fireflies Cruz (C.D. Ill., Dec 18 2025) and Fricker (N.D. Ill., Mar 2026) | **Unverifiable** | https://blog.buildbetter.ai/ai-notetaker-lawsuits-2026-how-to-record-meetings-legally/ says exactly this but attributes it to "The Little Binger" and to a tl;dv overview, with no docket. No primary court record was reachable. B correctly marks this secondhand. |
| 23 | Strawman-baseline objection: a plain CoT prompt gets Tier 4 leak to 2.0% (GPT-4o) | **Confirmed but incomplete** | The leak figure is right, but the composite (Leaks-or-Omits) of CoT is 34.0 vs 26.3 for the plain prompt, i.e. worse. A fair B+ must be judged on the composite, not on leakage. Also GPT-4o is not GPT-4: ConfAIde's 2023 "CoT does not help" was GPT-4/ChatGPT with a generic "step by step" prompt, so there is no contradiction, only a different model and prompt. B says this is "superseded"; the accurate wording is "does not generalise to newer models / CI-specific CoT". |
| 24 | "No peer-reviewed user study of notetaker consent" and "PRD 1.1 survey claim unverified" | **Partly wrong** | An industry survey exists (Kolmogorov Law / Pollfish, 500 U.S. workers, 167 exposed, 34.7% always asked): https://krdo.com/stacker-business-economy/2026/07/16/ai-notetakers-have-sat-in-on-1-in-3-us-workers-meetings-but-only-a-third-say-they-were-asked-first/ . It is law-firm-commissioned and not peer-reviewed, but it does support the PRD sentence in a weak form; B's "unverified" was too strong. |

## 3. Things B got right that A had missed (absorbed into the revision)

- Tier 4 is 20 transcripts (5x4 grid), explicit in context; cluster by secret.
- The 1-2-3 Check "18%" reduction is **23.0 -> 5.0 = 18 absolute points** vs the non-CoT single agent (A had flagged it as unverifiable). Against single-agent CoT, leakage is already 2.0, so the multi-agent pipeline is not better on leak; its composite is.
- A fair prompting baseline (B+) is required; the hindsight confound (offline single pass sees the later "strike that").
- The audit log / reasoning-trace leak (Leaky Thoughts, abstract-only), AirGapAgent as the closest "removal beats instruction" analogue, Trustera as live-redaction prior art, the statistical reporting plan (Wilson, exact McNemar, clustering).

## 4. Weaknesses in B that remain

- It overstates "superseded": 2023 CoT results and 2025 CI-CoT results are on different models and prompts.
- It reports 3-5 s ASR confirmation latency as a general bound while the only measurements are server-GPU, parliament speech.
- No treatment of Whisper hallucination on silence in an OFF period (it cites Careless Whisper at abstract level only, and only as a cue-recall concern).
- Items 8-10 and 5-7 are abstract-only, so their relevance claims are speculation.
