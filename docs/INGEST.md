# Ingest: meeting audio to Segments

Everything in `otr/ingest/` produces `otr.types.Segment` objects (id, speaker, text, t_start, t_end).

| Source | File | Needs | Status |
|---|---|---|---|
| Replay (JSONL or `Alice: text` script) | `replay_source.py` | nothing | tested |
| LiveKit room bot | `livekit_source.py` | livekit, livekit-api, faster-whisper, a LiveKit server | tested against a local server with synthetic audio; microphone speech still needs a human check |
| Mixed-audio diarization | `diarize.py` | pyannote.audio + HF token (optional) | pyannote path untested; energy splitter is a placeholder |

## Why LiveKit

A LiveKit room gives one audio track per participant, so speaker = `participant.identity`.
No ML diarization is needed, and it is more reliable than diarizing mixed audio.

## Run LiveKit locally

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-core.txt -r requirements-demo.txt -r requirements-ingest.txt
.venv/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8', download_root='models/faster-whisper')"
livekit-server --bind 127.0.0.1 --node-ip 127.0.0.1 --keys "devkey: otr-dev-secret-change-me-0123456789abcdef"
```

In another terminal:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m demo.server --source livekit --pipeline real --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/` in two local browser tabs. Each person joins with a
server-issued identity and starts **Not recorded**. The button controls only that
person's recorder subscription; everyone can see the status. The dev server's
placeholder key and secret are for the same-machine demo only. A LAN deployment
needs its own keys, HTTPS and participant authentication.

## Join as a human

The meeting page mints short-lived tokens locally. For a low-level SDK check,
you can still mint one from the command line:

```bash
.venv/bin/python -m otr.ingest.mint_token --room demo --identity alice
```

Do not use a hosted meeting page for the privacy demo. The app serves its
LiveKit browser SDK, CSS and JavaScript from local files.

## Start the bot

```bash
.venv/bin/python -m otr.ingest.livekit_source --room demo --consent-identity alice
```

The standalone bot needs an explicit `--consent-identity` for each consenting
participant. The meeting app handles this from each person's authenticated
button. The bot joins as `otr-bot` with `auto_subscribe=False`, runs local
`faster-whisper` per opted-in audio track, and yields speaker-attributed Segments.
Stop revokes that speaker, cancels pending work and unsubscribes.

In the live path, STT waits for the utterance to close after 700 ms of silence;
it does not emit partial prefixes that might reveal sensitive context too soon.
The energy threshold (500 RMS) is untuned, the chunker caps uninterrupted speech
at 20 seconds, and many simultaneous CPU transcriptions may lag. The privacy
pipeline holds text beyond ASR; sensitivity checks are not yet proven complete.

`load_whisper` resolves weights from the ignored local `models/faster-whisper`
cache or `OTR_WHISPER_MODEL_DIR` and refuses to download at runtime. Install the
model before disconnecting WAN; keep `HF_HUB_OFFLINE=1` for an offline run.

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
