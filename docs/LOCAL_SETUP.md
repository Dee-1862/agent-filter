# Local setup and current readiness

Updated 2026-10-22. Remote commit `aa9835e` added a LiveKit ingest skeleton, a replay demo, a local pipeline, and benchmarks. The LiveKit path and per-person consent are still being implemented and verified. Follow [PRD.md](PRD.md), especially A-001–A-006, and [WORK_SPLIT.md](WORK_SPLIT.md).

## Prepared on Lance's Mac

- Repo cloned from `Dee-1862/agent-filter` into `~/Desktop/Hobbies/Projects/agent-filter`; the initial commit was `2b7b7a0`, and the current pulled scaffold is `aa9835e`.
- Apple M2, 24 GiB memory.
- Homebrew `livekit-server` 1.13.10 installed. A local development server was started successfully and then stopped.
- Homebrew `whisper.cpp` 1.9.5 installed. No microphone or meeting audio has been processed.
- `models/ggml-base.en-q5_1.bin` downloaded from the [Whisper model repository](https://huggingface.co/ggerganov/whisper.cpp/blob/main/ggml-base.en-q5_1.bin) and ignored by Git. SHA-256: `4baf70dd0d7c4247ba2b81fafd9c01005ac77c2f9ef064e00dcf195d0e2fdd2f`. The file has not been benchmarked; its checksum matches the published model page.
- A Docker LiveKit image is cached locally but is not running. The native Homebrew server is simpler for the first same-machine demo.

## First implementation slice

1. Serve a two-participant LiveKit meeting locally with one visible consent control per participant and shared status indicators.
2. Give the recorder `autoSubscribe=false`; permit subscriptions only for authenticated opted-in participant identities.
3. On Stop, invalidate that participant's consent epoch synchronously, discard pending/in-flight content, then unsubscribe. Test that an OFF participant contributes zero frames to the recorder.
4. Run local ASR on opted-in per-person streams. Keep audio in RAM; do not use LiveKit egress or write audio files.
5. Show speaker-grouped transcript text only after local cue and HR/PII checks. The visible UI can show `Checking` immediately; it must not show unreviewed words.

Use a same-machine or LAN demo first. A remote deployment needs a self-hosted reachable server, TLS, authentication and TURN; it is not a prerequisite for the hackathon proof. Download dependencies and model weights in advance, then test with WAN disconnected to verify the app still works. The app must not load remote fonts, scripts, analytics, model APIs or external STUN services at runtime.

`models/`, recordings, transcript files, local databases, virtual environments, node dependencies and `.env` files are ignored by Git. This reduces accidental commits; it is not a substitute for access control or encryption.
