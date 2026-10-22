"""Long-lived local service: the notes server plus a tunnel, with the local model on only while a meeting is active.

  python -m otr.service --tunnel cloudflared --serve-page
  python -m otr.service --tunnel none --idle-minutes 10

The supervisor runs the preflight from otr.app, starts the consent-mode server (otr.app as a
subprocess, so it can be restarted), starts and supervises the tunnel (otr.tunnel), and watches
meeting activity through the loopback-only GET /api/_internal/activity. It drives

    SLEEPING -> WARMING -> READY -> IDLE -> SLEEPING

SLEEPING  server up, tunnel up, model unloaded, speech model idle. Requests are accepted and
          meetings can be created; the filter runs on rules only (GatedLLM raises at once).
WARMING   a meeting was created or a join requested; Ollama and the speech model are loading.
READY     model loaded and a meeting is in use.
IDLE      no active meeting (or no request for `busy_window` seconds). Model still loaded.
SLEEPING  again after `--idle-minutes` of IDLE: the model is unloaded (keep_alive 0, confirmed
          with /api/ps) and notes are switched off for anyone left in a lingering meeting.

Ollama itself is never tunnelled and is checked to be listening on loopback only.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
OLLAMA_PORT = 11434
STATES = ("SLEEPING", "WARMING", "READY", "IDLE")
LOOPBACK = "127.0.0.1"


# ---------------------------------------------------------------- server side: gate and gated model
class ServiceGate:
    """The server process's copy of the service state, pushed by the supervisor."""

    def __init__(self) -> None:
        self.state = "SLEEPING"
        self.model_loaded = False

    def llm_allowed(self) -> bool:
        return self.model_loaded and self.state in ("READY", "IDLE")


GATE = ServiceGate()


class GatedLLM:
    """Wraps the real LLM. While the model is not READY every call fails at once, which the
    pipeline already treats as "use rules only". A push is never blocked on a cold model."""

    def __init__(self, inner, gate: ServiceGate) -> None:
        self.inner, self.gate = inner, gate

    def complete(self, prompt: str, **kw) -> str:
        if not self.gate.llm_allowed():
            from otr.llm import LLMError
            raise LLMError("local model is not loaded (service sleeping or warming); rules only")
        return self.inner.complete(prompt, **kw)

    def warmup(self) -> float:
        return self.inner.warmup() if self.gate.llm_allowed() else float("inf")

    def __getattr__(self, name: str):
        return getattr(self.inner, name)


# ---------------------------------------------------------------- state machine (pure, fake-clock friendly)
@dataclass
class Machine:
    idle_s: float = 600.0          # IDLE this long before the model is unloaded
    busy_window_s: float = 60.0    # a meeting counts as in use if a request arrived this recently
    wake_window_s: float = 15.0    # SLEEPING wakes if a request arrived this recently with a meeting present
    unload_retry_s: float = 30.0
    warm_retry_s: float = 60.0
    clock: Callable[[], float] = time.monotonic
    state: str = "SLEEPING"
    entered: float = 0.0
    next_unload: float = 0.0
    next_warm: float = 0.0
    idle_seconds: float = 0.0
    history: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self.entered = self.clock()

    def _go(self, state: str, why: str) -> None:
        now = self.clock()
        self.history.append((round(now, 1), self.state, state, why))
        self.state, self.entered = state, now

    def step(self, act: Optional[dict], model_loaded: bool = False) -> list[str]:
        """One observation. `act` is the activity dict (None = server unreachable). Returns actions."""
        if act is None:
            return []
        now = self.clock()
        meetings = int(act.get("active_meetings", 0))
        since = float(act.get("seconds_since_last_request", 0.0))
        streams = int(act.get("open_streams", 0))
        self.idle_seconds = 0.0 if streams else since
        busy = meetings > 0 and (streams > 0 or since <= self.busy_window_s)
        wake = meetings > 0 and (streams > 0 or since <= self.wake_window_s)
        if self.state == "SLEEPING":
            if wake:
                self._go("WARMING", "meeting activity")
                return ["warm"]
        elif self.state == "READY":
            if not busy:
                self._go("IDLE", "no active meeting")
            elif not model_loaded and now >= self.next_warm:
                self._go("WARMING", "model was evicted")
                return ["warm"]
        elif self.state == "IDLE":
            if busy:
                self._go("READY", "meeting active again")
            elif self.idle_seconds >= self.idle_s and now >= self.next_unload:
                self.next_unload = now + self.unload_retry_s
                return ["unload"]
        return []

    def warm_done(self, ok: bool) -> None:
        if self.state != "WARMING":
            return
        if not ok:
            self.next_warm = self.clock() + self.warm_retry_s
        self._go("READY", "model loaded" if ok else "warm-up failed, rules only")

    def unloaded(self, ok: bool) -> list[str]:
        if ok and self.state == "IDLE":
            self._go("SLEEPING", "idle timeout, model unloaded")
            return ["stop_capture"]
        return []


# ---------------------------------------------------------------- plain HTTP helpers
def http_json(method: str, url: str, payload: Optional[dict] = None, timeout: float = 3.0) -> Optional[dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001 - unreachable means None
        return None


class OllamaAdmin:
    """Load and unload one model through Ollama's HTTP API on loopback."""

    def __init__(self, host: str, model: str, keep_alive: str = "30m",
                 call: Callable[..., Optional[dict]] = http_json,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.host, self.model, self.keep_alive = host.rstrip("/"), model, keep_alive
        self.call, self.sleep = call, sleep

    def _same(self, name: str) -> bool:
        a, b = name, self.model
        strip = lambda s: s[:-7] if s.endswith(":latest") else s  # noqa: E731
        return strip(a) == strip(b)

    def loaded(self) -> bool:
        data = self.call("GET", self.host + "/api/ps")
        return any(self._same(str(m.get("name") or m.get("model") or "")) for m in (data or {}).get("models", []))

    def warm(self) -> bool:
        data = self.call("POST", self.host + "/api/generate",
                         {"model": self.model, "prompt": "", "keep_alive": self.keep_alive, "stream": False},
                         timeout=180.0)
        return data is not None and self.loaded()

    def unload(self, confirm_s: float = 6.0) -> bool:
        """keep_alive 0, then confirm with /api/ps that the model is gone."""
        self.call("POST", self.host + "/api/generate",
                  {"model": self.model, "prompt": "", "keep_alive": 0, "stream": False}, timeout=30.0)
        waited = 0.0
        while waited <= confirm_s:
            if not self.loaded():
                return True
            self.sleep(0.5)
            waited += 0.5
        return False


# ---------------------------------------------------------------- Ollama exposure check
def ollama_exposure_warnings(env: Optional[dict] = None,
                             port_open: Optional[Callable[[str, int], bool]] = None,
                             local_ips: Optional[list[str]] = None) -> list[str]:
    """Ollama must listen on loopback only. Warn when it does not."""
    env = os.environ if env is None else env
    from otr.llm import default_host
    out: list[str] = []
    host = default_host()
    name = host.split("://", 1)[-1].split("/")[0].rsplit(":", 1)[0].strip("[]").lower()
    if name not in ("localhost", "127.0.0.1", "::1"):
        out.append(f"the configured Ollama host is {host}, which is not loopback; use http://127.0.0.1:{OLLAMA_PORT}")
    bind = str(env.get("OLLAMA_HOST", "")).split("://", 1)[-1].rsplit(":", 1)[0].strip("[]")
    if bind in ("0.0.0.0", "::", "*"):
        out.append("OLLAMA_HOST binds Ollama to every interface; set OLLAMA_HOST=127.0.0.1 and restart Ollama")
    if port_open is None:
        def port_open(h: str, p: int) -> bool:   # noqa: E306
            try:
                with socket.create_connection((h, p), timeout=0.4):
                    return True
            except OSError:
                return False
    if local_ips is None:
        try:
            local_ips = sorted({i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                                if not i[4][0].startswith("127.")})
        except OSError:
            local_ips = []
    for ip in local_ips:
        if port_open(ip, OLLAMA_PORT):
            out.append(f"Ollama answers on {ip}:{OLLAMA_PORT}, so other devices on the network can reach it; "
                       "set OLLAMA_HOST=127.0.0.1 and restart Ollama")
    return out


# ---------------------------------------------------------------- server subprocess
class ServerProc:
    def __init__(self, argv: list[str], env: dict, *, popen=subprocess.Popen,
                 clock: Callable[[], float] = time.monotonic, log: Callable[[str], None] = print) -> None:
        from otr.tunnel import Backoff
        self.argv, self.env, self._popen, self.clock, self.log = argv, env, popen, clock, log
        self.proc = None
        self.backoff = Backoff()
        self.starts = 0

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        self.proc = self._popen(self.argv, env=self.env, cwd=str(ROOT), stdin=subprocess.DEVNULL)
        self.starts += 1
        self.backoff.ok(self.clock())

    def ensure(self) -> None:
        if self.alive() or self.clock() < self.backoff.next_try:
            return
        self.log("[service] the notes server is not running; starting it")
        self.backoff.failed(self.clock())   # next restart waits longer if it keeps dying
        try:
            self.start()
        except OSError as e:
            self.log(f"[service] could not start the server: {type(e).__name__}")

    def restart(self, env: Optional[dict] = None) -> None:
        if env is not None:
            self.env = env
        self.stop()
        self.start()

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                proc.kill()


# ---------------------------------------------------------------- supervisor
@dataclass
class Config:
    tunnel: str = "none"
    port: int = 8765
    idle_minutes: float = 10.0
    serve_page: bool = False
    source: str = "livekit"
    llm: str = "auto"
    model: Optional[str] = None
    hold: Optional[float] = None
    fast: bool = False
    no_docker: bool = False
    page_origin: str = ""
    edge_key: str = ""

    @property
    def base(self) -> str:
        return f"http://{LOOPBACK}:{self.port}"


def server_argv(cfg: Config) -> list[str]:
    argv = [sys.executable, "-m", "otr.app", "--source", cfg.source, "--service", "--port", str(cfg.port),
            "--host", LOOPBACK, "--llm", cfg.llm]
    if cfg.model:
        argv += ["--model", cfg.model]
    if cfg.hold is not None:
        argv += ["--hold", str(cfg.hold)]
    if cfg.fast:
        argv.append("--fast")
    if cfg.no_docker:
        argv.append("--no-docker")
    return argv


def server_env(cfg: Config, public_url: Optional[str], base_env: Optional[dict] = None) -> dict:
    env = dict(os.environ if base_env is None else base_env)
    if cfg.serve_page:
        origin = public_url or cfg.base
    else:
        origin = cfg.page_origin or public_url or cfg.base
    env["OTR_PUBLIC_ORIGIN"] = origin.rstrip("/")
    env["MEETING_PUBLIC_ORIGIN"] = origin.rstrip("/")     # join links must point at the page the guest opens
    env["OTR_SERVICE"] = "1"
    if cfg.edge_key:
        env["OTR_EDGE_KEY"] = cfg.edge_key
    return env


class Service:
    def __init__(self, cfg: Config, *, machine: Machine, server: ServerProc, ollama: Optional[OllamaAdmin],
                 tunnel=None, call: Callable[..., Optional[dict]] = http_json,
                 clock: Callable[[], float] = time.monotonic, log: Callable[[str], None] = print,
                 threaded: bool = True, status_every: float = 30.0) -> None:
        self.cfg, self.m, self.server, self.ollama, self.tunnel = cfg, machine, server, ollama, tunnel
        self.call, self.clock, self.log, self.threaded = call, clock, log, threaded
        self.status_every = status_every
        self.model_loaded = False
        self.activity: Optional[dict] = None
        self._warm_result: Optional[bool] = None
        self._warm_thread: Optional[threading.Thread] = None
        self._last_ps = -1e9
        self._last_push = -1e9
        self._last_status = -1e9
        self._last_line = ""
        self.public_url: Optional[str] = None

    # -- warm-up runs off the tick thread
    def _warm(self) -> None:
        ok = True
        self.call("POST", self.cfg.base + "/api/_internal/service", {"warm_whisper": True})
        if self.ollama is not None:
            ok = self.ollama.warm()
            self.model_loaded = bool(ok)
        # wait (bounded) for the speech model so the first sentence does not pay for it
        t0 = self.clock()
        while self.clock() - t0 < 90.0:
            data = self.call("GET", self.cfg.base + "/api/_internal/activity")
            if data is None or data.get("whisper_loaded"):
                break
            time.sleep(0.5)
        self._warm_result = ok

    def _start_warm(self) -> None:
        self._warm_result = None
        if self.threaded:
            self._warm_thread = threading.Thread(target=self._warm, daemon=True, name="service-warm")
            self._warm_thread.start()
        else:
            self._warm()

    def tick(self) -> None:
        now = self.clock()
        self.server.ensure()
        if self.tunnel is not None:
            self.tunnel.tick()
            self.public_url = self.tunnel.tunnel.public_url
        act = self.call("GET", self.cfg.base + "/api/_internal/activity")
        self.activity = act
        if self.ollama is not None and now - self._last_ps >= 5.0:
            self._last_ps = now
            loaded = self.ollama.loaded()
            if self.m.state != "WARMING":
                self.model_loaded = loaded
        if self._warm_result is not None:
            result, self._warm_result = self._warm_result, None
            self.m.warm_done(result)
        for action in self.m.step(act, self.model_loaded):
            if action == "warm":
                self._start_warm()
            elif action == "unload":
                ok = self.ollama.unload() if self.ollama is not None else True
                if ok:
                    self.model_loaded = False
                for follow in self.m.unloaded(ok):
                    if follow == "stop_capture":
                        self.call("POST", self.cfg.base + "/api/_internal/service", {"capture": False})
        if act is not None and now - self._last_push >= 5.0 or self._state_changed():
            self._last_push = now
            self._pushed = self.m.state
            self.call("POST", self.cfg.base + "/api/_internal/service",
                      {"state": self.m.state, "model_loaded": bool(self.model_loaded)})
        self._status(now)

    _pushed = ""

    def _state_changed(self) -> bool:
        return self._pushed != self.m.state

    def status_line(self) -> str:
        a = self.activity or {}
        server = "up" if self.activity is not None else "down"
        tun = self.public_url or ("none" if self.tunnel is None else "starting")
        return (f"[service] state={self.m.state} model={'loaded' if self.model_loaded else 'unloaded'} "
                f"idle={int(self.m.idle_seconds)}s meetings={a.get('active_meetings', 0)} "
                f"people={a.get('participants', 0)} server={server} tunnel={tun}")

    def _status(self, now: float) -> None:
        line = self.status_line()
        key = line.split(" idle=")[0] + line.split(" meetings=")[-1]
        if key != self._last_line or now - self._last_status >= self.status_every:
            self._last_line, self._last_status = key, now
            self.log(line)

    def shutdown(self) -> None:
        if self.tunnel is not None:
            self.tunnel.stop()
        self.server.stop()
        if self.ollama is not None:
            self.ollama.unload(confirm_s=2.0)


# ---------------------------------------------------------------- CLI
def parse_args(argv=None) -> tuple[Config, bool]:
    from otr.tunnel import KINDS, load_config, truthy
    file_cfg = load_config()
    ap = argparse.ArgumentParser(prog="python -m otr.service", description=__doc__.split("\n")[0])
    ap.add_argument("--tunnel", choices=KINDS, default=file_cfg.get("tunnel", "none"))
    ap.add_argument("--port", type=int, default=int(file_cfg.get("port", 8765)))
    ap.add_argument("--idle-minutes", type=float, default=float(file_cfg.get("idle_minutes", 10)))
    ap.add_argument("--serve-page", action="store_true", default=truthy(file_cfg.get("serve_page", False)),
                    help="serve the page and API from this PC through the tunnel on one origin (realtime SSE works)")
    ap.add_argument("--source", choices=("livekit",), default="livekit")
    ap.add_argument("--llm", default=file_cfg.get("llm", "auto"), help="auto | none | ollama | ollama:MODEL")
    ap.add_argument("--model", default=file_cfg.get("model"), help="Whisper model, e.g. tiny.en")
    ap.add_argument("--hold", type=float, default=None)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--no-docker", action="store_true")
    ap.add_argument("--check", action="store_true", help="run the preflight and the Ollama exposure check, then exit")
    a = ap.parse_args(argv)
    if a.port == OLLAMA_PORT:
        ap.error("port 11434 is Ollama's; choose another port")
    cfg = Config(tunnel=a.tunnel, port=a.port, idle_minutes=a.idle_minutes, serve_page=a.serve_page,
                 source=a.source, llm=a.llm, model=a.model, hold=a.hold, fast=a.fast, no_docker=a.no_docker,
                 page_origin=str(file_cfg.get("page_origin", "")),
                 edge_key=str(file_cfg.get("edge_key", "")))
    return cfg, a.check


def llm_model_for(cfg: Config) -> Optional[str]:
    if cfg.llm == "none":
        return None
    from otr.llm import default_model
    return cfg.llm.partition(":")[2] or default_model()


def main(argv=None) -> int:
    cfg, check_only = parse_args(argv)
    from otr import app as otr_app
    from otr import tunnel as tn

    if cfg.serve_page and cfg.edge_key:
        print("[service] --serve-page cannot be combined with OTR_EDGE_KEY: browsers reach the tunnel "
              "directly and would be refused. Unset the edge key, or use the Vercel proxy mode.", file=sys.stderr)
        return 2
    if not cfg.serve_page and cfg.tunnel != "none" and not cfg.page_origin:
        print("[service] note: no page origin is set (OTR_PAGE_ORIGIN). Without --serve-page the server only "
              "accepts browsers from the Vercel page origin you configure there.", file=sys.stderr)

    opts = otr_app.Options(source=cfg.source, llm="ollama" if cfg.llm == "auto" else cfg.llm,
                           port=cfg.port, host=LOOPBACK, model=cfg.model, no_docker=cfg.no_docker)
    checks = otr_app.preflight(opts)
    print("[service] preflight\n" + otr_app.format_table(checks), file=sys.stderr)
    warnings = ollama_exposure_warnings()
    for w in warnings:
        print(f"[service] WARNING: {w}", file=sys.stderr)
    blockers = [c for c in checks if c.blocking]
    if cfg.tunnel != "none":
        exe = tn.find_exe(cfg.tunnel)
        if exe is None:
            print(f"[service] {cfg.tunnel} was not found on PATH", file=sys.stderr)
            blockers.append(otr_app.Check("tunnel", "FAIL", "not installed"))
    if check_only:
        return 1 if blockers else 0
    if blockers:
        print("[service] cannot start: " + "; ".join(f"{c.name} ({c.detail})" for c in blockers), file=sys.stderr)
        return 2

    file_cfg = tn.load_config()
    model = llm_model_for(cfg)
    ollama = OllamaAdmin(__import__("otr.llm", fromlist=["default_host"]).default_host(), model) if model else None
    machine = Machine(idle_s=cfg.idle_minutes * 60.0)

    sup = None
    public = None
    if cfg.tunnel != "none":
        sup = tn.Supervised(tn.make_tunnel(cfg.tunnel, cfg.port, file_cfg), log=print)
        try:
            public = sup.start()
            print(f"[service] public URL: {public}", flush=True)
        except tn.TunnelError as e:
            print(f"[service] tunnel not up yet ({tn.redact(str(e))[:200]}); it will be retried", file=sys.stderr)

    server = ServerProc(server_argv(cfg), server_env(cfg, public))
    svc = Service(cfg, machine=machine, server=server, ollama=ollama, tunnel=sup)
    if sup is not None:
        def new_url(url):
            print(f"[service] public URL changed: {url}", flush=True)
            server.restart(server_env(cfg, url))
        sup.on_url_change = new_url
    server.start()
    print(f"[service] notes server on {cfg.base} (loopback only). Model unloaded until a meeting starts.", flush=True)
    try:
        while True:
            svc.tick()
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[service] stopping", flush=True)
    finally:
        svc.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
