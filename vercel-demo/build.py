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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from demo.categories import js_source


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
        ("Calls and notes are processed on the local meeting host.",
         "Transcription and filtering run on the meeting host. This demo routes the call and approved live transcript through cloud services."),
        ("Notes are transcribed on the local meeting host. No cloud service is used.",
         "Transcription runs on the meeting host. This demo routes audio, video and approved live transcript text through cloud services."),
        ("the local meeting host transcribes your speech", "the meeting host transcribes your speech"),
        ("the local filter checks it", "the meeting host's filter checks it"),
        ("Speech recognition, filtering and the LiveKit room run on the local host serving this page. No cloud service is involved.",
         "Speech recognition and filtering run on the meeting host. In this public demo, audio and video pass through LiveKit Cloud, and approved live transcript text passes through Vercel and Cloudflare while your notes are on. Withheld text is never sent to the notes panel."),
    ):
        html = replace_required(html, old, new)
    (OUTPUT / "index.html").write_text(html)

    js = (SOURCE / "live.js").read_text()
    for old, new in (
        ("Live · local room", "Live · demo room"),
    ):
        js = replace_required(js, old, new)
    # Vercel's external rewrite buffers SSE responses in this demo. Poll the
    # viewer-scoped approved transcript; the backend sends no live text to
    # viewers whose notes are off. Keep local source SSE.
    start = js.index("  function connectStream() {")
    end = js.index("  function renderMicButton()", start)
    js = js[:start] + js[end:]
    js = replace_required(js, "  let room = null, me = null, eventSource = null;",
                          "  let room = null, me = null, eventSource = null, cloudPollTimer = null;")
    js = replace_required(js, "      connectStream();",
                          "      cloudPollTimer = setInterval(() => refreshMe(true), 3000);")
    js = replace_required(js, "      clearInterval(roomTimer);\n      stopDiagnostics();",
                          "      clearInterval(roomTimer);\n      clearInterval(cloudPollTimer);\n      stopDiagnostics();")
    (assets / "live.js").write_text(js)
    for filename in ("live.css", "views.css", "views.js", "livekit-client.umd.js", "livekit-client.LICENSE", "livekit-client.NOTICE"):
        shutil.copy2(SOURCE / filename, assets / filename)
    (assets / "categories.js").write_text(js_source())

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
