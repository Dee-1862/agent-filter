"""Two-browser proof of the whole live chain (no hardware): Edge + fake devices -> livekit-client ->
LiveKit -> bot -> VAD -> Whisper -> PII -> policy -> hold buffer -> approved caption in the page.

Context A (host) creates a meeting, B asks to join and A admits in the page. Both turn notes on, A's
fake microphone speaks a WAV, A turns its fake camera on. Checks:
  * an approved line appears in A's page (#captions) and in GET /api/me
  * B's page shows A's remote <video> playing (videoWidth > 0)
  * diagnostics reached hearing_you
  * speech-end to caption latency per spoken turn (speech end = last server-side loud sample)

  python experiments/browser_chain.py --app http://127.0.0.1:8796 [--wav clip.wav] [--json out.json]

Needs `pip install playwright` and Microsoft Edge (channel msedge). Loopback only. Uses the repo's
synthetic demo audio (demo_audio/*.wav is gitignored and never committed).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import wave
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
# (start, end) of alice's two turns in demo_audio/alice.wav
ALICE_TURNS = ((0.0, 7.9), (27.6, 32.3))

CAPTION_OBSERVER = """
(() => {
  window.__caps = [];
  const watch = () => {
    const el = document.getElementById('captions');
    if (!el) return setTimeout(watch, 200);
    let n = 0;
    const count = () => el.querySelectorAll('[data-id], .caption, p, li, div').length;
    const note = () => { const c = el.innerText.trim().length ? el.innerText.trim().split(/\\n/).filter(Boolean).length : 0;
                         while (n < c) { n++; window.__caps.push(Date.now()); } };
    new MutationObserver(note).observe(el, {childList: true, subtree: true, characterData: true});
    note();
  };
  watch();
})();
"""


def make_clip(src: Path, out: Path, lead_s: float, tail_s: float = 5.0, gap_s: float = 3.0) -> dict:
    """lead silence + alice turn 1 + gap + alice turn 2 + tail, 16 kHz mono. Returns layout (seconds)."""
    with wave.open(str(src), "rb") as w:
        rate, width, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
        parts = []
        for a, b in ALICE_TURNS:
            w.setpos(int(a * rate))
            parts.append(w.readframes(int((b - a) * rate)))
    sil = lambda s: b"\0" * (int(s * rate) * width * ch)  # noqa: E731
    with wave.open(str(out), "wb") as o:
        o.setnchannels(ch); o.setsampwidth(width); o.setframerate(rate)
        o.writeframes(sil(lead_s) + parts[0] + sil(gap_s) + parts[1] + sil(tail_s))
    t1 = lead_s + ALICE_TURNS[0][1] - ALICE_TURNS[0][0]
    t2 = t1 + gap_s + ALICE_TURNS[1][1] - ALICE_TURNS[1][0]
    return {"turn_ends_in_clip": [round(t1, 2), round(t2, 2)], "length": round(t2 + tail_s, 2)}


def make_silence(out: Path, seconds: float = 40.0, rate: int = 16000) -> None:
    with wave.open(str(out), "wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(rate)
        o.writeframes(b"\0\0" * int(rate * seconds))


def wait_js(page, expr: str, timeout_ms: int = 30000, every: float = 0.25):
    """Poll a JS expression with page.evaluate. (wait_for_function evals a string, which the page CSP forbids.)"""
    end = time.time() + timeout_ms / 1000.0
    while time.time() < end:
        v = page.evaluate(expr)
        if v:
            return v
        time.sleep(every)
    raise TimeoutError(f"condition not met in {timeout_ms} ms: {expr[:120]}")


def episodes(trace: list[dict], gap: float = 1.2) -> list[tuple[float, float]]:
    """Speech episodes (start, end) in epoch seconds from the diagnostics trace."""
    loud = [s["t"] for s in trace if s["loud"]]
    out: list[list[float]] = []
    for t in loud:
        if out and t - out[-1][1] <= gap:
            out[-1][1] = t
        else:
            out.append([t, t])
    return [(a, b) for a, b in out]


def latencies(trace: list[dict], caption_times: list[float]) -> list[dict]:
    """For each speech episode, the first caption that appears after its end."""
    eps = episodes(trace)
    res = []
    for i, (a, b) in enumerate(eps):
        nxt = eps[i + 1][0] if i + 1 < len(eps) else float("inf")
        c = [x for x in caption_times if x >= b - 0.2 and x < nxt + 30]
        c = [x for x in c if x < nxt or i + 1 == len(eps)]
        res.append({"episode": i + 1, "speech_s": round(b - a, 1),
                    "caption_after_speech_end_s": round(min(c) - b, 2) if c else None})
    return res


def run_chain(app: str, wav: Path, *, lead_s: float = 14.0, wait_s: float = 45.0, headed: bool = False,
              channel: str = "msedge", shots: Path | None = None, hold_note: str = "") -> dict:
    if urlparse(app).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("loopback only")
    from playwright.sync_api import sync_playwright

    tmp = Path(tempfile.mkdtemp(prefix="chain_"))
    clip, silent = tmp / "clip.wav", tmp / "silent.wav"
    layout = make_clip(wav, clip, lead_s)
    make_silence(silent)
    base = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            "--autoplay-policy=no-user-gesture-required"]
    r: dict = {"app": app, "hold_note": hold_note, "clip_layout": layout, "checks": {}}
    ck = r["checks"]
    problems: list[str] = []
    with sync_playwright() as p:
        b_host = p.chromium.launch(channel=channel, headless=not headed,
                                   args=base + [f"--use-file-for-fake-audio-capture={clip}%noloop"])
        b_guest = p.chromium.launch(channel=channel, headless=not headed,
                                    args=base + [f"--use-file-for-fake-audio-capture={silent}%noloop"])
        try:
            hc = b_host.new_context(viewport={"width": 1180, "height": 780}, permissions=["microphone", "camera"])
            gc = b_guest.new_context(viewport={"width": 1180, "height": 780}, permissions=["microphone", "camera"])
            host, guest = hc.new_page(), gc.new_page()
            host.add_init_script(CAPTION_OBSERVER)
            for pg, who in ((host, "host"), (guest, "guest")):
                pg.on("console", lambda m, who=who: problems.append(f"{who}: {m.text[:160]}")
                      if m.type == "error" else None)
            host.goto(app)
            host.click("#create-button")
            host.fill("#host-name", "Hana")
            host.fill("#host-email", "hana@example.com")
            host.click("#host-create-button")
            host.wait_for_selector("#share-screen:not(.hidden)", timeout=20000)
            host.click("#share-join-button")
            host.wait_for_selector("#meeting:not(.hidden)", timeout=30000)
            t_in_meeting = time.time()
            join_url = host.evaluate("document.getElementById('info-link').value")
            r["join_url_shape"] = urlparse(join_url).path.rsplit("/", 1)[0]

            guest.goto(join_url)
            guest.wait_for_selector("#guest-setup:not(.hidden)", timeout=20000)
            guest.fill("#guest-name", "Gail")
            guest.fill("#guest-email", "gail@example.com")
            guest.click("#guest-join-button")
            host.click("#people-button") if not host.is_visible("#lobby-list") else None
            host.wait_for_selector("#lobby-list button", timeout=20000)
            host.click("#lobby-list button:text-is('Admit')")
            guest.wait_for_selector("#meeting:not(.hidden)", timeout=30000)
            ck["guest_admitted"] = True

            # notes on for both (side panel -> Off The Record)
            for pg in (host, guest):
                pg.click("#agent-button")
                pg.wait_for_selector("#notes-button", state="visible", timeout=10000)
                if pg.get_attribute("#notes-button", "aria-checked") != "true":
                    pg.click("#notes-button")
                pg.wait_for_selector('#notes-button[aria-checked="true"]', timeout=10000)
            ck["notes_on_both"] = True
            r["seconds_from_host_join_to_notes_on"] = round(time.time() - t_in_meeting, 1)

            # camera on for the host; guest must see it playing
            host.click("#camera-button")
            wait_js(guest,
                "(() => { const t = [...document.querySelectorAll('.tile')].find(x => !x.classList.contains('self'));"
                " const v = t && t.querySelector('.tile-video'); return !!v && v.videoWidth > 0 && !v.paused; })()",
                40000)
            r["guest_sees_host_video_width"] = guest.evaluate(
                "[...document.querySelectorAll('.tile')].find(x => !x.classList.contains('self'))"
                ".querySelector('.tile-video').videoWidth")
            ck["remote_video_playing"] = r["guest_sees_host_video_width"] > 0

            # wait for the spoken turns; trace server-side audio state every ~100 ms
            trace: list[dict] = []
            states: set[str] = set()
            t_clip_end = time.time() + 3.0   # conservative: the clip has been playing since the host joined
            end_after = time.time() + layout["length"] + wait_s
            while time.time() < end_after:
                d = hc.request.get(app + "/api/diagnostics").json()["me"]
                states.add(d["state"])
                loud = d["audio_rms"] >= 200.0
                trace.append({"t": time.time(), "loud": loud, "level": d["audio_level"]})
                if (len(trace) % 10 == 0 and int(host.evaluate("window.__caps.length")) >= 2
                        and time.time() > t_clip_end):
                    break
                time.sleep(0.1)
            caps = [c / 1000.0 for c in host.evaluate("window.__caps")]
            me = hc.request.get(app + "/api/me").json()
            r["diagnostics_states_seen"] = sorted(states)
            ck["hearing_you"] = "hearing_you" in states
            ck["line_in_api_me"] = len(me.get("lines", [])) > 0
            ck["line_in_dom"] = len(caps) > 0
            r["approved_lines_in_api_me"] = len(me.get("lines", []))
            r["first_line_text_for_owner"] = (me["lines"][0]["text"][:100] if me.get("lines") else None)
            r["caption_dom_text"] = host.inner_text("#captions")[:160]
            r["latency"] = latencies(trace, caps)
            r["max_audio_level"] = max((s["level"] for s in trace), default=0)
            gd = gc.request.get(app + "/api/diagnostics").json()["me"]
            r["guest_state_with_silent_mic"] = gd["state"]
            if shots:
                shots.mkdir(parents=True, exist_ok=True)
                host.screenshot(path=str(shots / "chain-host.png"))
                guest.screenshot(path=str(shots / "chain-guest.png"))
            r["console_errors"] = problems[:8]
        finally:
            b_host.close()
            b_guest.close()
    r["ok"] = all(ck.values()) and len(ck) >= 6
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", default="http://127.0.0.1:8796")
    ap.add_argument("--wav", default=str(ROOT / "demo_audio" / "alice.wav"))
    ap.add_argument("--lead", type=float, default=14.0, help="silence before the first turn (time to admit/notes on)")
    ap.add_argument("--wait", type=float, default=45.0)
    ap.add_argument("--note", default="", help="free text stored in the result (e.g. hold seconds)")
    ap.add_argument("--json", help="write the result here")
    ap.add_argument("--shots", help="directory for screenshots")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    res = run_chain(a.app, Path(a.wav), lead_s=a.lead, wait_s=a.wait, headed=a.headed,
                    shots=Path(a.shots) if a.shots else None, hold_note=a.note)
    out = json.dumps(res, indent=2)
    print(out)
    if a.json:
        Path(a.json).write_text(out, encoding="utf-8")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
