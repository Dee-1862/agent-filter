"""Watch, from this laptop, whether a remote join reaches the notes engine and wakes the local model.

Run this on the host laptop while `python -m otr.service` is running, then open the public link
(the ngrok address or the Vercel page) on another device and create or join a meeting.

  python scripts/watch_remote.py               # service on port 8765
  python scripts/watch_remote.py --port 8799

Each line shows: meetings and people the server sees, requests that came through the tunnel,
whether the local model is loaded in Ollama, and the service state. It prints a clear message
when a remote request arrives and when the model loads or unloads. Nothing here reads meeting content.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request


def get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - shown as unreachable
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--every", type=float, default=2.0)
    a = ap.parse_args()
    base = f"http://127.0.0.1:{a.port}"
    print("Open the public link on another device and create or join a meeting. Ctrl+C to stop.\n")
    last_requests, last_loaded = None, None
    while True:
        act = get(base + "/api/_internal/activity")
        eg = get(base + "/api/_internal/egress")
        ps = get(a.ollama + "/api/ps")
        if act is None:
            print("notes server not reachable on", base, "(is python -m otr.service running?)")
            time.sleep(a.every)
            continue
        tunnelled = (eg or {}).get("totals", {}).get("requests", 0)
        loaded = [m["name"] for m in (ps or {}).get("models", [])]
        line = (f"{time.strftime('%H:%M:%S')}  meetings {act['active_meetings']}  people {act['participants']}  "
                f"requests through tunnel {tunnelled}  model {'loaded: ' + ', '.join(loaded) if loaded else 'not loaded'}  "
                f"service {act.get('service_state') or 'n/a'}")
        print(line, flush=True)
        if last_requests is not None and tunnelled > last_requests:
            print("  -> a request arrived through the tunnel: the remote page reached this laptop", flush=True)
        if last_loaded is not None and bool(loaded) != last_loaded:
            print("  -> the local model is now " + ("LOADED (woken by the meeting)" if loaded else "UNLOADED (idle)"), flush=True)
        last_requests, last_loaded = tunnelled, bool(loaded)
        time.sleep(a.every)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
