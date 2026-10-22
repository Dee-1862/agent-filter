# Running the demo: one entry point

```
python -m otr.app --source replay|audio|livekit|livekit-stream [options]
```

It prints a readiness table for the chosen source only, stops (exit 2) only on hard
requirements, prints the fix command for anything missing, warms the LLM, then serves the UI at
`http://127.0.0.1:8000/`. `--check` prints the table and exits (0 ready, 1 blocked).
Windows wrapper: `.\scripts\run_demo.ps1 <source> [-Audio ...] [-Llm ...] [-Check]`.

| Option | Meaning |
|---|---|
| `--audio PATH...` | folder, several per-speaker files, or one mixed file (audio source) |
| `--turns FILE` | speaker-turn JSON `[{"speaker","start","end"}]` for one mixed file |
| `--script FILE` | replay script (`Alice: text` lines, `@pause N`) or `.jsonl` |
| `--llm auto\|none\|ollama[:MODEL]` | default `auto`: uses the local model when Ollama is running and has it, otherwise rules + Presidio only |
| `--hold N` | hold-buffer seconds (default `$OTR_HOLD_SECONDS`, else 5 for `--source livekit` and 10 otherwise) |
| `--fast` | hold 2 s and close utterances after 450 ms of silence (a later "strike that" has less time to catch a line) |
| `--speed N` | audio/replay pacing: `1` real time, `4` four times faster, `0` as fast as possible |
| `--model tiny.en` | Whisper model (default `$OTR_WHISPER_MODEL` or `base.en`) |
| `--port N`, `--host H`, `--room R`, `--no-docker` | server port/host, LiveKit room, never run docker compose |

## 1. replay (scripted, nothing to download)

```
python -m otr.app --source replay --script demo/scripts/demo_main.txt
```
Hard needs: fastapi, uvicorn. Add `--llm ollama:qwen2.5:3b` for the implicit-sensitivity classifier
(needs `ollama serve` and `ollama pull qwen2.5:3b`; if Ollama is down it warns and continues without it).

## 2. audio: files instead of live voices

**Per-speaker files** (like LiveKit tracks; speaker = file name, so `alice.wav` is "alice"):
```
python -m otr.app --source audio --audio alice.wav bob.wav carol.wav --speed 1
python -m otr.app --source audio --audio my_meeting_folder/
```
Tracks start at 0 by default. To time-align them use an `offsets.json` next to the files
(`{"bob": 12.5}`) or a file name like `bob@12.5.wav`. Segments of all speakers are merged by the
time the utterance ended. A file called `mixed.*` in a folder with other tracks is ignored.

**One mixed file**:
```
python -m otr.app --source audio --audio meeting.wav --turns turns.json   # known speaker turns
python -m otr.app --source audio --audio meeting.wav                      # automatic labels
```
Without `--turns` it uses pyannote if installed and `HF_TOKEN` is set, otherwise a placeholder that
splits on pauses and alternates `SPEAKER_00`/`SPEAKER_01`. That placeholder is not speaker recognition.

Input format: 16-bit PCM `.wav` of any rate/channels is read and resampled to 16 kHz mono with
numpy alone (no ffmpeg). flac/ogg/mp3/float wav need `pip install soundfile` (or convert with
`ffmpeg -i in.mp3 -ar 16000 -ac 1 out.wav`).

Transcription runs once, before the server opens (progress on stderr; roughly 4 x 100 s of
audio took 17 s with `base.en` on this CPU), then playback is paced by `--speed` through the hold
buffer. The UI "restart" button replays the same transcript without re-transcribing.

**Demo audio without a microphone** (optional, Windows, no downloads; uses SAPI voices
David/Zira with different rates, so speakers sound alike in pairs):
```
python scripts/make_demo_audio.py          # writes demo_audio/{alice,bob,carol,dan,mixed}.wav, turns.json, timing.json
python -m otr.app --source audio --audio demo_audio --llm none
```
If no SAPI voice exists the script says so and exits 3; nothing else depends on it.

## 3. livekit (live voices, per-person consent)

```
python -m otr.app --source livekit
```
Runs `docker compose -f docker-compose.livekit.yml up -d` if the Docker daemon is up and port 7880 is
closed (`--no-docker` to skip; or run `livekit-server --dev` yourself). Open the page in two tabs or on
two machines; each person joins and starts "Not recorded". `livekit-stream` is the same transport but
auto-subscribes to everyone and has no consent buttons (testing only).
Hard needs: livekit, livekit-api, faster-whisper, Whisper weights, a reachable LiveKit server.

## What needs downloading (nothing happens at runtime)

| Item | Needed by | Command / size |
|---|---|---|
| Python packages | all | `pip install -r requirements-core.txt -r requirements-demo.txt`; audio/livekit also `-r requirements-ingest.txt` |
| Whisper weights | audio, livekit* | one time, `base.en` about 150 MB, `tiny.en` about 75 MB: `python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8', download_root='models/faster-whisper')"` |
| Presidio + spaCy model | optional, all | `pip install -r requirements-pii.txt && python -m spacy download en_core_web_lg` (regex fallback otherwise; `OTR_NO_PRESIDIO=1` forces it) |
| Ollama model | optional, `--llm ollama` | `ollama pull qwen2.5:3b` |
| LiveKit server image | livekit* | pulled by docker compose on first start |

Whisper weights are found in `$OTR_WHISPER_MODEL_DIR`, `models/faster-whisper/`, or the HuggingFace
cache (`~/.cache/huggingface/hub/models--Systran--faster-whisper-<model>`).
