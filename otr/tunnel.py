"""Tunnel launchers with one interface: start, public_url, healthy, stop.

  cloudflared  named tunnel (stable hostname) or quick tunnel (trycloudflare URL parsed from stderr)
  ngrok        `ngrok http <port> --domain <static-domain>`; URL read from the local ngrok API
  tailscale    `tailscale funnel <port>`; URL parsed from `tailscale funnel status`

Configuration comes from the environment or a gitignored .otr-service.json. Tokens are passed
to child processes through the environment, never on a command line, and every line a child
prints is passed through redact() before it is shown.

Nothing here talks to Ollama. Port 11434 is refused as a tunnel target.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ".otr-service.json"
OLLAMA_PORT = 11434
KINDS = ("cloudflared", "ngrok", "tailscale", "none")

_TRY_CF = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")
_TS_URL = re.compile(r"https://[a-z0-9][a-z0-9.-]*\.ts\.net")
_SECRETS = (
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}(?:\.[A-Za-z0-9_\-]+)*"),                       # JWT-like tokens
    re.compile(r"(?i)(--?(?:token|authtoken|auth-token|credentials?|secret)[ =])\S+"),   # flags
    re.compile(r"(?i)\b((?:tunnel_token|ngrok_authtoken|authtoken|token|secret|apikey|api_key)\s*[=:]\s*\"?)[^\s\",]+"),
)


class TunnelError(RuntimeError):
    pass


def redact(text: str) -> str:
    """Remove anything that looks like a token or secret from a log line."""
    out = _SECRETS[0].sub("[redacted]", text)
    for rx in _SECRETS[1:]:
        out = rx.sub(lambda m: m.group(1) + "[redacted]", out)
    return out


def find_exe(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    candidates = {
        "cloudflared": [r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
                        r"C:\Program Files\cloudflared\cloudflared.exe"],
        "tailscale": [r"C:\Program Files\Tailscale\tailscale.exe"],
        "ngrok": [],
    }.get(name, [])
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def default_fetch(url: str, timeout: float = 8.0) -> int:
    """HTTPS GET returning the status code (0 on any failure)."""
    req = urllib.request.Request(url, headers={"User-Agent": "otr-service-health"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(1024)
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001 - any failure means unhealthy
        return 0


def default_get_json(url: str, timeout: float = 3.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- configuration
def load_config(path: Optional[Path] = None, env: Optional[dict] = None) -> dict:
    """Merge .otr-service.json (if any) under environment overrides. Returns a flat dict.

    Keys: tunnel, port, idle_minutes, serve_page, page_origin, edge_key,
          cloudflared_name, cloudflared_hostname, cloudflared_token,
          ngrok_domain, llm, model.
    Environment names: OTR_TUNNEL, OTR_SERVICE_PORT, OTR_IDLE_MINUTES, OTR_SERVE_PAGE,
          OTR_PAGE_ORIGIN, OTR_EDGE_KEY, OTR_CLOUDFLARED_NAME, OTR_CLOUDFLARED_HOSTNAME,
          OTR_CLOUDFLARED_TOKEN, OTR_NGROK_DOMAIN.
    """
    env = os.environ if env is None else env
    cfg: dict = {}
    p = path if path is not None else ROOT / CONFIG_FILE
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({str(k): v for k, v in data.items()})
    except (OSError, ValueError):
        pass
    mapping = {"OTR_TUNNEL": "tunnel", "OTR_SERVICE_PORT": "port", "OTR_IDLE_MINUTES": "idle_minutes",
               "OTR_SERVE_PAGE": "serve_page", "OTR_PAGE_ORIGIN": "page_origin",
               "OTR_EDGE_KEY": "edge_key", "OTR_CLOUDFLARED_NAME": "cloudflared_name",
               "OTR_CLOUDFLARED_HOSTNAME": "cloudflared_hostname",
               "OTR_CLOUDFLARED_TOKEN": "cloudflared_token", "OTR_NGROK_DOMAIN": "ngrok_domain"}
    for name, key in mapping.items():
        if env.get(name):
            cfg[key] = env[name]
    return cfg


def truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------- base
class Tunnel:
    kind = "base"

    def __init__(self, port: int, *, popen=subprocess.Popen, fetch: Callable[..., int] = default_fetch,
                 get_json: Callable[..., Optional[dict]] = default_get_json,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, extra_env: Optional[dict] = None) -> None:
        if int(port) == OLLAMA_PORT:
            raise TunnelError("refusing to tunnel port 11434: that is Ollama, which must stay on loopback")
        self.port = int(port)
        self._popen, self._fetch, self._get_json = popen, fetch, get_json
        self._clock, self._sleep = clock, sleep
        self._extra_env = dict(extra_env or {})
        self._proc = None
        self._url: Optional[str] = None
        self.lines: deque[str] = deque(maxlen=200)   # redacted output of the child
        self._reader: Optional[threading.Thread] = None

    # -- subclass hooks
    def command(self) -> list[str]:
        raise NotImplementedError

    def discover(self) -> Optional[str]:
        raise NotImplementedError

    # -- interface
    @property
    def public_url(self) -> Optional[str]:
        return self._url

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, timeout: float = 45.0) -> str:
        self.stop()
        self._url = None
        env = dict(os.environ)
        env.update(self._extra_env)
        try:
            self._proc = self._popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, env=env, text=True, encoding="utf-8",
                                     errors="replace")
        except OSError as e:
            raise TunnelError(f"could not start {self.kind}: {type(e).__name__}") from e
        self._reader = threading.Thread(target=self._pump, args=(self._proc,), daemon=True,
                                        name=f"{self.kind}-log")
        self._reader.start()
        t0 = self._clock()
        while self._clock() - t0 < timeout:
            if not self.alive():
                raise TunnelError(f"{self.kind} exited early: {self.tail()}")
            url = self.discover()
            if url:
                self._url = url.rstrip("/")
                return self._url
            self._sleep(0.25)
        self.stop()
        raise TunnelError(f"{self.kind} did not report a public URL within {timeout:.0f}s: {self.tail()}")

    def _pump(self, proc) -> None:
        try:
            for line in proc.stdout:          # type: ignore[union-attr]
                self.lines.append(redact(line.rstrip()))
        except Exception:  # noqa: BLE001
            pass

    def tail(self, n: int = 3) -> str:
        return " | ".join(list(self.lines)[-n:]) or "no output"

    def healthy(self) -> bool:
        """HTTPS GET <public>/api/health through the tunnel must return 200."""
        if not self._url or not self.alive():
            return False
        return self._fetch(self._url + "/api/health") == 200

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except Exception:  # noqa: BLE001
                    proc.kill()
            except Exception:  # noqa: BLE001
                pass
        self._url = None


# ---------------------------------------------------------------- cloudflared
class Cloudflared(Tunnel):
    kind = "cloudflared"

    def __init__(self, port: int, *, name: str = "", hostname: str = "", token: str = "", **kw) -> None:
        env = dict(kw.pop("extra_env", None) or {})
        if token:
            env["TUNNEL_TOKEN"] = token              # environment only, never argv
        super().__init__(port, extra_env=env, **kw)
        self.name, self.hostname, self.has_token = name, hostname.strip().lower(), bool(token)
        self.exe = find_exe("cloudflared") or "cloudflared"

    @property
    def named(self) -> bool:
        return bool(self.name or self.has_token)

    def command(self) -> list[str]:
        local = f"http://127.0.0.1:{self.port}"
        if not self.named:
            return [self.exe, "tunnel", "--url", local, "--no-autoupdate"]
        cmd = [self.exe, "tunnel", "--no-autoupdate", "run", "--url", local]
        if self.name:
            cmd.append(self.name)
        return cmd

    def discover(self) -> Optional[str]:
        if self.named:
            if not self.hostname:
                raise TunnelError("a named cloudflared tunnel needs its public hostname "
                                  "(OTR_CLOUDFLARED_HOSTNAME or cloudflared_hostname)")
            # The hostname is stable. Wait until the connector says it is registered.
            if any("Registered tunnel connection" in ln for ln in self.lines):
                return "https://" + self.hostname
            return None
        for ln in list(self.lines):
            m = _TRY_CF.search(ln)
            if m:
                return m.group(0)
        return None


# ---------------------------------------------------------------- ngrok
class Ngrok(Tunnel):
    kind = "ngrok"
    API = "http://127.0.0.1:4040/api/tunnels"

    def __init__(self, port: int, *, domain: str = "", **kw) -> None:
        super().__init__(port, **kw)
        self.domain = domain.strip()
        self.exe = find_exe("ngrok") or "ngrok"

    def command(self) -> list[str]:
        cmd = [self.exe, "http", f"127.0.0.1:{self.port}", "--log", "stdout"]
        if self.domain:
            cmd += ["--domain", self.domain]
        return cmd

    def discover(self) -> Optional[str]:
        data = self._get_json(self.API)
        for t in (data or {}).get("tunnels", []):
            url = str(t.get("public_url", ""))
            if url.startswith("https://") and (not self.domain or self.domain in url):
                return url
        return None


# ---------------------------------------------------------------- tailscale
class Tailscale(Tunnel):
    kind = "tailscale"

    def __init__(self, port: int, *, run=subprocess.run, **kw) -> None:
        super().__init__(port, **kw)
        self._run = run
        self.exe = find_exe("tailscale") or "tailscale"
        self._started = False

    def _tailscale(self, *args: str, timeout: float = 20.0) -> str:
        try:
            r = self._run([self.exe, *args], capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as e:
            raise TunnelError(f"tailscale failed: {type(e).__name__}") from e
        return (r.stdout or "") + (r.stderr or "")

    def alive(self) -> bool:                  # funnel runs inside the Tailscale daemon
        return self._started

    def start(self, timeout: float = 45.0) -> str:
        self.stop()
        out = self._tailscale("funnel", "--bg", str(self.port))
        self._started = True
        for ln in out.splitlines():
            self.lines.append(redact(ln))
        t0 = self._clock()
        while self._clock() - t0 < timeout:
            url = self.discover()
            if url:
                self._url = url
                return url
            self._sleep(0.5)
        self._started = False
        raise TunnelError("tailscale funnel did not report a URL. Is Funnel enabled for this node? "
                          + self.tail())

    def command(self) -> list[str]:
        return [self.exe, "funnel", "--bg", str(self.port)]

    def discover(self) -> Optional[str]:
        m = _TS_URL.search(self._tailscale("funnel", "status"))
        return m.group(0) if m else None

    def stop(self) -> None:
        if self._started:
            try:
                self._tailscale("funnel", "reset")
            except TunnelError:
                pass
        self._started = False
        self._url = None


def make_tunnel(kind: str, port: int, cfg: Optional[dict] = None, **kw) -> Optional[Tunnel]:
    cfg = cfg or {}
    if kind in (None, "", "none"):
        return None
    if int(port) == OLLAMA_PORT:
        raise TunnelError("refusing to tunnel port 11434 (Ollama)")
    if kind == "cloudflared":
        return Cloudflared(port, name=str(cfg.get("cloudflared_name", "")),
                           hostname=str(cfg.get("cloudflared_hostname", "")),
                           token=str(cfg.get("cloudflared_token", "")), **kw)
    if kind == "ngrok":
        return Ngrok(port, domain=str(cfg.get("ngrok_domain", "")), **kw)
    if kind == "tailscale":
        return Tailscale(port, **kw)
    raise TunnelError(f"unknown tunnel {kind!r}; choose one of {', '.join(KINDS)}")


# ---------------------------------------------------------------- supervision with backoff
class Backoff:
    def __init__(self, first: float = 2.0, cap: float = 60.0, reset_after: float = 120.0) -> None:
        self.first, self.cap, self.reset_after = first, cap, reset_after
        self.delay = 0.0
        self.next_try = 0.0
        self.last_ok = 0.0

    def failed(self, now: float) -> float:
        if self.last_ok and now - self.last_ok >= self.reset_after:
            self.delay = 0.0
        self.delay = self.first if self.delay == 0 else min(self.cap, self.delay * 2)
        self.next_try = now + self.delay
        return self.delay

    def ok(self, now: float) -> None:
        self.last_ok = now


class Supervised:
    """Keeps a tunnel up: health check every `check_every` seconds, restart after `max_fail`
    failures in a row, and wait with exponential backoff between failed restarts."""

    def __init__(self, tunnel: Tunnel, *, clock: Callable[[], float] = time.monotonic,
                 check_every: float = 30.0, max_fail: int = 3, log: Callable[[str], None] = print,
                 on_url_change: Optional[Callable[[Optional[str]], None]] = None) -> None:
        self.tunnel, self.clock, self.check_every, self.max_fail = tunnel, clock, check_every, max_fail
        self.log, self.on_url_change = log, on_url_change
        self.backoff = Backoff()
        self.fail = 0
        self.last_check = 0.0
        self.restarts = 0
        self.healthy_now = False

    def start(self) -> str:
        url = self.tunnel.start()
        self.backoff.ok(self.clock())
        self.last_check = self.clock()
        return url

    def tick(self) -> None:
        now = self.clock()
        t = self.tunnel
        if not t.alive():
            self.healthy_now = False
            self._restart(now, "process exited")
            return
        if now - self.last_check < self.check_every:
            return
        self.last_check = now
        if t.healthy():
            self.fail = 0
            self.healthy_now = True
            self.backoff.ok(now)
            return
        self.healthy_now = False
        self.fail += 1
        if self.fail >= self.max_fail:
            self._restart(now, f"{self.fail} failed health checks")

    def _restart(self, now: float, why: str) -> None:
        if now < self.backoff.next_try:
            return
        old = self.tunnel.public_url
        self.log(f"[tunnel] restarting {self.tunnel.kind}: {why}")
        try:
            new = self.tunnel.start()
        except TunnelError as e:
            wait = self.backoff.failed(now)
            self.log(f"[tunnel] restart failed ({redact(str(e))[:160]}); retry in {wait:.0f}s")
            return
        self.restarts += 1
        self.fail = 0
        self.last_check = now
        self.backoff.ok(now)
        self.log(f"[tunnel] public URL: {new}")
        if new != old and self.on_url_change:
            self.on_url_change(new)

    def stop(self) -> None:
        self.tunnel.stop()
