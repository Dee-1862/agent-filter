"""Live demo server: segments -> otr Pipeline -> Events -> browser (SSE).

Run:  python -m demo.server --script demo/scripts/demo_main.txt
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import re
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from otr.types import Segment

STATIC = Path(__file__).parent / "static"
LINE_RE = re.compile(r"^\s*([^:#@][^:]{0,40}?)\s*:\s*(.+?)\s*$")
SPOKEN_STOP_RE = re.compile(
    # Match a direct opening request. Whisper may mishear the last pronoun in
    # "please stop recording me"; the unambiguous imperative is sufficient.
    # Anchoring avoids stopping for "he said stop recording me" or
    # "don't stop recording me" in ordinary conversation.
    r"^\s*(?:hey[,.]?\s+)?(?:please[,.]?\s+)?(?:stop\s+recording\b"
    r"|(?:don't|do\s+not)\s+record\s+me\b"
    r"|i\s+(?:don't|do\s+not)\s+want\s+(?:this|that|my\s+voice|me)\s+(?:to\s+be\s+)?recorded\b)",
    re.I,
)


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


class LiveSession:
    """Consent-gated LiveKit input and a shared, approved-only transcript.

    Each speaker has their own policy pipeline. The temporary text and full
    audit trail stay in process memory and are never placed in ``messages``.
    """

    def __init__(self, pipeline_cls, kind, source, hold_seconds=10.0):
        self.pipeline_cls, self.kind, self.source = pipeline_cls, kind, source
        self.hold_seconds = hold_seconds
        self.messages = [{"type": "reset", "mode": "livekit", "pipeline": kind}]
        self.sessions: dict[str, str] = {}  # opaque browser session -> identity
        self.names: dict[str, str] = {}
        self.pipes: dict[str, object] = {}
        self.sensitive_paused: set[str] = set()
        self.approved: dict[str, dict] = {}
        self.tasks: list[asyncio.Task] = []
        self.t0 = time.monotonic()
        if hasattr(source, "on_participant_left"):
            source.on_participant_left = self.leave

    def identity_for(self, request: Request) -> str:
        sid = request.cookies.get("otr_session", "")
        identity = self.sessions.get(sid)
        if not identity:
            raise HTTPException(401, "Join the meeting first")
        return identity

    def snapshot(self) -> dict:
        consent = self.source.consent_snapshot()
        return {identity: {"name": name, "recording": bool(consent.get(identity, False)),
                           "sensitive_paused": identity in self.sensitive_paused}
                for identity, name in self.names.items()}

    def publish_participants(self):
        self.messages.append({"type": "participants", "participants": self.snapshot()})

    def set_consent(self, identity: str, enabled: bool, *, sensitive_pause: bool = False):
        if sensitive_pause:
            self.sensitive_paused.add(identity)
        else:
            self.sensitive_paused.discard(identity)
        self.source.set_consent(identity, enabled)
        if not enabled:
            # Drop buffered/private text. Previously approved lines remain until
            # an explicit retroactive removal is supported by the policy engine.
            self.pipes.pop(identity, None)
        self.publish_participants()

    def leave(self, identity: str):
        self.set_consent(identity, False)
        self.names.pop(identity, None)
        for sid, owner in list(self.sessions.items()):
            if owner == identity:
                del self.sessions[sid]
        self.publish_participants()

    def _pipe(self, identity: str):
        if identity not in self.pipes:
            self.pipes[identity] = self.pipeline_cls(hold_seconds=self.hold_seconds)
        return self.pipes[identity]

    def _publish_events(self, identity: str, events):
        # A sensitive hold must never turn into a user-approved publication in
        # this prototype. Stop the source first, discard its private pipeline,
        # and publish only a text-free status. Other speakers keep recording.
        if any(event.kind == "pending_confirm" for event in events):
            self.set_consent(identity, False, sensitive_pause=True)
            return
        safe = []
        for event in events:
            if event.kind == "committed" and self.source.consent_snapshot().get(identity, False):
                line = {"id": event.segment_id, "speaker": identity, "name": self.names.get(identity, identity),
                        "text": event.text}
                self.approved[event.segment_id] = line
                safe.append({"kind": "committed", "line": line})
            elif event.kind == "retro_removed":
                self.approved.pop(event.segment_id, None)
                safe.append({"kind": "removed", "id": event.segment_id})
            elif event.kind == "state_change" and event.state == "OFF":
                self.set_consent(identity, False)
        if safe:
            self.messages.append({"type": "transcript", "changes": safe})

    def push(self, segment: Segment):
        identity = segment.speaker
        if not self.source.consent_snapshot().get(identity, False):
            return
        if SPOKEN_STOP_RE.search(segment.text):
            self.set_consent(identity, False)
            return
        pipe = self._pipe(identity)
        self._publish_events(identity, pipe.push(segment, now=self.now()))

    def now(self):
        return time.monotonic() - self.t0

    async def _consume(self):
        try:
            async for segment in self.source.segments():
                self.push(segment)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[demo] LiveKit capture stopped: {exc}", file=sys.stderr)
            for identity in list(self.names):
                self.set_consent(identity, False)
            self.messages.append({"type": "service", "status": "Capture unavailable"})

    async def _ticker(self):
        while True:
            await asyncio.sleep(0.2)
            for identity, pipe in list(self.pipes.items()):
                if self.source.consent_snapshot().get(identity, False):
                    self._publish_events(identity, pipe.tick(self.now()))

    def start(self):
        self.tasks = [asyncio.create_task(self._consume()), asyncio.create_task(self._ticker())]

    def stop(self):
        for task in self.tasks:
            task.cancel()
        self.tasks = []


# ---------------------------------------------------------------- app
def create_app(pipeline="auto", script=None, speed=1.0, hold_seconds=10.0, autostart=True,
               source="replay", live_source=None):
    cls, kind = load_pipeline_class(pipeline)
    live = source == "livekit"
    if live:
        if live_source is None:
            from otr.ingest.livekit_source import LiveKitSource
            live_source = LiveKitSource()
        session = LiveSession(cls, kind, live_source, hold_seconds=hold_seconds)
    else:
        session = Session(cls, kind, script=script, speed=speed, hold_seconds=hold_seconds)

    @asynccontextmanager
    async def lifespan(app):
        if live:
            if autostart:
                session.start()
        else:
            session.start(replay=autostart)
        yield
        session.stop()

    app = FastAPI(title="OTR demo", lifespan=lifespan)
    app.state.session = session

    @app.get("/")
    async def index():
        return FileResponse(STATIC / ("live.html" if live else "index.html"))

    @app.get("/static/{asset}")
    async def static_asset(asset: str):
        if asset not in {"live.js", "livekit-client.umd.js", "live.css"}:
            raise HTTPException(404)
        return FileResponse(STATIC / asset)

    if live:
        @app.get("/api/config")
        async def config():
            # The LiveKit URL is public room transport configuration; secrets
            # are used only on the server to mint short-lived participant tokens.
            return {"mode": "livekit", "url": os.environ.get("LIVEKIT_PUBLIC_URL", session.source.url),
                    "room": session.source.room_name}

        @app.post("/api/join")
        async def join(body: dict):
            from datetime import timedelta
            from livekit import api
            name = str(body.get("name", "")).strip()[:60]
            if not name:
                raise HTTPException(400, "Display name required")
            identity = "person-" + uuid.uuid4().hex
            sid = secrets.token_urlsafe(32)
            token = (api.AccessToken(session.source.api_key, session.source.api_secret)
                     .with_identity(identity).with_name(name)
                     .with_ttl(timedelta(hours=2))
                     .with_grants(api.VideoGrants(room_join=True, room=session.source.room_name,
                                                  can_publish=True, can_subscribe=True))
                     .to_jwt())
            session.sessions[sid] = identity
            session.names[identity] = name
            session.set_consent(identity, False)
            response = JSONResponse({"identity": identity, "name": name, "token": token})
            response.set_cookie("otr_session", sid, httponly=True, samesite="strict",
                                secure=False, max_age=7200)
            return response

        @app.get("/api/me")
        async def me(request: Request):
            identity = session.identity_for(request)
            return {"identity": identity, "participants": session.snapshot(),
                    "lines": list(session.approved.values())}

        @app.post("/api/consent")
        async def consent(request: Request, body: dict):
            identity = session.identity_for(request)
            if body.get("recording") is not True and body.get("recording") is not False:
                raise HTTPException(400, "recording must be a boolean")
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                raise HTTPException(403, "Origin mismatch")
            session.set_consent(identity, body["recording"])
            return {"identity": identity, "recording": body["recording"]}

        @app.post("/api/leave")
        async def leave(request: Request):
            identity = session.identity_for(request)
            session.leave(identity)
            response = JSONResponse({"ok": True})
            response.delete_cookie("otr_session")
            return response

        @app.get("/stream")
        async def live_stream(request: Request):
            session.identity_for(request)
            async def gen():
                # Do not replay earlier approved text after retroactive deletion.
                # A fresh connection gets only the current approved snapshot.
                i = len(session.messages)
                yield f"data: {json.dumps({'type': 'participants', 'participants': session.snapshot()})}\n\n"
                yield f"data: {json.dumps({'type': 'snapshot', 'lines': list(session.approved.values())})}\n\n"
                while True:
                    if request.cookies.get("otr_session", "") not in session.sessions:
                        return
                    while i < len(session.messages):
                        message = session.messages[i]
                        if message.get("type") == "transcript":
                            changes = [change for change in message["changes"] if change["kind"] != "committed"
                                       or change["line"]["id"] in session.approved]
                            message = {"type": "transcript", "changes": changes}
                        yield f"data: {json.dumps(message)}\n\n"
                        i += 1
                    if await request.is_disconnected():
                        return
                    await asyncio.sleep(0.2)
            return StreamingResponse(gen(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

        return app

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
            from otr.ingest.livekit_source import LiveKitSource
        except ImportError as e:
            print("LiveKit mode needs otr/ingest/livekit_source.py, which is not available "
                  f"({e}). Use --source replay, or type lines in the page.", file=sys.stderr)
            return 2
        source = LiveKitSource(room=os.environ.get("LIVEKIT_ROOM", "demo"),
                               model=os.environ.get("OTR_WHISPER_MODEL", "base.en"))
    else:
        source = None

    import uvicorn
    app = create_app(a.pipeline or "auto", a.script, a.speed, a.hold,
                     source=a.source, live_source=source)
    print(f"[demo] pipeline={app.state.session.kind}  open http://{a.host}:{a.port}/")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
