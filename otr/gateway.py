"""On-demand meeting host: a small always-on doorbell in front of the full notes server.

The gateway owns the public tunnel and a light TCP listener. The heavy meeting host
(speech to text, PII models, LiveKit bot, local model on demand) is NOT running while idle.

  * A visitor opens the link (directly or through the Vercel page): the gateway sees the request,
    starts the meeting host, shows a short "starting" page or a 503 with Retry-After, then passes
    all traffic through unchanged (so live updates keep streaming).
  * When no meeting is active and no request has arrived for --idle-minutes, the host is stopped.
    The tunnel and the gateway stay up, ready for the next visitor.

  python -m otr.gateway                      # tunnel and settings from .otr-service.json
  python -m otr.gateway --tunnel none        # local only, for testing
  python -m otr.gateway --idle-minutes 15

The full host is started as `python -m otr.app --source livekit` on an internal loopback port.
Bytes are piped as-is, so the host still sees the public Host header and treats the request as
tunnelled (egress rules apply). The gateway never reads meeting content.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

STARTING_HTML = (
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<meta http-equiv=\"refresh\" content=\"4\"><title>Off The Record</title>"
    "<style>body{font-family:Roboto,Arial,sans-serif;display:grid;place-items:center;height:100vh;margin:0;"
    "color:#202124}p{color:#5f6368}</style></head><body><main><h1>Starting the meeting host</h1>"
    "<p>The notes engine on the host laptop is waking up. This page refreshes on its own.</p>"
    "</main></body></html>"
)


def http_response(status: str, body: bytes, ctype: str, extra: str = "") -> bytes:
    head = (f"HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
            f"Cache-Control: no-store\r\nConnection: close\r\n{extra}\r\n")
    return head.encode("ascii") + body


class Host:
    """The heavy meeting host process, started and stopped on demand."""

    def __init__(self, port: int, args: list[str], env: Optional[dict] = None):
        self.port, self.args, self.env = port, args, env
        self.proc: Optional[subprocess.Popen] = None
        self.started_at: Optional[float] = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self.running:
            return
        cmd = [sys.executable, "-m", "otr.app", "--source", "livekit", "--port", str(self.port), *self.args]
        log = open(ROOT / ".otr-host.log", "ab")
        self.proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
                                     env={**os.environ, **(self.env or {})})
        self.started_at = time.time()
        print(f"[gateway] visitor arrived: starting the meeting host on 127.0.0.1:{self.port}", flush=True)

    def ready(self) -> bool:
        if not self.running:
            return False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/health", timeout=0.4) as r:
                return r.status == 200
        except Exception:  # noqa: BLE001
            return False

    def activity(self) -> Optional[dict]:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/_internal/activity", timeout=2) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def stop(self) -> None:
        if not self.running:
            return
        print("[gateway] idle: stopping the meeting host (tunnel stays up)", flush=True)
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        else:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        self.proc = None


class Gateway:
    def __init__(self, listen_port: int, host: Host, idle_minutes: float):
        self.listen_port, self.host = listen_port, host
        self.idle_s = idle_minutes * 60
        self.last_request = 0.0
        self.open_conns = 0

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.last_request = time.time()
        try:
            first = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
        except Exception:  # noqa: BLE001
            writer.close()
            return
        line = first.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        path = line.split(" ")[1] if " " in line else "/"
        if not self.host.ready():
            self.host.start()
            for _ in range(4):                      # give a warm restart a moment before answering
                if self.host.ready():
                    break
                await asyncio.sleep(0.5)
        if not self.host.ready():
            if path.startswith("/api/") or path.startswith("/stream"):
                body = b'{"detail":"The meeting host is starting. Try again in a few seconds."}'
                writer.write(http_response("503 Service Unavailable", body, "application/json", "Retry-After: 5\r\n"))
            else:
                writer.write(http_response("200 OK", STARTING_HTML.encode("utf-8"), "text/html; charset=utf-8"))
            await writer.drain()
            writer.close()
            return
        try:
            up_r, up_w = await asyncio.open_connection("127.0.0.1", self.host.port)
        except OSError:
            writer.close()
            return
        self.open_conns += 1
        up_w.write(first)
        await up_w.drain()

        async def pipe(src, dst):
            try:
                while True:
                    chunk = await src.read(65536)
                    if not chunk:
                        break
                    dst.write(chunk)
                    await dst.drain()
                    self.last_request = time.time()
            except Exception:  # noqa: BLE001
                pass
            finally:
                try:
                    dst.close()
                except Exception:  # noqa: BLE001
                    pass

        await asyncio.gather(pipe(reader, up_w), pipe(up_r, writer))
        self.open_conns -= 1

    async def idle_watch(self) -> None:
        while True:
            await asyncio.sleep(15)
            if not self.host.running:
                continue
            act = self.host.activity() or {}
            busy = act.get("active_meetings", 0) > 0 or self.open_conns > 0
            quiet_for = time.time() - self.last_request
            if not busy and quiet_for > self.idle_s and time.time() - (self.host.started_at or 0) > self.idle_s:
                self.host.stop()

    async def run(self) -> None:
        server = await asyncio.start_server(self.handle, "127.0.0.1", self.listen_port)
        print(f"[gateway] listening on 127.0.0.1:{self.listen_port}; meeting host starts on the first visit", flush=True)
        asyncio.create_task(self.idle_watch())
        async with server:
            await server.serve_forever()


def main(argv=None) -> int:
    from otr.tunnel import load_config, make_tunnel
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tunnel", default=cfg.get("tunnel", "none"), help="ngrok | cloudflared | none")
    ap.add_argument("--port", type=int, default=int(cfg.get("port", 8765)), help="public port behind the tunnel")
    ap.add_argument("--host-port", type=int, default=8766, help="internal port for the meeting host")
    ap.add_argument("--idle-minutes", type=float, default=float(cfg.get("idle_minutes", 10)))
    ap.add_argument("--llm", default=cfg.get("llm", "auto"))
    ap.add_argument("--hold", type=float, default=None)
    a = ap.parse_args(argv)
    host_args = ["--llm", a.llm] + (["--hold", str(a.hold)] if a.hold else [])
    host = Host(a.host_port, host_args)
    gw = Gateway(a.port, host, a.idle_minutes)
    tunnel = make_tunnel(a.tunnel, a.port, cfg)
    if tunnel is not None:
        url = tunnel.start()
        host.env = {"OTR_PUBLIC_ORIGIN": url}     # let the public page create and join meetings
        print(f"[gateway] public link: {url}", flush=True)
    try:
        asyncio.run(gw.run())
    except KeyboardInterrupt:
        pass
    finally:
        gw.host.stop()
        if tunnel is not None:
            tunnel.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
