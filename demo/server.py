"""Live demo server: segments -> otr Pipeline -> Events -> browser (SSE).

Run:  python -m demo.server --script demo/scripts/demo_main.txt
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import re
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from otr.types import Segment

STATIC = Path(__file__).parent / "static"
LINE_RE = re.compile(r"^\s*([^:#@][^:]{0,40}?)\s*:\s*(.+?)\s*$")


# ---------------------------------------------------------------- helpers
def parse_script(path) -> list[tuple[str, str, float]]:
    """Parse 'Speaker: text' lines -> [(speaker, text, delay_before_seconds)].
    '# comment' and blank lines are skipped; '@pause N' adds N seconds before the next line.
    (Own parser; the demo does not depend on otr.ingest.replay_source.)"""
    out, extra = [], 0.0
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@pause"):
            try:
                extra += float(line.split()[1])
            except (IndexError, ValueError):
                pass
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        speaker, text = m.group(1), m.group(2)
        delay = max(1.5, len(text.split()) * 0.33) + extra
        out.append((speaker, text, delay))
        extra = 0.0
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


# ---------------------------------------------------------------- session
class Session:
    def __init__(self, pipeline_cls, kind, script=None, speed=1.0, hold_seconds=10.0, llm=None):
        self.pipeline_cls, self.kind = pipeline_cls, kind
        self.script, self.speed, self.hold_seconds, self.llm = script, speed, hold_seconds, llm
        self.messages: list[dict] = []
        self.done = False
        self.tasks: list = []
        self._reset()

    def _reset(self):
        self.pipe = self.pipeline_cls(llm=self.llm, hold_seconds=self.hold_seconds)
        self.t0 = time.monotonic()
        self.n = 0
        self.done = False
        self.messages.append({"type": "reset", "hold_seconds": self.hold_seconds, "pipeline": self.kind})

    def now(self) -> float:
        return time.monotonic() - self.t0

    def _emit(self, events):
        if not events:
            return
        self.messages.append({
            "type": "events",
            "events": [e.to_dict() for e in events],
            "notes": [s.to_dict() for s in self.pipe.notes()],
            "audit": [e.to_dict() for e in self.pipe.audit_log()],
        })

    def say(self, speaker: str, text: str):
        self.n += 1
        t = self.now()
        seg = Segment(id=f"u{self.n}", speaker=speaker, text=text, t_start=t, t_end=t)
        self.messages.append({"type": "segment", "segment": seg.to_dict()})
        self._emit(self.pipe.push(seg, now=t))
        return seg

    def tick(self):
        self._emit(self.pipe.tick(self.now()))

    def confirm(self, segment_id: str, keep_out: bool):
        evs = self.pipe.confirm(segment_id, keep_out)
        self._emit(evs)
        return evs

    def set_hold(self, seconds: float):
        self.hold_seconds = seconds
        if hasattr(self.pipe, "hold_seconds"):
            self.pipe.hold_seconds = seconds
        self.messages.append({"type": "config", "hold_seconds": seconds})

    def flush(self):
        self._emit(self.pipe.flush())

    # -- background work
    async def _ticker(self):
        while True:
            await asyncio.sleep(0.2)
            self.tick()

    async def _replay(self, lines):
        for speaker, text, delay in lines:
            await asyncio.sleep(delay / self.speed)
            self.say(speaker, text)
        # let the last lines age out, then end of meeting
        await asyncio.sleep(self.hold_seconds + 0.5)
        self.flush()
        self.done = True
        self.messages.append({"type": "done"})

    def start(self, replay=True):
        self.stop()
        self.tasks.append(asyncio.ensure_future(self._ticker()))
        if self.script and replay:
            self.tasks.append(asyncio.ensure_future(self._replay(parse_script(self.script))))

    def stop(self):
        for t in self.tasks:
            t.cancel()
        self.tasks = []

    def restart(self):
        self.stop()
        self._reset()
        self.start()


# ---------------------------------------------------------------- app
def create_app(pipeline="auto", script=None, speed=1.0, hold_seconds=10.0, autostart=True):
    cls, kind = load_pipeline_class(pipeline)
    session = Session(cls, kind, script=script, speed=speed, hold_seconds=hold_seconds)

    @asynccontextmanager
    async def lifespan(app):
        session.start(replay=autostart)
        yield
        session.stop()

    app = FastAPI(title="OTR demo", lifespan=lifespan)
    app.state.session = session

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    async def state():
        return {"pipeline": kind, "hold_seconds": session.hold_seconds, "done": session.done,
                "messages": len(session.messages),
                "notes": [s.to_dict() for s in session.pipe.notes()],
                "audit": [e.to_dict() for e in session.pipe.audit_log()]}

    @app.get("/stream")
    async def stream(request: Request, since: int = 0, once: bool = False):
        """SSE. Replays history from `since` (or Last-Event-ID), then follows live.
        once=1 ends the stream when the session is done and the client is caught up."""
        last = request.headers.get("last-event-id")
        if last and last.isdigit():
            since = int(last) + 1

        async def gen():
            i = since
            idle = 0
            while True:
                while i < len(session.messages):
                    yield f"id: {i}\ndata: {json.dumps(session.messages[i])}\n\n"
                    i += 1
                    idle = 0
                if once and session.done:
                    return
                await asyncio.sleep(0.1)
                idle += 1
                if idle % 150 == 0:
                    yield ": keepalive\n\n"
                    if await request.is_disconnected():
                        return

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/say")
    async def say(body: dict):
        speaker = str(body.get("speaker", "")).strip() or "Presenter"
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "text required")
        seg = session.say(speaker, text)
        return {"segment_id": seg.id}

    @app.post("/api/confirm")
    async def confirm(body: dict):
        sid = body.get("segment_id")
        if not sid or "keep_out" not in body:
            raise HTTPException(400, "segment_id and keep_out required")
        evs = session.confirm(str(sid), bool(body["keep_out"]))
        return {"events": [e.to_dict() for e in evs]}

    @app.post("/api/hold")
    async def hold(body: dict):
        try:
            sec = float(body.get("seconds"))
        except (TypeError, ValueError):
            raise HTTPException(400, "seconds required")
        sec = max(0.0, min(120.0, sec))
        session.set_hold(sec)
        return {"hold_seconds": sec}

    @app.post("/api/restart")
    async def restart():
        session.restart()
        return {"ok": True}

    @app.post("/api/flush")
    async def flush():
        session.flush()
        return {"ok": True}

    return app


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="OTR live demo server")
    ap.add_argument("--script", help="script file ('Alice: text' per line)")
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed multiplier")
    ap.add_argument("--hold", type=float, default=10.0, help="initial hold seconds")
    ap.add_argument("--pipeline", choices=["real", "fake"], default=None)
    ap.add_argument("--source", choices=["replay", "livekit"], default="replay")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    if a.source == "livekit":
        try:
            importlib.import_module("otr.ingest.livekit_source")
        except ImportError as e:
            print("LiveKit mode needs otr/ingest/livekit_source.py, which is not available "
                  f"({e}). Use --source replay, or type lines in the page.", file=sys.stderr)
            return 2
        print("otr.ingest.livekit_source found, but live wiring into the demo is not implemented yet; "
              "use replay/typed input.", file=sys.stderr)
        return 2

    import uvicorn
    app = create_app(a.pipeline or "auto", a.script, a.speed, a.hold)
    print(f"[demo] pipeline={app.state.session.kind}  open http://{a.host}:{a.port}/")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
