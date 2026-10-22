"""Readiness table for a new machine. Usage: python scripts/check_env.py [--model NAME]

Read-only: it never installs, pulls, or starts anything; it prints the exact next commands.
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import inspect
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request

OK, WARN, MISSING = "OK", "WARN", "MISSING"
rows: list[tuple[str, str, str]] = []
todo: list[str] = []


def add(name: str, status: str, detail: str = "", fix: str = "") -> None:
    rows.append((name, status, detail))
    if fix and status != OK:
        todo.append(f"{name}: {fix}")


def run(cmd: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # missing exe, timeout
        return 127, str(e)


def tcp(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def default_model() -> str:
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from otr.llm import OllamaLLM
        d = inspect.signature(OllamaLLM.__init__).parameters["model"].default
        if isinstance(d, str) and d:
            return d
    except Exception:
        pass
    return os.environ.get("OTR_LLM_MODEL", "qwen3.5:4b")


def check_python() -> None:
    v = sys.version_info
    ok = (3, 10) <= v[:2] < (3, 14)
    add("Python", OK if ok else WARN, f"{v.major}.{v.minor}.{v.micro}", "install Python 3.12 from python.org")


def check_packages() -> None:
    pkgs = [("presidio-analyzer", "pip install presidio-analyzer presidio-anonymizer"),
            ("presidio-anonymizer", "pip install presidio-anonymizer"),
            ("spacy", "pip install spacy"),
            ("faster-whisper", "pip install -r requirements-ingest.txt"),
            ("livekit", "pip install -r requirements-ingest.txt"),
            ("livekit-api", "pip install -r requirements-ingest.txt"),
            ("fastapi", "pip install -r requirements-demo.txt"),
            ("uvicorn", "pip install -r requirements-demo.txt"),
            ("matplotlib", "pip install -r requirements-bench.txt"),
            ("pytest", "pip install pytest")]
    for name, fix in pkgs:
        try:
            add(f"pkg {name}", OK, md.version(name))
        except md.PackageNotFoundError:
            add(f"pkg {name}", MISSING, "", fix)
    try:
        import spacy
        installed = set(spacy.util.get_installed_models())
        if "en_core_web_lg" in installed:
            add("spaCy model", OK, "en_core_web_lg")
        elif "en_core_web_sm" in installed:
            add("spaCy model", WARN, "only en_core_web_sm (less accurate)", "python -m spacy download en_core_web_lg  (~400 MB)")
        else:
            add("spaCy model", MISSING, "", "python -m spacy download en_core_web_lg  (~400 MB)")
    except Exception:
        add("spaCy model", MISSING, "spacy not importable", "pip install spacy, then python -m spacy download en_core_web_lg")


def check_whisper() -> None:
    d = os.environ.get("OTR_WHISPER_MODEL_DIR")
    cands = [d] if d else []
    cands += ["models/faster-whisper", os.path.expanduser("~/.cache/huggingface/hub")]
    for c in cands:
        if c and os.path.isdir(c):
            hit = any("whisper" in n.lower() for n in os.listdir(c)) or os.path.exists(os.path.join(c, "model.bin"))
            if hit:
                add("Whisper model", OK, c)
                return
    add("Whisper model", MISSING, "", "python -c \"from faster_whisper import WhisperModel; "
        "WhisperModel('base.en', device='cpu', compute_type='int8', download_root='models/faster-whisper')\"  (~150 MB)")


def check_ollama(model: str) -> None:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not host.startswith("http"):
        host = "http://" + host
    exe = shutil.which("ollama")
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        add("Ollama server", MISSING if not exe else WARN,
            "CLI found, server not answering" if exe else "not installed",
            "ollama serve  (or start the Ollama app)" if exe else "install from https://ollama.com/download/windows")
        add(f"Ollama model {model}", MISSING, "", f"ollama pull {model}")
        return
    add("Ollama server", OK, host)
    add("Ollama models", OK if names else WARN, ", ".join(names) or "none", "" if names else f"ollama pull {model}")
    have = any(n == model or n.split(":")[0] == model and ":" not in model for n in names)
    add(f"Ollama model {model}", OK if have else MISSING, "default model" , f"ollama pull {model}")


def check_gpu() -> None:
    if not shutil.which("nvidia-smi"):
        add("GPU", WARN, "no nvidia-smi (CPU only; fine for small models)")
        return
    rc, out = run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader"])
    add("GPU / VRAM", OK if rc == 0 else WARN, out.strip().replace("\n", " | ")[:120])


def check_docker() -> None:
    if not shutil.which("docker"):
        add("Docker CLI", WARN, "not installed (optional: native livekit-server also works)",
            "install Docker Desktop, or download livekit-server from https://github.com/livekit/livekit/releases")
        return
    add("Docker CLI", OK, run(["docker", "--version"])[1].strip()[:60])
    rc, _ = run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)
    add("Docker daemon", OK if rc == 0 else WARN, "answering" if rc == 0 else "not running",
        "start Docker Desktop and wait for the whale icon to settle")


def check_livekit() -> None:
    up = tcp("localhost", 7880)
    add("LiveKit ws://localhost:7880", OK if up else WARN, "port open" if up else "nothing listening",
        "docker compose -f docker-compose.livekit.yml up -d   (or: livekit-server --dev)")


def check_resources() -> None:
    free = shutil.disk_usage(os.getcwd()).free / 1e9
    add("Free disk", OK if free >= 10 else WARN, f"{free:.1f} GB", "free up at least 10 GB for models")
    ram = None
    if os.name == "nt":
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("p", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                            ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            ms = MS(); ms.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            ram = (ms.total / 2**30, ms.avail / 2**30)
        except Exception:
            pass
    else:
        try:
            pages, avail = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_AVPHYS_PAGES")
            sz = os.sysconf("SC_PAGE_SIZE")
            ram = (pages * sz / 2**30, avail * sz / 2**30)
        except Exception:
            pass
    if ram:
        add("RAM", OK if ram[0] >= 8 else WARN, f"{ram[0]:.1f} GiB total, {ram[1]:.1f} GiB free")
    else:
        add("RAM", WARN, "unknown")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="Ollama model to require (default: otr.llm default)")
    a = ap.parse_args()
    model = a.model or default_model()
    check_python(); check_packages(); check_whisper(); check_ollama(model)
    check_gpu(); check_docker(); check_livekit(); check_resources()
    w = max(len(r[0]) for r in rows)
    print(f"{'CHECK'.ljust(w)}  {'STATUS':8} DETAIL")
    print("-" * (w + 40))
    for n, s, d in rows:
        print(f"{n.ljust(w)}  {s:8} {d}")
    if todo:
        print("\nNext commands:")
        for t in dict.fromkeys(todo):
            print("  - " + t)
    bad = [r for r in rows if r[1] == MISSING]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} ready, {len(bad)} missing.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
