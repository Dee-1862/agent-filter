"""Drive the REAL browser path with a fake microphone: Edge + livekit-client + LiveKit + bot + Whisper.

Chromium flags make getUserMedia deliver a WAV file as the microphone, so the page runs exactly as
it does with a person: it creates a meeting, publishes the mic track, and the approved caption
shows up in the DOM. Needs `pip install playwright` and Microsoft Edge (channel='msedge', no
browser download). Loopback only; uses the repo's synthetic demo audio.

  python experiments/browser_fake_mic.py demo_audio/alice.wav --start 0 --end 8 --app http://127.0.0.1:8020
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
import wave
from pathlib import Path
from urllib.parse import urlparse


def cut_wav(src: Path, start: float, end: float | None, lead_s: float, tail_s: float, out: Path) -> float:
    with wave.open(str(src), "rb") as w:
        params, rate, width, ch = w.getparams(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        w.setpos(int(start * rate))
        body = w.readframes(int(((end or w.getnframes() / rate) - start) * rate))
    silence = lambda s: b"\0" * (int(s * rate) * width * ch)  # noqa: E731
    with wave.open(str(out), "wb") as o:
        o.setparams(params)
        o.writeframes(silence(lead_s) + body + silence(tail_s))
    return len(body) / (rate * width * ch)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav")
    ap.add_argument("--app", default="http://127.0.0.1:8020")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=8.0)
    ap.add_argument("--lead", type=float, default=8.0, help="silence before speech (time to switch notes on)")
    ap.add_argument("--wait", type=float, default=25.0, help="seconds to wait for a caption after the clip")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--channel", default="msedge")
    a = ap.parse_args()
    if urlparse(a.app).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("loopback only")
    from playwright.sync_api import sync_playwright

    tmp = Path(tempfile.mkdtemp(prefix="fakemic_"))
    clip = tmp / "clip.wav"
    speech_s = cut_wav(Path(a.wav), a.start, a.end, a.lead, 3.0, clip)
    flags = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
             f"--use-file-for-fake-audio-capture={clip}%noloop"]
    result: dict = {"clip_speech_seconds": round(speech_s, 2)}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=a.channel, headless=not a.headed, args=flags)
        ctx = browser.new_context(permissions=["microphone"])
        page = ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(m.text[:200]) if m.type in ("error", "warning") else None)
        page.goto(a.app)
        page.click("#create-button")
        page.fill("#host-name", "Browser Tester")
        page.fill("#host-email", "tester@example.com")
        page.click("#host-create-button")
        page.click("#share-join-button")
        page.wait_for_selector("#meeting:not(.hidden)", timeout=20000)
        t_joined = time.monotonic()
        if not page.locator("#notes-button").is_visible():
            page.click("#agent-button")          # open the Off The Record panel
        if page.get_attribute("#notes-button", "aria-checked") != "true":
            page.click("#notes-button")
        page.wait_for_selector('#notes-button[aria-checked="true"]', timeout=10000)
        t_notes = time.monotonic()
        result["notes_on_after_join_s"] = round(t_notes - t_joined, 2)
        diag, first = [], None
        t_end_est = t_joined + a.lead + speech_s   # fake device opens at getUserMedia, close to join
        deadline = t_end_est + a.wait
        while time.monotonic() < deadline:
            d = ctx.request.get(a.app + "/api/diagnostics").json()
            diag.append({"t": round(time.monotonic() - t_joined, 1), **d["me"]})
            n = len(ctx.request.get(a.app + "/api/me").json()["lines"])
            if n and first is None:
                first = time.monotonic()
                result["first_caption_text_present"] = True
                result["first_caption_s_after_est_speech_end"] = round(first - t_end_est, 1)
                time.sleep(0.6)   # let the page's SSE render it
                result["caption_in_page"] = page.inner_text("#captions")[:120]
            if first and time.monotonic() - first > 6:
                break
            time.sleep(0.25)
        result["me_states_seen"] = sorted({d["state"] for d in diag})
        result["max_audio_level"] = max((d["audio_level"] for d in diag), default=0)
        result["last_diagnostics"] = diag[-1] if diag else None
        result["lines_in_api_me"] = len(ctx.request.get(a.app + "/api/me").json()["lines"])
        result["console_problems"] = logs[:5]
        page.screenshot(path=str(tmp / "final.png"))
        result["screenshot"] = str(tmp / "final.png")
        browser.close()
    print(json.dumps(result, indent=2))
    return 0 if result.get("first_caption_text_present") else 1


if __name__ == "__main__":
    raise SystemExit(main())
