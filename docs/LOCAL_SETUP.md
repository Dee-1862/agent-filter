# Local setup and current readiness

Updated 2026-10-22. Remote commit `aa9835e` added a LiveKit ingest skeleton, a replay demo, a local pipeline, and benchmarks. The current feature branch wires the LiveKit path to a local meeting page and per-person consent. Follow [INGEST.md](INGEST.md) to run it, [LOCAL_PRIVACY.md](LOCAL_PRIVACY.md) for the data boundary, and [WORK_SPLIT.md](WORK_SPLIT.md) for ownership.

## Prepared on Lance's Mac

- Repo cloned from `Dee-1862/agent-filter` into `~/Desktop/Hobbies/Projects/agent-filter`; the initial commit was `2b7b7a0`, and the current pulled scaffold is `aa9835e`.
- Apple M2, 24 GiB memory.
- Homebrew `livekit-server` 1.13.10 installed. A local development server was started successfully and then stopped.
- Homebrew `whisper.cpp` 1.9.5 installed. No microphone or meeting audio has been processed.
- `models/ggml-base.en-q5_1.bin` downloaded from the [Whisper model repository](https://huggingface.co/ggerganov/whisper.cpp/blob/main/ggml-base.en-q5_1.bin) and ignored by Git. SHA-256: `4baf70dd0d7c4247ba2b81fafd9c01005ac77c2f9ef064e00dcf195d0e2fdd2f`. The file has not been benchmarked; its checksum matches the published model page.
- A Docker LiveKit image is cached locally but is not running. The native Homebrew server is simpler for the first same-machine demo.

## Implemented first slice

1. A two-participant browser check showed each person's visible Start/Stop control and shared status indicators.
2. The recorder starts with `auto_subscribe=False` and subscribes only to the opted-in identity.
3. Stop invalidates that participant's consent epoch, discards pending/in-flight text, and unsubscribes. A synthetic clip after Stop produced no new transcript line.
4. Local faster-whisper runs on opted-in per-person streams. The live path keeps audio in RAM and does not use LiveKit egress or write audio files.
5. Shared transcript text appears only after local policy approval and a hold. Sensitive flags pause capture for that person and discard the pending utterance. The current rule-based policy is incomplete for some contextual HR or numeric disclosures; Deekshith's local model work will address that gap.

Use a same-machine or LAN demo first. A remote deployment needs a self-hosted reachable server, TLS, authentication and TURN; it is not a prerequisite for the hackathon proof. Download dependencies and model weights in advance, then test with WAN disconnected to verify the app still works. The app must not load remote fonts, scripts, analytics, model APIs or external STUN services at runtime.

`models/`, recordings, transcript files, local databases, virtual environments, node dependencies and `.env` files are ignored by Git. This reduces accidental commits; it is not a substitute for access control or encryption.
