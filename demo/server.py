"""Live demo server: SegmentSource -> StreamRunner(Pipeline) -> Events -> browser (SSE).

Run:
  python -m demo.server --script demo/scripts/demo_main.txt                   # replay (default)
  python -m demo.server --source livekit --room demo --pipeline real          # live voice
  python -m demo.server --pipeline real --llm ollama:qwen2.5:3b --script ...
Typed lines (POST /api/say, the box at the bottom of the page) work with every source.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import json
import os
import sys
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from otr.runtime import StreamRunner
from otr.types import Segment

STATIC = Path(__file__).parent / "static"


# ---------------------------------------------------------------- helpers
def load_script_segments(path) -> list[Segment]:
    """Script file -> Segments via otr.ingest.replay_source.parse_script.
    '@pause N' directives (which parse_script would treat as text) are handled here by
    shifting the timestamps of everything after them by N seconds."""
    from otr.ingest.replay_source import load_jsonl, parse_script
    p = Path(path)
    if p.suffix.lower() in (".jsonl", ".json"):
        return load_jsonl(p)
    chunks: list[tuple[float, list[str]]] = [(0.0, [])]
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("@pause"):
            try:
                chunks.append((float(line.split()[1]), []))
            except (IndexError, ValueError):
                pass
            continue
        chunks[-1][1].append(raw)
    out: list[Segment] = []
    t = 0.0
    for pause, lines in chunks:
        t += pause
        segs = parse_script("\n".join(lines), t0=t)
        for s in segs:
            s.id = f"s{len(out) + 1:04d}"
            out.append(s)
        if segs:
            t = segs[-1].t_end + 0.5
    return out


def load_pipeline_class(kind: str):
    """kind: real | fake | auto. Lazy import of the real pipeline."""
    if kind in ("real", "auto"):
        try:
            return importlib.import_module("otr.pipeline").Pipeline, "real"
        except Exception as e:  # ImportError or a broken module
            print(f"[demo] otr.pipeline unavailable ({e!r}); falling back to fake", file=sys.stderr)
    from demo.fake_pipeline import Pipeline
    return Pipeline, "fake"


def build_llm(spec: str):
    """'none' | 'ollama:MODEL'. Falls back to None (with a warning) if unavailable."""
    if not spec or spec == "none":
        return None
    if spec.startswith("ollama"):
        model = spec.partition(":")[2] or "qwen2.5:3b"
        try:
            from otr.llm import OllamaLLM
            llm = OllamaLLM(model=model)
            urllib.request.urlopen(llm.host + "/api/tags", timeout=1.5).read()
            return llm
        except Exception as e:
            print(f"[demo] WARNING: Ollama model {model!r} unavailable ({e!r}); running with --llm none",
                  file=sys.stderr)
            return None
    print(f"[demo] WARNING: unknown --llm {spec!r}; running with --llm none", file=sys.stderr)
    return None


def build_livekit_source(room: str):
    """Lazy-import the LiveKit source; raise RuntimeError with a clear message if unusable."""
    missing = [m for m in ("livekit", "faster_whisper") if importlib.util.find_spec(m) is None]
    if missing:
        raise RuntimeError("LiveKit mode needs the packages " + ", ".join(missing)
                           + " (pip install -r requirements-ingest.txt)")
    if not os.environ.get("LIVEKIT_URL"):
        print("[demo] LIVEKIT_URL not set; using ws://localhost:7880 with devkey/secret "
              "(docker compose -f docker-compose.livekit.yml up -d)", file=sys.stderr)
    try:
        from otr.ingest.livekit_source import LiveKitSource
    except ImportError as e:
        raise RuntimeError(f"otr.ingest.livekit_source not importable: {e}") from e
    return LiveKitSource(room=room)


# ---------------------------------------------------------------- app
def create_app(pipeline="auto", script=None, speed=1.0, hold_seconds=10.0, autostart=True,
               source="replay", room="demo", llm=None, tick_interval=0.25, live_source=None):
    """source: 'replay' (script optional; typed lines always work) or 'livekit'."""
    cls, kind = load_pipeline_class(pipeline)
    if source == "livekit":  # per-person consent mode (demo/live_session.py)
        from demo.live_session import create_live_app
        return create_live_app(cls, kind, live_source=live_source, hold_seconds=hold_seconds,
                               autostart=autostart)

    def new_pipe():
        return cls(llm=llm, hold_seconds=hold_seconds)

    def new_source():
        if source == "livekit-stream":
            return build_livekit_source(room)
        if script and autostart:
            from otr.ingest.replay_source import ReplaySource
            return ReplaySource(load_script_segments(script), speed=speed)
        return None

    src = new_source()
    runner = StreamRunner(src, new_pipe(), tick_interval=tick_interval, hold_seconds=hold_seconds,
                          pipeline_kind=kind, source_name=source if src is not None else "typed",
                          source_factory=(new_source if source == "livekit-stream" else None),
                          reconnect=(source == "livekit-stream"))

    @asynccontextmanager
    async def lifespan(app):
        runner.start()
        yield
        await runner.stop()

    app = FastAPI(title="OTR demo", lifespan=lifespan)
    app.state.runner = runner

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    async def state():
        h = runner.health()
        return {"pipeline": kind, "hold_seconds": runner.hold_seconds, "done": runner.done,
                "source": h["source"], "source_state": h["source_state"],
                "health": h, "pending": runner.pending_confirms(),
                "notes": runner.notes(), "audit": runner.audit()}

    @app.get("/api/health")
    async def health():
        return runner.health()

    @app.get("/stream")
    async def stream(request: Request, since: int | None = None, once: bool = False):
        """SSE. Replays history after `since` (or Last-Event-ID), then follows live.
        once=1 ends the stream after the 'done' message."""
        last = request.headers.get("last-event-id")
        if last and last.isdigit():
            since = int(last)
        sub = runner.subscribe(since)

        async def gen():
            try:
                yield "retry: 1500\n\n"
                while True:
                    try:
                        m = await asyncio.wait_for(sub.get(), 10)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        if await request.is_disconnected():
                            return
                        continue
                    idline = f"id: {m['seq']}\n" if "seq" in m else ""
                    yield f"{idline}data: {json.dumps(m)}\n\n"
                    if once and m["type"] == "done":
                        return
            finally:
                runner.unsubscribe(sub)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/say")
    async def say(body: dict):
        speaker = str(body.get("speaker", "")).strip() or "Presenter"
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "text required")
        seg = await runner.say(speaker, text)
        return {"segment_id": seg.id}

    @app.post("/api/confirm")
    async def confirm(body: dict):
        sid = body.get("segment_id")
        if not sid or "keep_out" not in body:
            raise HTTPException(400, "segment_id and keep_out required")
        evs = await runner.confirm(str(sid), bool(body["keep_out"]))
        return {"events": [e.to_dict() for e in evs]}

    @app.post("/api/hold")
    async def hold(body: dict):
        try:
            sec = float(body.get("seconds"))
        except (TypeError, ValueError):
            raise HTTPException(400, "seconds required")
        sec = max(0.0, min(120.0, sec))
        runner.set_hold_seconds(sec)
        return {"hold_seconds": sec}

    @app.post("/api/restart")
    async def restart():
        await runner.restart(new_pipe(), new_source(), new_source if source == "livekit" else None)
        return {"ok": True}

    @app.post("/api/flush")
    async def flush():
        await runner.flush()
        return {"ok": True}

    return app


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="OTR live demo server")
    ap.add_argument("--source", choices=["replay", "livekit", "livekit-stream"], default="replay")
    ap.add_argument("--script", help="replay script ('Alice: text' per line, '@pause N' ok) or .jsonl")
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed multiplier")
    ap.add_argument("--room", default="demo", help="LiveKit room name")
    ap.add_argument("--hold", type=float, default=10.0, help="initial hold seconds")
    ap.add_argument("--pipeline", choices=["real", "fake"], default=None)
    ap.add_argument("--llm", default="none", help="none | ollama:MODEL")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    if a.source == "replay" and not a.script:
        print("[demo] no --script given: idle, type lines in the page", file=sys.stderr)
    live_source = None
    if a.source == "livekit":
        try:
            from otr.ingest.livekit_source import LiveKitSource
            live_source = LiveKitSource(room=os.environ.get("LIVEKIT_ROOM", a.room),
                                        model=os.environ.get("OTR_WHISPER_MODEL", "base.en"))
        except ImportError as e:
            print(f"[demo] LiveKit mode unavailable: {e}", file=sys.stderr)
            return 2
    try:
        app = create_app(a.pipeline or "auto", a.script, a.speed, a.hold, source=a.source,
                         room=a.room, llm=build_llm(a.llm), live_source=live_source)
    except (RuntimeError, OSError) as e:
        print(f"[demo] cannot start: {e}", file=sys.stderr)
        return 2

    import uvicorn
    r = getattr(app.state, "runner", None)
    if r is not None:
        print(f"[demo] source={r.source_name} pipeline={r.pipeline_kind}  open http://{a.host}:{a.port}/")
    else:
        print(f"[demo] consent mode  open http://{a.host}:{a.port}/")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
