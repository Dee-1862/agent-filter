"""Edge layer for tunnelled traffic: edge key, egress ledger, loopback-only service endpoints.

A request is "tunnelled" when it looks like it came through a tunnel or proxy: it carries
forwarding headers (X-Forwarded-For, CF-Connecting-IP, Forwarded, ...), or its peer is not
loopback or a private LAN address, or it reached a loopback socket with a public Host header
(a tunnel connector on this PC that adds no forwarding headers). Only requests that are not
tunnelled count as direct.

Three jobs, all pure ASGI so streaming responses are not buffered:

1. Edge key. When OTR_EDGE_KEY is set, a tunnelled request must carry X-OTR-Edge-Key equal to
   it (constant-time compare) or it gets 401. GET /api/health and GET /static/* are exempt.
   Direct requests are unaffected.
2. Egress ledger. For tunnelled requests only: per route and method, request and response byte
   counts, and the set of field PATHS seen in JSON bodies and SSE data lines (never values).
   Every path must be on ALLOWED_FIELDS (deny by default). Audit mode (default) logs and counts
   anything else; OTR_EGRESS_ENFORCE=1 replaces the response with a 500.
3. Loopback-only service endpoints under /api/_internal/: activity (counts and ages only),
   egress totals (field paths, never values), and the supervisor's state push. A tunnelled
   request to these paths gets 404.
"""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

EDGE_KEY_HEADER = "x-otr-edge-key"

FORWARDING_HEADERS = frozenset({
    "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-forwarded-port",
    "x-forwarded-server", "forwarded", "x-real-ip", "cf-connecting-ip", "cf-ray",
    "cf-visitor", "cf-ipcountry", "true-client-ip", "cdn-loop", "x-vercel-forwarded-for",
    "x-vercel-id", "x-original-forwarded-for", "tailscale-user-login",
})

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


# ---------------------------------------------------------------- classification
def _headers(scope: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in scope.get("headers") or ():
        out.setdefault(k.decode("latin-1").lower(), v.decode("latin-1"))
    return out


def _peer_kind(scope: dict) -> str:
    """loopback | private | public (anything unparsable counts as public)."""
    client = scope.get("client")
    if not client:
        return "public"
    try:
        ip = ipaddress.ip_address(str(client[0]).split("%")[0])
    except ValueError:
        return "public"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return "loopback"
    if ip.is_private or ip.is_link_local:
        return "private"
    return "public"


def _host_is_loopback(host_header: str) -> bool:
    h = host_header.strip().lower()
    if h.startswith("["):
        h = h[1:].split("]", 1)[0]
    elif h.count(":") == 1:
        h = h.split(":", 1)[0]
    return h in LOOPBACK_HOSTS or h.endswith(".localhost")


def classify(scope: dict) -> str:
    """"direct" (loopback to loopback), "lan" (private peer, no forwarding) or "tunnelled"."""
    hdrs = _headers(scope)
    if any(name in FORWARDING_HEADERS for name in hdrs):
        return "tunnelled"
    peer = _peer_kind(scope)
    if peer == "loopback":
        return "direct" if _host_is_loopback(hdrs.get("host", "localhost")) else "tunnelled"
    if peer == "private":
        return "lan"
    return "tunnelled"


def is_tunnelled(scope: dict) -> bool:
    return classify(scope) == "tunnelled"


def is_direct_loopback(scope: dict) -> bool:
    return classify(scope) == "direct"


# ---------------------------------------------------------------- allowlist
# Field paths that may appear in a tunnelled JSON body or SSE message. Paths are dotted names;
# "[]" marks a list and "*" a dynamic key (an identity, a segment id or a category key, each
# validated by shape in DYNAMIC_KEYS). Anything else is a violation. Derived from the payloads
# of the consent-mode app (demo/live_session.py); see tests/test_egress.py for the scripted run.
_PARTICIPANT = ("name", "recording", "sensitive_paused")
_TRAIL = ("family", "before", "after", "held_s")
_LINE = ("id", "speaker", "name", "text", "seq")
_KEPT_CHIP = ("id", "category", "seq") + tuple("trail." + t for t in _TRAIL)
_KEPT_EVENT = ("id", "seq", "t", "category", "family", "before", "after", "held_s", "action", "code")
_INSIGHTS = ("approved", "total", "removed", "now", "hold_seconds", "kept_out.*",
             "timeline[].t", "timeline[].state")
_REDACTION = ("suppressed", "removed", "total")
_CATEGORY = ("key", "label", "short", "rule", "pattern", "families[]")
_FAMILY = ("engine", "label", "text")


def _under(prefix: str, names) -> set[str]:
    return {f"{prefix}.{n}" for n in names}


def _build_allowed() -> frozenset[str]:
    a: set[str] = set()
    # /api/me (and SSE snapshot/status share the pieces)
    a |= {"identity", "finalized", "delivery_email", "email_opted_in", "ready_for_final",
          "finalized_count", "contributor_count", "waiting"}
    a |= _under("participants.*", _PARTICIPANT)
    a |= _under("kept_out[]", _KEPT_CHIP)
    a |= _under("lines[]", _LINE)
    a |= set(_INSIGHTS) | _under("insights", _INSIGHTS)
    a |= _under("redaction_counts", _REDACTION)
    a |= _under("kept_out_events[]", _KEPT_EVENT)
    a |= {"line_times.*"}
    # SSE messages
    a |= {"type", "mode", "pipeline", "status", "retry"}
    a |= _under("participants.*", _PARTICIPANT)          # {"type": "participants", ...}
    a |= _under("kept_out[]", _KEPT_CHIP)
    a |= _under("changes[]", ("kind", "id", "category", "seq", "owner"))
    a |= _under("changes[].line", _LINE)
    a |= _under("changes[].trail", _TRAIL)
    # kept_out is a dict in status messages and /api/me insights; a list of chips in /api/me
    # (the "kept_out.*" entry in _INSIGHTS covers the dict form).
    # /api/diagnostics
    a |= {"hold_seconds"}
    a |= _under("models.whisper", ("name", "loaded", "load_seconds", "rtf"))
    a |= _under("models.llm", ("name", "reachable", "warm"))
    a |= _under("models.presidio", ("model", "available"))
    a |= _under("me", ("subscribed", "notes_on", "audio_rms", "audio_level", "last_frame_age_s",
                       "stt_last_activity_age_s", "state", "error", "waiting_lines"))
    a |= _under("service", ("state", "model_loaded", "idle_seconds"))
    # /api/config, /api/categories, /api/join, meetings
    a |= {"mode", "url", "room", "name", "token", "role", "room_id", "join_url", "request_id",
          "ok", "transport_disconnected", "recording", "finalized", "ready", "enabled", "email",
          "pending[].request_id", "pending[].name", "pending[].email",
          "recipients[].name", "recipients[].email", "version"}
    a |= _under("categories[]", _CATEGORY) | _under("families.*", _FAMILY)
    a |= _under("lines[]", ("id", "name", "text"))
    a |= {"detail"}                                       # FastAPI error text (fixed strings)
    a |= _under("redaction_counts", _REDACTION)
    return frozenset(a)


ALLOWED_FIELDS = _build_allowed()

# Parent names whose children are dynamic keys, and the shape each key must have.
DYNAMIC_KEYS: dict[str, re.Pattern] = {
    "participants": re.compile(r"person-[0-9a-f]{32}\Z"),
    "line_times": re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z"),
    "kept_out": re.compile(r"[a-z][a-z0-9_]{0,40}\Z"),
    "families": re.compile(r"[a-z][a-z0-9_]{0,40}\Z"),
}


def walk_fields(value: Any, prefix: str = "") -> tuple[set[str], set[str]]:
    """(paths seen, violations). Paths contain field names only, never values."""
    seen: set[str] = set()
    bad: set[str] = set()

    def visit(v: Any, path: str, parent: str) -> None:
        if isinstance(v, dict):
            for key, child in v.items():
                key = str(key)
                rule = DYNAMIC_KEYS.get(parent)
                if rule is not None and path.endswith(parent):
                    if rule.match(key):
                        step = "*"
                    else:
                        bad.add(f"{path}.<invalid key>")
                        continue
                else:
                    step = key
                child_path = f"{path}.{step}" if path else step
                if isinstance(child, (dict, list)):
                    visit(child, child_path, key)
                else:
                    seen.add(child_path)
        elif isinstance(v, list):
            item_path = path + "[]"
            for item in v:
                if isinstance(item, (dict, list)):
                    visit(item, item_path, parent)
                else:
                    seen.add(item_path)
    visit(value, prefix, "")
    for p in seen:
        if p not in ALLOWED_FIELDS:
            bad.add(p)
    return seen, bad


# ---------------------------------------------------------------- ledger
@dataclass
class RouteStats:
    requests: int = 0
    response_bytes: int = 0
    fields: set = field(default_factory=set)
    violations: set = field(default_factory=set)


_ID_SEGMENT = re.compile(r"^/(m|api/meetings)/[^/]+")


def route_key(method: str, path: str) -> str:
    path = _ID_SEGMENT.sub(lambda m: "/" + m.group(1) + "/{id}", path)
    return f"{method} {path}"


class Ledger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.routes: dict[str, RouteStats] = {}
        self.violation_counts: dict[str, int] = {}
        self.blocked = 0

    def record(self, key: str, nbytes: int, fields: set, violations: set) -> None:
        with self._lock:
            st = self.routes.setdefault(key, RouteStats())
            st.requests += 1
            st.response_bytes += nbytes
            st.fields |= fields
            st.violations |= violations
            for v in violations:
                self.violation_counts[v] = self.violation_counts.get(v, 0) + 1

    def add_fields(self, key: str, fields: set, violations: set) -> None:
        with self._lock:
            st = self.routes.setdefault(key, RouteStats())
            st.fields |= fields
            st.violations |= violations
            for v in violations:
                self.violation_counts[v] = self.violation_counts.get(v, 0) + 1

    def count_bytes(self, key: str, nbytes: int) -> None:
        with self._lock:
            self.routes.setdefault(key, RouteStats()).response_bytes += nbytes

    def snapshot(self, enforce: bool) -> dict:
        with self._lock:
            routes = [{"route": k, "requests": s.requests, "response_bytes": s.response_bytes,
                       "fields": sorted(s.fields), "violations": sorted(s.violations)}
                      for k, s in sorted(self.routes.items())]
            return {"enforce": enforce,
                    "totals": {"requests": sum(s.requests for s in self.routes.values()),
                               "response_bytes": sum(s.response_bytes for s in self.routes.values()),
                               "violations": sum(self.violation_counts.values()),
                               "blocked": self.blocked},
                    "violations": dict(sorted(self.violation_counts.items())),
                    "routes": routes}


def enforcing() -> bool:
    return os.environ.get("OTR_EGRESS_ENFORCE", "") == "1"


# ---------------------------------------------------------------- activity (counts and ages only)
class Activity:
    """Last-request clock and open-stream count. Health checks, internal and static paths do not count."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.last_request = clock()
        self.open_streams = 0

    def touch(self, method: str, path: str) -> None:
        if path.startswith("/api/_internal/") or path == "/api/health" or path.startswith("/static/"):
            return
        if path.startswith("/api/") or path == "/stream" or path.startswith("/m/"):
            self.last_request = self.clock()

    def idle_seconds(self) -> float:
        return 0.0 if self.open_streams > 0 else max(0.0, self.clock() - self.last_request)


@dataclass
class EdgeContext:
    """What the middleware needs from the app. All of it is counts, never meeting content."""
    meetings: dict
    ledger: Ledger = field(default_factory=Ledger)
    activity: Activity = field(default_factory=Activity)
    gate: Any = None                                   # otr.service.ServiceGate or None
    live_source: Any = None
    on_service_update: Optional[Callable[[dict], None]] = None

    def counts(self) -> dict:
        active = [m for m in list(self.meetings.values()) if m.get("session") is not None
                  and not getattr(m["session"], "closed", False)]
        people = sum(len(m["session"].names) for m in active)
        return {"active_meetings": len(active), "participants": people,
                "open_streams": self.activity.open_streams,
                "seconds_since_last_request": round(self.activity.idle_seconds(), 1),
                "whisper_loaded": getattr(self.live_source, "_transcribe", None) is not None,
                "service_state": getattr(self.gate, "state", None)}

    def service_public(self) -> Optional[dict]:
        if self.gate is None:
            return None
        return {"state": self.gate.state, "model_loaded": bool(self.gate.model_loaded),
                "idle_seconds": int(self.activity.idle_seconds())}


# ---------------------------------------------------------------- middleware
def _json_bytes(status: int, payload: dict) -> list[dict]:
    body = json.dumps(payload).encode()
    return [{"type": "http.response.start", "status": status,
             "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                         (b"content-length", str(len(body)).encode())]},
            {"type": "http.response.body", "body": body}]


def edge_key_ok(scope_headers: dict[str, str], method: str, path: str) -> bool:
    key = os.environ.get("OTR_EDGE_KEY", "")
    if not key:
        return True
    if method == "GET" and (path == "/api/health" or path.startswith("/static/")):
        return True
    given = scope_headers.get(EDGE_KEY_HEADER, "")
    return hmac.compare_digest(given.encode("utf-8"), key.encode("utf-8"))


class EdgeMiddleware:
    def __init__(self, app, ctx: EdgeContext) -> None:
        self.app = app
        self.ctx = ctx

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        ctx = self.ctx
        method, path = scope["method"], scope["path"]
        kind = classify(scope)
        hdrs = _headers(scope)

        if path.startswith("/api/_internal/"):
            if kind != "direct":
                for m in _json_bytes(404, {"detail": "Not Found"}):
                    await send(m)
                return
            await self._internal(scope, receive, send, method, path)
            return

        ctx.activity.touch(method, path)
        if kind != "tunnelled":
            if path == "/stream":
                await self._count_stream(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        if not edge_key_ok(hdrs, method, path):
            for m in _json_bytes(401, {"detail": "Edge key required"}):
                await send(m)
            return
        await self._ledgered(scope, receive, send, method, path)

    # -- /stream is long lived; count it so an open page keeps the service awake
    async def _count_stream(self, scope, receive, send):
        self.ctx.activity.open_streams += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.ctx.activity.open_streams = max(0, self.ctx.activity.open_streams - 1)

    async def _ledgered(self, scope, receive, send, method, path):
        ctx = self.ctx
        key = route_key(method, path)
        enforce = enforcing()
        state: dict[str, Any] = {"start": None, "ctype": "", "chunks": [], "bytes": 0, "stopped": False,
                                 "sse_tail": b""}
        is_stream = path == "/stream"
        if is_stream:
            ctx.activity.open_streams += 1

        async def wrapped(message):
            if state["stopped"]:
                return
            t = message["type"]
            if t == "http.response.start":
                state["start"] = message
                for k, v in message.get("headers", []):
                    if k.lower() == b"content-type":
                        state["ctype"] = v.decode("latin-1").lower()
                if "application/json" in state["ctype"]:
                    return                                 # hold until the body is complete
                await send(message)
                return
            if t != "http.response.body":
                await send(message)
                return
            body = message.get("body", b"")
            state["bytes"] += len(body)
            ctype = state["ctype"]
            if "application/json" in ctype:
                state["chunks"].append(body)
                if message.get("more_body"):
                    return
                raw = b"".join(state["chunks"])
                seen, bad = self._inspect_json(raw)
                ctx.ledger.record(key, state["bytes"], seen, bad)
                if bad:
                    self._log(key, bad)
                    if enforce:
                        ctx.ledger.blocked += 1
                        for m in _json_bytes(500, {"detail": "Blocked by egress policy"}):
                            await send(m)
                        return
                await send(state["start"])
                await send({"type": "http.response.body", "body": raw})
                return
            if "text/event-stream" in ctype:
                data = state["sse_tail"] + body
                *lines, state["sse_tail"] = data.split(b"\n")
                seen, bad = set(), set()
                for line in lines:
                    if line.startswith(b"data: "):
                        s, b = self._inspect_json(line[6:])
                        seen |= s
                        bad |= b
                ctx.ledger.count_bytes(key, len(body))
                if seen or bad:
                    ctx.ledger.add_fields(key, seen, bad)
                if bad:
                    self._log(key, bad)
                    if enforce:
                        ctx.ledger.blocked += 1
                        state["stopped"] = True          # drop this chunk and end the stream
                        await send({"type": "http.response.body", "body": b"", "more_body": False})
                        return
            if not message.get("more_body"):
                if "application/json" not in ctype:
                    ctx.ledger.record(key, state["bytes"], set(), set())
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        finally:
            if is_stream:
                ctx.activity.open_streams = max(0, ctx.activity.open_streams - 1)
                ctx.ledger.record(key, 0, set(), set())

    @staticmethod
    def _inspect_json(raw: bytes) -> tuple[set, set]:
        try:
            return walk_fields(json.loads(raw.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            return set(), {"<unparsable json>"}

    @staticmethod
    def _log(key: str, bad: set) -> None:
        # Field paths only. Never values.
        print(f"[egress] {key}: field(s) not on the allowlist: {', '.join(sorted(bad))}", file=sys.stderr)

    # -- loopback-only
    async def _internal(self, scope, receive, send, method, path):
        ctx = self.ctx
        if method == "GET" and path == "/api/_internal/activity":
            payload = ctx.counts()
        elif method == "GET" and path == "/api/_internal/egress":
            payload = ctx.ledger.snapshot(enforcing())
        elif method == "POST" and path == "/api/_internal/service":
            body = b""
            while True:
                msg = await receive()
                body += msg.get("body", b"")
                if not msg.get("more_body"):
                    break
            try:
                update = json.loads(body.decode("utf-8") or "{}")
                if not isinstance(update, dict):
                    raise ValueError
            except ValueError:
                for m in _json_bytes(400, {"detail": "bad json"}):
                    await send(m)
                return
            payload = await self._apply_service(update)
        else:
            for m in _json_bytes(404, {"detail": "Not Found"}):
                await send(m)
            return
        for m in _json_bytes(200, payload):
            await send(m)

    async def _apply_service(self, update: dict) -> dict:
        ctx = self.ctx
        gate = ctx.gate
        if gate is not None:
            if update.get("state") in ("SLEEPING", "WARMING", "READY", "IDLE"):
                gate.state = update["state"]
            if isinstance(update.get("model_loaded"), bool):
                gate.model_loaded = update["model_loaded"]
        if ctx.on_service_update is not None:
            ctx.on_service_update(update)
        if update.get("warm_whisper") is True and ctx.live_source is not None \
                and hasattr(ctx.live_source, "preload"):
            asyncio.get_running_loop().create_task(self._preload())
        if update.get("capture") is False:
            self._stop_capture()
        return {"ok": True, "service": ctx.service_public()}

    async def _preload(self) -> None:
        try:
            await self.ctx.live_source.preload()
        except Exception as exc:  # noqa: BLE001
            print(f"[service] speech model failed to load: {type(exc).__name__}", file=sys.stderr)

    def _stop_capture(self) -> None:
        """Idle: turn notes off for everyone still listed in a lingering meeting."""
        for room in list(self.ctx.meetings.values()):
            live = room.get("session")
            if live is None:
                continue
            for identity in list(live.names):
                try:
                    live.set_consent(identity, False)
                except Exception:  # noqa: BLE001
                    pass


def install_edge(app, ctx: EdgeContext) -> EdgeContext:
    app.add_middleware(EdgeMiddleware, ctx=ctx)
    app.state.edge = ctx
    return ctx
