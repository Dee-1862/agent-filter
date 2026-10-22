"""Package the existing meeting UI for a static Vercel demo.

Usage: python vercel-demo/build.py https://public-backend.example
The backend URL is public configuration, never a secret.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "demo" / "static"
OUTPUT = ROOT / "public"


def backend_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Backend must be a public HTTPS origin")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Backend URL must be an origin without a path, query, or fragment")
    return value.rstrip("/")


def replace_required(source: str, old: str, new: str) -> str:
    if old not in source:
        raise ValueError(f"Expected UI text missing: {old[:80]}")
    return source.replace(old, new)


def build(origin: str) -> None:
    origin = backend_origin(origin)
    assets = OUTPUT / "static"
    assets.mkdir(parents=True, exist_ok=True)

    html = (SOURCE / "live.html").read_text()
    for old, new in (
        ("Private meetings on your own network", "Consent-first meetings"),
        ("Calls and note processing stay on the local meeting host. Share the link only with people who can reach it.",
         "This demo uses a cloud relay for the call and meeting controls. Transcription and filtering run on the meeting host."),
        ("Notes are transcribed on the local meeting host — no cloud service.",
         "Transcription runs on the meeting host. This demo relays meeting traffic through cloud services."),
        ("The local filter keeps sensitive lines out", "The meeting host's filter keeps sensitive lines out"),
        ("the local meeting host transcribes your speech", "the meeting host transcribes your speech"),
        ("the local filter checks it", "the meeting host's filter checks it"),
        ("Speech recognition, filtering, and the LiveKit room run on the local host serving this page. No cloud service is involved.",
         "Speech recognition and filtering run on the meeting host. This demo relays meeting traffic through cloud services."),
    ):
        html = replace_required(html, old, new)
    (OUTPUT / "index.html").write_text(html)

    js = (SOURCE / "live.js").read_text()
    for old, new in (
        ("Your audio is being transcribed locally for notes.", "The meeting host is transcribing your audio for notes."),
        ("The local filter paused your notes", "The meeting host's filter paused your notes"),
        ("Live · local room", "Live · demo room"),
    ):
        js = replace_required(js, old, new)
    # Vercel's external rewrite buffers SSE responses in this demo. Fetch the
    # viewer-scoped status summary instead; keep local source SSE.
    start = js.index("  function connectStream() {")
    end = js.index("  function renderMicButton()", start)
    js = js[:start] + js[end:]
    js = replace_required(js, 'api("/api/me")', 'api("/api/me?summary=1")')
    js = replace_required(js, "  let room = null, me = null, eventSource = null;",
                          "  let room = null, me = null, eventSource = null, cloudPollTimer = null;")
    js = replace_required(js, "      connectStream();",
                          "      cloudPollTimer = setInterval(() => refreshMe(true), 5000);")
    js = replace_required(js, "      clearInterval(roomTimer);\n      if (eventSource) eventSource.close();",
                          "      clearInterval(roomTimer);\n      clearInterval(cloudPollTimer);\n      if (eventSource) eventSource.close();")
    (assets / "live.js").write_text(js)
    for filename in ("live.css", "livekit-client.umd.js", "livekit-client.LICENSE", "livekit-client.NOTICE"):
        shutil.copy2(SOURCE / filename, assets / filename)

    # Browser API calls remain same-origin. This retains first-party session
    # cookies and needs no CORS exception in the browser.
    config = {
        "version": 2,
        "framework": None,
        "outputDirectory": "public",
        "rewrites": [
            {"source": "/api/:path*", "destination": origin + "/api/:path*"},
            {"source": "/m/:room", "destination": "/index.html"},
        ],
        "headers": [
            {"source": "/api/:path*", "headers": [{"key": "Cache-Control", "value": "no-store"}]},
            {"source": "/:path*", "headers": [{"key": "Referrer-Policy", "value": "same-origin"}]},
        ],
    }
    (ROOT / "vercel.json").write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python vercel-demo/build.py https://public-backend.example")
    build(sys.argv[1])
