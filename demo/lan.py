"""Run the consent demo on one Wi-Fi network with local TLS and random LiveKit keys.

Requires the native ``livekit-server`` and ``caddy`` executables. Caddy's local
CA stays in the ignored .local-lan directory; share only its root.crt, never a
private key. This launcher makes no cloud API calls.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local-lan"


def lan_ip(value: str | None) -> str:
    if value is None and sys.platform == "darwin":
        for interface in ("en0", "en1"):
            result = subprocess.run(["ipconfig", "getifaddr", interface], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                value = result.stdout.strip()
                break
    if value is None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 1))  # Route lookup only; no packet is sent.
            value = sock.getsockname()[0]
    address = ipaddress.ip_address(value)
    if address.version != 4 or not address.is_private or address.is_loopback:
        raise ValueError("Choose a private, non-loopback IPv4 address on the host's Wi-Fi network")
    return str(address)


def private_file(path: Path, content: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)


def wait_for_port(port: int, process: subprocess.Popen, seconds: float = 20) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Process exited during startup; check {STATE / 'logs'}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for local TCP port {port}; check {STATE / 'logs'}")


def wait_for_http(url: str, process: subprocess.Popen, seconds: float = 20,
                  context: ssl.SSLContext | None = None) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Process exited during startup; check {STATE / 'logs'}")
        try:
            with urllib.request.urlopen(url, timeout=0.5, context=context) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}; check {STATE / 'logs'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start a local-only HTTPS/WSS meeting for the same Wi-Fi network")
    parser.add_argument("--lan-ip", help="Host Wi-Fi IPv4 address; defaults to en0/en1 on macOS")
    parser.add_argument("--python", default=str(ROOT / ".venv" / "bin" / "python"),
                        help="Python with demo dependencies installed")
    parser.add_argument("--pipeline", choices=("real", "fake"), default="real")
    args = parser.parse_args(argv)
    try:
        ip = lan_ip(args.lan_ip)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    caddy = shutil.which("caddy")
    livekit = shutil.which("livekit-server")
    python = shutil.which(args.python) or (args.python if Path(args.python).is_file() else None)
    missing = [name for name, value in (("caddy", caddy), ("livekit-server", livekit),
                                         ("Python with project dependencies", python)) if not value]
    if missing:
        parser.error("Missing " + ", ".join(missing) + "; see docs/SECURE_LAN.md")

    STATE.mkdir(mode=0o700, exist_ok=True)
    STATE.chmod(0o700)
    logs = STATE / "logs"
    logs.mkdir(mode=0o700, exist_ok=True)
    caddy_storage = STATE / "caddy-storage"
    caddy_storage.mkdir(mode=0o700, exist_ok=True)
    key = "LAN" + secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(48)
    livekit_config = STATE / "livekit.yaml"
    caddyfile = STATE / "Caddyfile"
    private_file(livekit_config, f"""port: 17880
bind_addresses:
  - 127.0.0.1
rtc:
  tcp_port: 17881
  udp_port: 17882
  node_ip: {ip}
  use_external_ip: false
  stun_servers:
    - {ip}:17882
keys:
  {key}: {secret}
logging:
  level: warn
""")
    private_file(caddyfile, f"""{{
  admin off
  auto_https disable_redirects
  local_certs
  skip_install_trust
  storage file_system {caddy_storage}
}}
https://{ip}:18443 {{
  reverse_proxy 127.0.0.1:18772
}}
https://{ip}:18444 {{
  reverse_proxy 127.0.0.1:17880
}}
""")
    env = os.environ.copy()
    env.update({
        "LIVEKIT_URL": "ws://127.0.0.1:17880",
        "LIVEKIT_PUBLIC_URL": f"wss://{ip}:18444",
        "LIVEKIT_API_KEY": key,
        "LIVEKIT_API_SECRET": secret,
        "MEETING_PUBLIC_ORIGIN": f"https://{ip}:18443",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    })
    commands = [
        ("livekit", [livekit, "--config", str(livekit_config)]),
        ("app", [python, "-m", "demo.server", "--source", "livekit", "--pipeline", args.pipeline,
                 "--host", "127.0.0.1", "--port", "18772"]),
        ("caddy", [caddy, "run", "--config", str(caddyfile), "--adapter", "caddyfile"]),
    ]
    processes: list[subprocess.Popen] = []
    streams = []
    try:
        for name, command in commands:
            stream = open(logs / f"{name}.log", "w", encoding="utf-8")
            os.chmod(logs / f"{name}.log", 0o600)
            streams.append(stream)
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            processes.append(process)
            if name == "livekit":
                wait_for_port(17880, process)
            elif name == "app":
                wait_for_http("http://127.0.0.1:18772/api/config", process)
        root_cert = caddy_storage / "pki" / "authorities" / "local" / "root.crt"
        deadline = time.monotonic() + 20
        while not root_cert.exists() and time.monotonic() < deadline:
            if processes[-1].poll() is not None:
                raise RuntimeError(f"Caddy exited during startup; check {logs / 'caddy.log'}")
            time.sleep(0.2)
        if not root_cert.exists():
            raise RuntimeError(f"Caddy certificate not ready; check {logs / 'caddy.log'}")
        wait_for_http(f"https://{ip}:18443/api/config", processes[-1],
                      context=ssl.create_default_context(cafile=root_cert))
        print(f"Meeting: https://{ip}:18443/", flush=True)
        print(f"Trust this PUBLIC root certificate on each device before opening the link: {root_cert}", flush=True)
        print("WebRTC media: UDP 17882 (TCP 17881 fallback); same Wi-Fi only.", flush=True)
        print("Press Ctrl-C to stop all three local services.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("A service exited unexpectedly; check .local-lan/logs")
    except KeyboardInterrupt:
        return 0
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
        for process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in streams:
            stream.close()
        livekit_config.unlink(missing_ok=True)  # Ephemeral API keys are never kept after shutdown.


if __name__ == "__main__":
    raise SystemExit(main())
