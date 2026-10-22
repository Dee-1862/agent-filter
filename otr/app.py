"""Single entry point: pick a source, check readiness, start the demo server.

  python -m otr.app --source replay --script demo/scripts/demo_main.txt
  python -m otr.app --source audio --audio demo_audio            # per-speaker WAVs in a folder
  python -m otr.app --source audio --audio mixed.wav --turns turns.json
  python -m otr.app --source livekit                              # per-person consent mode
  python -m otr.app --source livekit-stream                       # all participants, auto-subscribed
  python -m otr.app --source replay --check                       # only print the readiness table

Only the chosen source's requirements are checked. A failing hard requirement stops the start
with the fix command; soft ones (Ollama, Presidio) just print a warning and the run continues
with rules/regex only. Nothing is downloaded at runtime.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
LIVEKIT_PORT = 7880
COMPOSE_FILE = "docker-compose.livekit.yml"
SOURCES = ("livekit", "livekit-stream", "audio", "replay")


# ---------------------------------------------------------------- probes (injectable for tests)
def _http_json(url: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _docker_ok() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _run(cmd: list[str], cwd: Optional[Path] = None) -> int:
    try:
        return subprocess.run(cmd, cwd=str(cwd) if cwd else None, timeout=300).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _presidio() -> tuple[bool, str]:
    if os.environ.get("OTR_NO_PRESIDIO"):
        return False, "disabled by OTR_NO_PRESIDIO"
    try:
        from otr import pii
        ok = pii.presidio_available()
        return ok, pii.presidio_model() if ok else "spaCy model missing"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _whisper_dir(model: str) -> Optional[Path]:
    from otr.ingest.audio_file_source import find_whisper_dir
    return find_whisper_dir(model)


@dataclass
class Env:
    """Everything preflight touches, so tests can replace it."""
    http_json: Callable[..., dict] = _http_json
    port_open: Callable[[str, int], bool] = _port_open
    docker_ok: Callable[[], bool] = _docker_ok
    run: Callable[..., int] = _run
    has_module: Callable[[str], bool] = _has_module
    presidio: Callable[[], tuple] = _presidio
    whisper_dir: Callable[[str], Optional[Path]] = _whisper_dir
    exists: Callable[[str], bool] = lambda p: Path(p).exists()
    sleep: Callable[[float], None] = time.sleep


@dataclass
class Check:
    name: str
    status: str            # ok | warn | FAIL
    detail: str
    fix: str = ""

    @property
    def blocking(self) -> bool:
        return self.status == "FAIL"


@dataclass
class Options:
    source: str = "replay"
    audio: list = field(default_factory=list)
    turns: Optional[str] = None
    script: Optional[str] = None
    llm: str = "none"
    hold: float = 10.0
    speed: float = 1.0
    port: int = 8000
    host: str = "127.0.0.1"
    model: Optional[str] = None
    room: str = "demo"
    no_docker: bool = False


def whisper_model(o: Options) -> str:
    return o.model or os.environ.get("OTR_WHISPER_MODEL") or "base.en"


def llm_model(spec: str) -> str:
    from otr.llm import default_model
    return spec.partition(":")[2] or default_model()


# ---------------------------------------------------------------- preflight
def preflight(o: Options, env: Optional[Env] = None) -> list[Check]:
    env = env or Env()
    checks: list[Check] = []
    add = lambda *a: checks.append(Check(*a))  # noqa: E731
    pip_demo = "pip install -r requirements-core.txt -r requirements-demo.txt"
    pip_ingest = "pip install -r requirements-ingest.txt"

    for mod in ("fastapi", "uvicorn"):
        add(f"python: {mod}", "ok" if env.has_module(mod) else "FAIL",
            "installed" if env.has_module(mod) else "missing", "" if env.has_module(mod) else pip_demo)
    if env.port_open(o.host, o.port):
        add(f"port {o.port}", "FAIL", "already in use", f"choose another: --port {o.port + 1}")
    else:
        add(f"port {o.port}", "ok", "free")

    ok, detail = env.presidio()
    add("Presidio PII model", "ok" if ok else "warn",
        detail if ok else f"{detail}; regex-only PII detection",
        "" if ok else "pip install -r requirements-pii.txt && python -m spacy download en_core_web_lg")

    if o.llm and o.llm != "none":
        _check_ollama(o, env, add)

    if o.source == "replay":
        if o.script:
            ok = env.exists(o.script)
            add("script", "ok" if ok else "FAIL", o.script if ok else f"not found: {o.script}",
                "" if ok else "see demo/scripts/*.txt")
        else:
            add("script", "warn", "none: idle, type lines in the page")
    if o.source == "audio":
        _check_audio(o, env, add)
    if o.source in ("audio", "livekit", "livekit-stream"):
        fw = env.has_module("faster_whisper")
        add("faster-whisper", "ok" if fw else "FAIL", "installed" if fw else "missing",
            "" if fw else pip_ingest)
        model = whisper_model(o)
        d = env.whisper_dir(model)
        add(f"Whisper weights ({model})", "ok" if d else "FAIL", str(d) if d else "not on disk",
            "" if d else (f"python -c \"from faster_whisper import WhisperModel; WhisperModel('{model}', "
                          "device='cpu', compute_type='int8', download_root='models/faster-whisper')\"  "
                          "(one-time, base.en ~150 MB, tiny.en ~75 MB; use --model tiny.en on slow networks)"))
    if o.source in ("livekit", "livekit-stream"):
        _check_livekit(o, env, add)
    return checks


def _check_ollama(o: Options, env: Env, add) -> None:
    from otr.llm import default_host
    host, model = default_host(), llm_model(o.llm)
    try:
        names = [m.get("name", "") for m in env.http_json(host + "/api/tags").get("models", [])]
    except Exception as e:  # noqa: BLE001
        add("Ollama", "warn", f"not reachable at {host} ({type(e).__name__}); running with rules only",
            "ollama serve   (or use --llm none)")
        return
    have = {n for n in names} | {n[:-7] for n in names if n.endswith(":latest")}
    if model in have:
        add(f"Ollama model {model}", "ok", f"installed at {host}")
    else:
        add(f"Ollama model {model}", "warn", "server up but model not installed; running with rules only",
            f"ollama pull {model}")


def _check_audio(o: Options, env: Env, add) -> None:
    if not o.audio:
        add("audio input", "FAIL", "no --audio given", "--audio demo_audio   (folder or files)")
        return
    bad = [p for p in o.audio if not env.exists(p)]
    if bad:
        add("audio input", "FAIL", "not found: " + ", ".join(bad),
            "python scripts/make_demo_audio.py   (optional local TTS demo, Windows)")
    else:
        add("audio input", "ok", ", ".join(map(str, o.audio)))
    if o.turns and not env.exists(o.turns):
        add("turns json", "FAIL", f"not found: {o.turns}")
    if any(str(p).lower().endswith((".mp3", ".flac", ".ogg", ".opus")) for p in o.audio):
        sf = env.has_module("soundfile")
        add("soundfile", "ok" if sf else "FAIL", "installed" if sf else "needed for non-wav audio",
            "" if sf else "pip install soundfile   (or convert: ffmpeg -i in.mp3 -ar 16000 -ac 1 out.wav)")


def _check_livekit(o: Options, env: Env, add) -> None:
    lk = env.has_module("livekit") and env.has_module("livekit.api")
    add("python: livekit", "ok" if lk else "FAIL", "installed" if lk else "missing",
        "" if lk else "pip install -r requirements-ingest.txt")
    open_ = env.port_open("127.0.0.1", LIVEKIT_PORT)
    if open_:
        add(f"LiveKit port {LIVEKIT_PORT}", "ok", "server reachable")
        return
    if o.no_docker:
        add(f"LiveKit port {LIVEKIT_PORT}", "FAIL", "closed", f"docker compose -f {COMPOSE_FILE} up -d")
        return
    dk = env.docker_ok()
    add("Docker daemon", "ok" if dk else "FAIL", "running" if dk else "not running",
        "" if dk else "start Docker Desktop, or run a local livekit-server --dev")
    if dk:
        add(f"LiveKit port {LIVEKIT_PORT}", "warn", "closed; will run docker compose up -d",
            f"docker compose -f {COMPOSE_FILE} up -d")
    else:
        add(f"LiveKit port {LIVEKIT_PORT}", "FAIL", "closed and Docker is down",
            f"docker compose -f {COMPOSE_FILE} up -d   (or livekit-server --dev)")


def format_table(checks: list[Check]) -> str:
    w = max([len(c.name) for c in checks] + [4])
    lines = [f"{'check'.ljust(w)}  status  detail"]
    for c in checks:
        lines.append(f"{c.name.ljust(w)}  {c.status.ljust(6)}  {c.detail}")
        if c.fix and c.status != "ok":
            lines.append(f"{' ' * w}          fix: {c.fix}")
    return "\n".join(lines)


def ensure_livekit(o: Options, env: Env, wait_s: float = 25.0) -> bool:
    """Start the dev server with docker compose if the port is closed and Docker is up."""
    if env.port_open("127.0.0.1", LIVEKIT_PORT):
        return True
    if o.no_docker or not env.docker_ok():
        return False
    print(f"[app] starting LiveKit: docker compose -f {COMPOSE_FILE} up -d", file=sys.stderr)
    if env.run(["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"], cwd=ROOT) != 0:
        return False
    t0 = time.monotonic()
    while time.monotonic() - t0 < wait_s:
        if env.port_open("127.0.0.1", LIVEKIT_PORT):
            return True
        env.sleep(0.5)
    return env.port_open("127.0.0.1", LIVEKIT_PORT)


# ---------------------------------------------------------------- start
def build_llm(o: Options):
    """OllamaLLM warmed up, or None (rules only) when unavailable."""
    if not o.llm or o.llm == "none":
        return None
    from otr.llm import parse_llm_spec
    llm = parse_llm_spec(o.llm)
    if llm is None:
        print(f"[app] unknown --llm {o.llm!r}; using none", file=sys.stderr)
        return None
    print(f"[app] warming LLM {llm.model} (first call loads it into memory)...", file=sys.stderr, flush=True)
    secs = llm.warmup()
    if secs == float("inf"):
        print("[app] WARNING: LLM warm-up failed; continuing with rules only", file=sys.stderr)
        return None
    print(f"[app] LLM ready ({secs:.1f}s)", file=sys.stderr)
    return llm


def build_audio_source(o: Options):
    from otr.ingest.audio_file_source import AudioFileSource
    src = AudioFileSource(o.audio, turns=o.turns, speed=o.speed, model=whisper_model(o))
    src.load_model()
    src.transcribe_all()   # up front, so playback is smooth; also cached for /api/restart
    return src


def make_app(o: Options, llm=None, audio_src=None):
    """Build the FastAPI app via demo.server.create_app (imported lazily; demo/ is not modified)."""
    from demo import server as ds
    if o.source == "audio":
        # create_app has no custom-source hook: reuse its replay path (so restart works too) by
        # swapping the two lookups it makes at call time for our pre-transcribed AudioFileSource.
        import otr.ingest.replay_source as rs
        orig_load, orig_cls = ds.load_script_segments, rs.ReplaySource
        ds.load_script_segments = lambda path: path
        rs.ReplaySource = lambda segs, speed=1.0: audio_src.clone(speed=speed)
        try:
            app = ds.create_app("auto", "audio-source", o.speed, o.hold, source="replay", llm=llm)
        finally:
            ds.load_script_segments, rs.ReplaySource = orig_load, orig_cls
        runner = app.state.runner
        if getattr(runner, "_source", None) is None:   # demo.server changed shape: inject directly
            runner._source = audio_src.clone()
            runner.source_state = "starting"
        runner.source_name = "audio"
        return app
    live_source = None
    if o.source == "livekit":
        from otr.ingest.livekit_source import LiveKitSource
        live_source = LiveKitSource(room=os.environ.get("LIVEKIT_ROOM", o.room), model=whisper_model(o))
    return ds.create_app("auto", o.script, o.speed, o.hold, source=o.source, room=o.room, llm=llm,
                         live_source=live_source)


def _auto_llm() -> str:
    """"ollama" if the local Ollama answers and has the default model, else "none" (rules only)."""
    try:
        from otr.llm import OllamaLLM, default_model
        have = [str(m.get("name", m)) if isinstance(m, dict) else str(m) for m in OllamaLLM().installed()]
        want = default_model()
        if any(h == want or h.split(":")[0] == want.split(":")[0] for h in have):
            return "ollama"
    except Exception:  # noqa: BLE001 - any failure means no model, rules only
        pass
    print("[app] --llm auto: Ollama or the default model is not available, using rules only", file=sys.stderr)
    return "none"


def parse_args(argv=None) -> tuple[Options, bool]:
    ap = argparse.ArgumentParser(prog="python -m otr.app", description=__doc__.split("\n")[0])
    ap.add_argument("--source", choices=SOURCES, default="replay")
    ap.add_argument("--audio", nargs="+", metavar="PATH", help="folder / per-speaker files / one mixed file")
    ap.add_argument("--turns", help="speaker-turn JSON for a single mixed file")
    ap.add_argument("--script", help="replay script (Alice: text lines, @pause N) or .jsonl")
    ap.add_argument("--llm", default="auto", help="auto | none | ollama | ollama:MODEL (auto uses the local model when Ollama is running and has it)")
    ap.add_argument("--hold", type=float, default=None,
                    help="hold seconds before a line is released (default $OTR_HOLD_SECONDS, else 5 for "
                         "--source livekit and 10 otherwise; shorter = less time for a later 'strike that')")
    ap.add_argument("--fast", action="store_true", help="fastest redaction for demos: hold 2 s and utterances close after 450 ms of silence (a later 'strike that' has less time to catch a line)")
    ap.add_argument("--speed", type=float, default=1.0, help="1 = real time, 0 = as fast as possible (audio/replay)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", help="Whisper model, e.g. tiny.en (default $OTR_WHISPER_MODEL or base.en)")
    ap.add_argument("--room", default="demo", help="LiveKit room")
    ap.add_argument("--no-docker", action="store_true", help="never run docker compose for LiveKit")
    ap.add_argument("--check", action="store_true", help="print the readiness table and exit")
    a = ap.parse_args(argv)
    if a.llm == "auto":
        a.llm = _auto_llm()
    if a.fast:
        os.environ.setdefault("OTR_SILENCE_MS", "450")
        if a.hold is None and "OTR_HOLD_SECONDS" not in os.environ:
            a.hold = 2.0
    hold = a.hold
    if hold is None:
        try:
            hold = float(os.environ["OTR_HOLD_SECONDS"])
        except (KeyError, ValueError):
            hold = 5.0 if a.source == "livekit" else 10.0
    o = Options(source=a.source, audio=a.audio or [], turns=a.turns, script=a.script, llm=a.llm,
                hold=hold, speed=a.speed, port=a.port, host=a.host, model=a.model, room=a.room,
                no_docker=a.no_docker)
    return o, a.check


def main(argv=None, env: Optional[Env] = None) -> int:
    o, check_only = parse_args(argv)
    env = env or Env()
    checks = preflight(o, env)
    print(f"[app] source={o.source}  llm={o.llm}  hold={o.hold}s\n" + format_table(checks), file=sys.stderr)
    blockers = [c for c in checks if c.blocking]
    if o.source in ("livekit", "livekit-stream") and not check_only             and not env.port_open("127.0.0.1", LIVEKIT_PORT):
        if ensure_livekit(o, env):   # docker compose up -d, then judge again
            blockers = [c for c in preflight(o, env) if c.blocking]
    if check_only:
        return 1 if blockers else 0
    if blockers:
        print("[app] cannot start: " + "; ".join(f"{c.name} ({c.detail})" for c in blockers), file=sys.stderr)
        return 2

    try:
        llm = build_llm(o)
        audio_src = build_audio_source(o) if o.source == "audio" else None
        app = make_app(o, llm, audio_src)
    except (RuntimeError, ValueError, OSError, ImportError) as e:
        print(f"[app] cannot start: {e}", file=sys.stderr)
        return 2
    import uvicorn
    print(f"[app] open http://{o.host}:{o.port}/", file=sys.stderr, flush=True)
    uvicorn.run(app, host=o.host, port=o.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
