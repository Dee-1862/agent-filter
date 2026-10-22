"""Record a three person meeting end to end and save screenshots, videos and proof files.

Alice hosts, Bob and Carol join and are admitted. Each browser's microphone plays that person's
voice track (text to speech, demo_audio/*.wav; Dan's lines are mixed into Bob's track so the salary
line is spoken). Everyone turns notes on. The real chain runs: browser microphone, LiveKit, the
notes engine on this laptop (Whisper, Presidio, cue detector, hold buffer, local model), and the page.

Saves to docs/images/showcase/ (screenshots, small PNGs) and docs/showcase/ (videos and proof JSON):
  * each person's call view, kept-out markers in the live captions, Insights, How it decides, and an opened marker
  * proof_<name>.json: that person's approved lines and kept-out kinds, as the server returned them

  python experiments/showcase.py --app http://127.0.0.1:8799

The server must already run, for example:
  python -m otr.app --source livekit --port 8799 --hold 5 --llm ollama
Needs Playwright for Python and Microsoft Edge. Loopback only.
"""
from __future__ import annotations

import argparse
import array
import json
import sys
import tempfile
import time
import wave
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "demo_audio"
SHOTS = ROOT / "docs" / "images" / "showcase"
OUT = ROOT / "docs" / "showcase"
PEOPLE = [("Alice", "alice@example.com", ["alice"]),
          ("Bob", "bob@example.com", ["bob", "dan"]),
          ("Carol", "carol@example.com", ["carol"])]


def read_track(name: str) -> tuple[array.array, int, int, int]:
    with wave.open(str(AUDIO / f"{name}.wav"), "rb") as w:
        rate, width, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
        if width != 2:
            raise SystemExit(f"{name}.wav must be 16-bit PCM")
        a = array.array("h", w.readframes(w.getnframes()))
    return a, rate, width, ch


def make_clip(names: list[str], lead_s: float, out: Path) -> float:
    """Mix the named tracks, prefix lead_s of silence, write a wav. Returns the clip length."""
    tracks = [read_track(n) for n in names]
    rate, width, ch = tracks[0][1:]
    n = max(len(t[0]) for t in tracks)
    mix = array.array("h", bytes(2 * n))
    for t in tracks:
        for i, v in enumerate(t[0]):
            mix[i] = max(-32768, min(32767, mix[i] + v))
    lead = array.array("h", bytes(2 * int(lead_s * rate) * ch))
    with wave.open(str(out), "wb") as o:
        o.setnchannels(ch); o.setsampwidth(width); o.setframerate(rate)
        o.writeframes((lead + mix + array.array("h", bytes(2 * rate * 8 * ch))).tobytes())
    return lead_s + n / ch / rate + 8


def wait_js(page, expr: str, timeout_s: float = 30.0):
    end = time.time() + timeout_s
    while time.time() < end:
        v = page.evaluate(expr)
        if v:
            return v
        time.sleep(0.25)
    raise TimeoutError(expr[:100])


def shot(page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    print(f"  screenshot {name}.png", flush=True)


def open_view(page, link: str) -> None:
    if not page.is_visible("#side-panel"):
        page.click("#agent-button")
    if page.is_visible("#panel-back"):
        page.click("#panel-back")
    page.click(f"#{link}")
    time.sleep(0.6)


def run(app: str, speech_at: float, wait_after: float) -> int:
    if urlparse(app).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("loopback only")
    from playwright.sync_api import sync_playwright

    tmp = Path(tempfile.mkdtemp(prefix="showcase_"))
    OUT.mkdir(parents=True, exist_ok=True)
    flags = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
             "--autoplay-policy=no-user-gesture-required"]
    t_speech = time.time() + speech_at       # the moment everyone's first word should be heard
    pages, contexts, browsers = {}, {}, []
    errors: list[str] = []
    with sync_playwright() as p:
        try:
            join_url = None
            for name, email, tracks in PEOPLE:
                lead = max(3.0, t_speech - time.time() - 6.0)   # about 6 s from launch to the microphone opening
                clip = tmp / f"{name.lower()}.wav"
                make_clip(tracks, lead, clip)
                b = p.chromium.launch(channel="msedge", headless=True,
                                      args=flags + [f"--use-file-for-fake-audio-capture={clip}%noloop"])
                browsers.append(b)
                ctx = b.new_context(viewport={"width": 1280, "height": 800}, permissions=["microphone", "camera"],
                                    record_video_dir=str(OUT / "video"), record_video_size={"width": 1280, "height": 800})
                pg = ctx.new_page()
                pg.on("console", lambda m, n=name: errors.append(f"{n}: {m.text[:140]}") if m.type == "error" else None)
                contexts[name], pages[name] = ctx, pg
                if join_url is None:
                    pg.goto(app)
                    pg.click("#create-button")
                    pg.fill("#host-name", name)
                    pg.fill("#host-email", email)
                    pg.click("#host-create-button")
                    pg.wait_for_selector("#share-screen:not(.hidden)", timeout=20000)
                    join_url = pg.input_value("#share-link")
                    pg.click("#share-join-button")
                    pg.wait_for_selector("#meeting:not(.hidden)", timeout=30000)
                    print(f"{name} created the meeting", flush=True)
                else:
                    pg.goto(join_url)
                    pg.wait_for_selector("#guest-setup:not(.hidden)", timeout=20000)
                    pg.fill("#guest-name", name)
                    pg.fill("#guest-email", email)
                    pg.click("#guest-join-button")
                    host = pages["Alice"]
                    if not host.is_visible("#lobby-list"):
                        host.click("#people-button")
                    host.wait_for_selector("#lobby-list button:text-is('Admit')", timeout=20000)
                    host.click("#lobby-list button:text-is('Admit')")
                    pg.wait_for_selector("#meeting:not(.hidden)", timeout=30000)
                    print(f"{name} was admitted", flush=True)
                pg.click("#agent-button")
                pg.wait_for_selector("#notes-button", state="visible", timeout=10000)
                if pg.get_attribute("#notes-button", "aria-checked") != "true":
                    pg.click("#notes-button")
                pg.wait_for_selector('#notes-button[aria-checked="true"]', timeout=10000)
                pg.click("#camera-button")
                print(f"{name} turned notes and camera on", flush=True)

            shot(pages["Alice"], "01-three-people-notes-on")
            left = t_speech - time.time()
            print(f"speech starts in about {left:.0f} s, meeting runs for about 110 s", flush=True)
            moments = {30: "02-off-the-record-starts", 50: "03-kept-out-markers-live", 70: "04-strike-that",
                       90: "05-salary-mention"}
            done = set()
            end = t_speech + 104 + wait_after
            while time.time() < end:
                t = time.time() - t_speech
                for at, label in moments.items():
                    if t >= at and at not in done:
                        done.add(at)
                        for name in pages:
                            shot(pages[name], f"{label}-{name.lower()}")
                time.sleep(0.5)

            for name, pg in pages.items():
                me = contexts[name].request.get(app + "/api/me").json()
                proof = {"person": name, "approved_lines": [l.get("text") for l in me.get("lines", [])],
                         "kept_out": me.get("kept_out", []), "insights": me.get("insights", {})}
                (OUT / f"proof_{name.lower()}.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
                print(f"{name}: {len(proof['approved_lines'])} approved lines, {len(proof['kept_out'])} kept out", flush=True)
                shot(pg, f"06-final-captions-{name.lower()}")
                open_view(pg, "link-insights")
                shot(pg, f"07-insights-{name.lower()}")
                open_view(pg, "link-explain")
                shot(pg, f"08-how-it-decides-{name.lower()}")
                pg.click("#panel-back")
                chip = pg.query_selector("#captions [data-category]")
                if chip:
                    chip.click()
                    time.sleep(0.6)
                    shot(pg, f"09-why-kept-out-{name.lower()}")
            diag = contexts["Alice"].request.get(app + "/api/diagnostics").json()
            (OUT / "diagnostics_alice.json").write_text(json.dumps(diag, indent=2), encoding="utf-8")
        finally:
            for ctx in contexts.values():
                ctx.close()
            for b in browsers:
                b.close()
    (OUT / "console_errors.txt").write_text("\n".join(errors[:50]), encoding="utf-8")
    print(f"videos in {OUT / 'video'}, screenshots in {SHOTS}", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", default="http://127.0.0.1:8799")
    ap.add_argument("--speech-at", type=float, default=75.0, help="seconds from start until the first word")
    ap.add_argument("--wait-after", type=float, default=20.0)
    a = ap.parse_args()
    return run(a.app, a.speech_at, a.wait_after)


if __name__ == "__main__":
    sys.exit(main())
