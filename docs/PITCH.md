# Pitch: Off The Record

Audience: hackathon judges and the super{set} team. Everything here can be traced to a file in this repo or to a source linked below. Claims that are not yet verified are labeled as such.

## One line

A meeting notetaker that lets each person decide whether their speech can enter the notes, then catches requests like "off the record" and "strike that" before a line is released.

## The problem

- Notetaker bots record everything. There is no way to say "not that part" and have it honored.
- Asking a language model once to "remove anything private" still leaks. ConfAIde reports 39% (GPT-4) and 57% (ChatGPT) leakage on its meeting-summary task, with the privacy instruction already in the prompt.
- Consent is usually decided for you. A law-firm commissioned survey (n=167 people who had seen an AI notetaker) found 34.7% were always asked first, 25.1% never.

## What we built

- Each person joins a LiveKit room and decides for themselves whether their voice goes into the notes. The notetaker subscribes to their audio track only after they opt in. The public demo uses LiveKit Cloud for the call.
- Speech is transcribed locally (faster-whisper). Each sentence waits in a short hold buffer before it can reach the shared notes.
- Presidio masks contact details. A cue detector hears "off the record", "between us", "back on the record" and "strike that". A small state machine remembers whether notes are on or off. A local Ollama model handles sensitive topics with no spoken cue (pay, health, HR).
- The page shows the kinds of things kept out (counts per category), never the content, and explains why a line was kept out.
- Transcription, filtering, and note assembly run on the host laptop. The public demo sends call audio and video through LiveKit Cloud; Vercel and Cloudflare carry meeting controls and approved transcript responses. The live path does not write raw audio files or a transcript database by default. A fully local deployment remains the target.

## Fit with the super{set} portfolio

- Ketch (privacy and data governance): the closest match. Our per-person consent, purpose and enforcement flow uses the same ideas. We treat this as an analogy, not an integration. We did not find public documentation for an offline deployment. A possible next step is an adapter that maps each participant's consent state to a Ketch purpose so the choice is recorded in a system an organization already audits. Ketch's public consent API and Web SDK exist; how its purposes and enforcement would map is not verified.
- Headlamp Health and PointHealth (healthcare data): clinical and patient-adjacent conversations are the clearest case for sensitive content that nobody announces. Not tested on any clinical data.
- Eubrics (sales coaching with live roleplay and analytics): live calls are recorded and scored, so per-person consent and "strike that" apply. Not tested with that product.
- Moneyball.ai (deal introductions and matching): deal calls carry confidential terms. Not tested.

## Demo script (3 minutes)

1. Two people join the meeting. One turns notes on, the other leaves them off. Only the first person's words appear.
2. The first person says "this next bit is off the record". The status changes, and what follows stays out of the notes until they say they are back on the record.
3. They say "strike that" about a line that is still in the hold buffer. It disappears before it ever commits.
4. They mention a salary. The page asks to keep it out, or it is held back automatically in consent mode.
5. Open the insights view: counts of kinds of things kept out, with no text. Open the explanation view to see which rule fired.

## What is real and what is not

- Measured on synthetic data written by us: on 36 held-out items (22 with private content), our system leaked on 5 of 22 (23%, 95% interval 10 to 43%) while simple rule baselines leaked on 17 of 22. These baselines are stand-ins, not real language-model baselines, so this is not yet a fair comparison. The development set result (1%) was tuned on and is not a result. See `bench/results_heldout.md` and `docs/RESEARCH.md`.
- Synthetic-voice end-to-end runs (text-to-speech through LiveKit, Whisper and the consent-gated pipeline) worked for the basic path. They also found failures: a bare employee number reached the transcript, and a spoken stop request was misheard once. See `docs/TTS_EXPERIMENT.md`.
- A host and guest have joined the public call in real browsers. A user also confirmed a call with a friend worked. Real-voice transcription accuracy has not been measured. Also not done: a run with several real people, a hand-checked benchmark, a fair language-model baseline, or Meet or Zoom integration (which needs a meeting-bot service).

## Ask

- Feedback from the Ketch team on mapping per-person consent to purposes and enforcement.
- A healthcare or sales-coaching partner willing to try it on non-sensitive pilot calls.

Sources: [super{set} portfolio](https://www.superset.com/portfolio), [Ketch developers](https://www.ketch.com/developers), ConfAIde ([arXiv 2310.17884](https://arxiv.org/abs/2310.17884)).
