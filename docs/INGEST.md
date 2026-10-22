# Ingest: meeting audio to Segments

Everything in `otr/ingest/` produces `otr.types.Segment` objects (id, speaker, text, t_start, t_end).

| Source | File | Needs | Status |
|---|---|---|---|
| Replay (JSONL or `Alice: text` script) | `replay_source.py` | nothing | tested |
| LiveKit room bot | `livekit_source.py` | livekit, livekit-api, faster-whisper, a LiveKit server | written from the SDK docs, NOT run |
| Mixed-audio diarization | `diarize.py` | pyannote.audio + HF token (optional) | pyannote path untested; energy splitter is a placeholder |

## Why LiveKit

A LiveKit room gives one audio track per participant, so speaker = `participant.identity`.
No ML diarization is needed, and it is more reliable than diarizing mixed audio.

## Run LiveKit locally

```bash
pip install -r requirements-ingest.txt
docker compose -f docker-compose.livekit.yml up -d     # ws://localhost:7880, key devkey / secret
export LIVEKIT_URL=ws://localhost:7880 LIVEKIT_API_KEY=devkey LIVEKIT_API_SECRET=secret
```

## Join as a human

Mint a token:

```bash
python -m otr.ingest.mint_token --room demo --identity alice     # prints a JWT
# or: lk token create --api-key devkey --api-secret secret --join --room demo --identity alice
```

Open https://meet.livekit.io, choose "Custom", and enter `ws://localhost:7880` plus the token.
(An https page may refuse a plain `ws://` server because of mixed content. If so, run the
LiveKit Meet starter app locally, `github.com/livekit-examples/meet`, pointed at the
local server, or use `localhost` in a browser that treats it as secure.) Repeat with
`--identity bob` in a second tab. Each human is a separate track.

## Start the bot

```bash
python -m otr.ingest.livekit_source --room demo     # prints one Segment JSON per line
```

The bot joins as `otr-bot` (subscribe-only), runs one `UtteranceChunker` per remote
participant audio track (16 kHz mono, energy VAD, faster-whisper `base.en` CPU int8), and
yields Segments. In code: `async for seg in LiveKitSource(room="demo").segments()`.

STT behaviour (`stt.py`): text is only emitted when confirmed, either by two consecutive
passes agreeing on a word prefix (LocalAgreement-2, re-run every 2 s) or by end of
utterance after 700 ms of silence. Caveats: the energy threshold (500 RMS) is untuned,
a participant who joins after the bot is only picked up on `track_subscribed`, and
whisper runs in a thread executor so many simultaneous speakers on CPU may lag.

## Demo without any of this

```bash
python -m otr.ingest.replay_source script.txt 4    # script or .jsonl, 4x real time
```

```python
ReplaySource.from_file("script.txt", speed=1.0).segments()
```

## Mixed audio (recordings)

`diarize.diarize_pyannote(wav, hf_token)` returns `Turn(SPEAKER_00, start, end)` list; it
raises a clear error if pyannote or the token is missing. `energy_turns()` is a
dependency-free PLACEHOLDER (pause splitting plus round-robin labels) and is only right for
strict two-person turn-taking. Joining turns to transcribed words is not implemented.

## Google Meet / Zoom: honest status

LiveKit is its own WebRTC platform. It does NOT join Google Meet or Zoom calls.
Options, none implemented here:

1. Meeting-bot API (Vexa, Attendee): a bot joins the Meet/Zoom call as a participant and
   streams per-speaker or mixed audio and transcripts. Best real integration; future work: write a
   `SegmentSource` adapter over its websocket/webhook.
2. SIP / phone bridge: LiveKit SIP can take dial-in audio, but this is mixed and loses
   per-person identity. Meet/Zoom dial-in numbers need the host's settings.
3. Capture audio of a call (loopback / virtual cable) and run `diarize.py`. Works anywhere
   but diarization is the weak link and needs everyone's consent.

Recommendation for the demo: show LiveKit (two browser tabs plus the bot) for the live,
reliable-identity story, with `replay_source` as the fallback if wifi or Docker fails. Mention
Vexa/Attendee as the path to real Meet/Zoom.
