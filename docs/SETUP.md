# Setup for a new teammate (Windows)

Goal: a machine where the full local pipeline runs with no network at demo time. Sizes are approximate; check the sources if you are on a metered link.

## 1. Quick path

```powershell
git clone https://github.com/Dee-1862/agent-filter.git
cd agent-filter
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements-core.txt -r requirements-demo.txt -r requirements-ingest.txt -r requirements-pii.txt
python scripts/check_env.py
```

`check_env.py` is read-only. It prints a table (Python, packages, spaCy model, Whisper model, Ollama and its models, GPU/VRAM, Docker CLI and daemon, LiveKit on port 7880, disk, RAM) and, under "Next commands", the exact command for each missing item. Fix those, rerun until it says nothing is missing, then run `python -m pytest -q`.

## 2. Everything you download

| What | Command | Size (approx) | Needed for |
|---|---|---|---|
| Python 3.12 | python.org installer | 25 MB | everything |
| pip packages (core, demo, ingest, bench) | `pip install -r requirements-*.txt` | 0.3-0.6 GB | app, tests, live audio |
| Presidio + spaCy | `pip install -r requirements-pii.txt` | 0.1 GB | PII detection (regex fallback works without it) |
| spaCy model `en_core_web_sm` | `python -m spacy download en_core_web_sm` | ~13 MB | Presidio NER; the default for now. otr/pii.py prefers `en_core_web_lg` if installed, else sm. Email, phone, SSN and card recognizers are regex-based and do not depend on model size; only NER entities such as PERSON do |
| spaCy model `en_core_web_lg` (optional upgrade) | `python -m spacy download en_core_web_lg` | ~400 MB | Better name detection. Slow on a weak connection; resumable with `curl -C -` against the wheel URL |
| Whisper `base.en` (faster-whisper) | `python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8', download_root='models/faster-whisper')"` | ~150 MB | live speech-to-text |
| Ollama for Windows | https://ollama.com/download/windows | ~1 GB | local LLM |
| Ollama model `qwen3.5:4b` (or whatever `otr/llm.py` defaults to; `check_env.py --model NAME` overrides) | `ollama pull qwen3.5:4b` | ~3 GB | contextual classification |
| LiveKit server | Docker Desktop (~600 MB installer) plus the `livekit/livekit-server` image (~100 MB), or the native `livekit-server.exe` from the LiveKit releases page (~50 MB) | 0.1-0.7 GB | live meeting room |

Total on a clean machine: roughly 5-6 GB. Keep 10 GB free.

## 3. Start the services

```powershell
ollama serve                                   # skip if the Ollama tray app is running
docker compose -f docker-compose.livekit.yml up -d   # needs Docker Desktop running; or: livekit-server --dev
python -m demo.server --source livekit --pipeline real --host 127.0.0.1 --port 8765
```

See [INGEST.md](INGEST.md) for the meeting page and bot, and [LOCAL_PRIVACY.md](LOCAL_PRIVACY.md) for the data boundary.

## 4. Switches

- `OTR_NO_PRESIDIO=1` forces the regex PII path (what most tests set; fastest, least coverage).
- `OTR_WHISPER_MODEL_DIR=<dir containing model.bin>` points STT at a pre-downloaded model and keeps it offline.
- Docker is optional. If the daemon is not running, `check_env.py` shows WARN and the command to start it.

## 5. Common problems

- `OSError: [E050] Can't find model 'en_core_web_lg'`: run the spaCy download command above. The app still works on regex until then.
- Ollama model MISSING while the server is OK: run the `ollama pull` line the script printed.
- Port 7880 closed: LiveKit is not running; see section 3.
- GPU: `nvidia-smi` is used only to report VRAM. A 4B model at 4-bit needs about 3 GB of VRAM; CPU also works, slower.
