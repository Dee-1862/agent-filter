"""Join the consent-mode meeting as a participant and speak a WAV file into it as a microphone.

Dependency-light stand-in for a person with a mic: stdlib `wave` decodes the file (no ffmpeg),
numpy resamples to 48 kHz mono like a browser microphone, and 10 ms frames are published to
LiveKit at real-time pace. It uses only the real server endpoints, so the whole server chain
runs: LiveKit -> bot subscription -> VAD -> Whisper -> policy -> hold buffer -> approved line.

  python experiments/inject_audio.py demo_audio/alice.wav --start 0 --end 7.8 --app http://127.0.0.1:8010
  python experiments/inject_audio.py clip.wav --join-url http://127.0.0.1:8010/m/ROOM   # guest; host admits in the page
  python experiments/inject_audio.py clip.wav --legacy                                   # old single-room /api/join flow

Default flow: create a meeting as host (/api/meetings), publish the mic, turn notes on
(/api/consent), play the clip, then report when each approved line appeared (only timing and
counts are printed; with --show-text the approved text of THIS tool's own participant too).
Loopback URLs only. The clip must be speech you are free to use (the repo's synthetic demo audio).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from pathlib import Path
from urllib.parse import urlparse

import httpx
import numpy as np

RATE = 48000
FRAME = RATE // 100   # 10 ms


def require_loopback(url: str) -> str:
    u = urlparse(url)
    if u.scheme not in ("http", "https", "ws", "wss") or u.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit(f"refusing non-loopback URL: {url}")
    return url.rstrip("/")


def load_wav_48k(path: Path, start: float = 0.0, end: float | None = None) -> np.ndarray:
    """Decode 8/16/32-bit PCM WAV with the stdlib, mix to mono, resample to 48 kHz int16."""
    with wave.open(str(path), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        w.setpos(min(n, int(start * rate)))
        raw = w.readframes((int(end * rate) if end else n) - int(start * rate))
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(width)
    if dtype is None:
        raise SystemExit(f"unsupported sample width {width * 8} bit; use 8/16/32-bit PCM WAV")
    a = np.frombuffer(raw, dtype=dtype).astype("float64")
    if width == 1:
        a = (a - 128) * 256
    elif width == 4:
        a = a / 65536
    if ch > 1:
        a = a[: len(a) // ch * ch].reshape(-1, ch).mean(axis=1)
    if rate != RATE and len(a):
        a = np.interp(np.arange(int(len(a) * RATE / rate)) / RATE, np.arange(len(a)) / rate, a)
    return np.clip(np.rint(a), -32768, 32767).astype(np.int16)


async def publish(room_url: str, token: str, pcm: np.ndarray, tail_s: float, stamps: dict) -> None:
    """Connect, publish a 48 kHz mono mic track, stream `pcm` in 10 ms frames in real time."""
    from livekit import rtc
    room = rtc.Room()
    await room.connect(room_url, token)
    source = rtc.AudioSource(RATE, 1)
    track = rtc.LocalAudioTrack.create_audio_track("injected-mic", source)
    await room.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    stamps["published"] = time.monotonic()
    try:
        await stamps["go"].wait()      # caller turns notes on first, then releases us
        stamps["speech_start"] = time.monotonic()
        total = len(pcm) + int(tail_s * RATE)
        pcm = np.concatenate([pcm, np.zeros(total - len(pcm), dtype=np.int16)])
        t0 = time.monotonic()
        for i in range(0, total - FRAME + 1, FRAME):
            await asyncio.sleep(max(0.0, t0 + i / RATE - time.monotonic()))
            await source.capture_frame(rtc.AudioFrame(pcm[i:i + FRAME].tobytes(), sample_rate=RATE,
                                                      num_channels=1, samples_per_channel=FRAME))
            if i >= len(pcm) - int(tail_s * RATE) and "speech_end" not in stamps:
                stamps["speech_end"] = time.monotonic()
        stamps["done"].set()
        await stamps["finish"].wait()
    finally:
        await room.disconnect()


async def watch(client: httpx.AsyncClient, stamps: dict, events: list, stop: asyncio.Event, show_text: bool) -> None:
    """Poll /api/me and /api/diagnostics every 50 ms; log when decodes and approved lines appear."""
    seen_lines: set[str] = set()
    seen_utt = 0
    while not stop.is_set():
        try:
            me = (await client.get("/api/me")).json()
            for line in me.get("lines", []):
                if line["id"] not in seen_lines:
                    seen_lines.add(line["id"])
                    events.append({"event": "approved_line", "t": time.monotonic(),
                                   "words": len(line["text"].split()),
                                   **({"text": line["text"]} if show_text else {})})
            dg = (await client.get("/api/diagnostics")).json()
            mine = dg.get("me", {})
            age = mine.get("stt_last_activity_age_s")
            if age is not None and age < 0.2 and mine.get("state") != "error":
                key = round(time.monotonic() - age, 1)
                if not events or events[-1].get("event") != "decoded" or abs(events[-1]["t"] - (time.monotonic() - age)) > 0.3:
                    events.append({"event": "decoded", "t": time.monotonic() - age,
                                   "decode_s": mine.get("stt_last_decode_s"), "_key": key})
            stamps["last_diag"] = dg
        except Exception as exc:  # noqa: BLE001
            stamps["watch_error"] = repr(exc)
        await asyncio.sleep(0.05)


async def run(args) -> dict:
    base = require_loopback(args.app)
    pcm = load_wav_48k(Path(args.wav), args.start, args.end)
    speech_s = len(pcm) / RATE
    stamps = {"go": asyncio.Event(), "done": asyncio.Event(), "finish": asyncio.Event()}
    events: list[dict] = []
    stop = asyncio.Event()
    async with httpx.AsyncClient(base_url=base, timeout=15) as client:
        if args.legacy:
            r = await client.post("/api/join", json={"name": args.name})
        elif args.join_url:
            room_id = urlparse(args.join_url).path.rstrip("/").rsplit("/", 1)[-1]
            r = await client.post(f"/api/meetings/{room_id}/request", json={"name": args.name, "email": "inject@example.com"})
            r.raise_for_status()
            print(f"waiting for the host to admit '{args.name}' in the page ...", flush=True)
            while True:
                s = (await client.get(f"/api/meetings/{room_id}/status")).json()
                if s["status"] == "admitted":
                    r = httpx.Response(200, json=s)
                    break
                if s["status"] == "denied":
                    raise SystemExit("host denied the request")
                await asyncio.sleep(0.5)
        else:
            r = await client.post("/api/meetings", json={"name": args.name, "email": "inject@example.com"})
        r.raise_for_status()
        access = r.json()
        if not access.get("token"):
            raise SystemExit("server returned no LiveKit token (livekit-api missing?)")
        room_url = require_loopback(access.get("url") or "ws://localhost:7880")
        if not args.legacy and not args.join_url:
            print(f"meeting: {access['join_url']}  (open it in the browser as the host to watch)", flush=True)
        pub = asyncio.create_task(publish(room_url, access["token"], pcm, args.tail, stamps))
        watcher = asyncio.create_task(watch(client, stamps, events, stop, args.show_text))
        try:
            while "published" not in stamps:
                if pub.done():
                    pub.result()
                await asyncio.sleep(0.05)
            if not args.no_consent:
                (await client.post("/api/consent", json={"recording": True})).raise_for_status()
            stamps["notes_on"] = time.monotonic()
            await asyncio.sleep(args.settle)             # let the bot subscribe before speaking
            stamps["go"].set()
            await asyncio.wait_for(stamps["done"].wait(), speech_s + args.tail + 30)
            deadline = time.monotonic() + args.wait
            while time.monotonic() < deadline:
                if any(e["event"] == "approved_line" for e in events) and args.stop_after_first:
                    break
                await asyncio.sleep(0.2)
            dg = (await client.get("/api/diagnostics")).json()
            final = {"diagnostics": dg}
        finally:
            stop.set()
            stamps["finish"].set()
            await asyncio.gather(watcher, return_exceptions=True)
            try:
                await client.post("/api/consent", json={"recording": False})
                await client.post("/api/leave")
            except Exception:  # noqa: BLE001
                pass
            await asyncio.gather(pub, return_exceptions=True)
    t_end = stamps.get("speech_end", stamps.get("speech_start", 0))
    rel = lambda t: round(t - t_end, 2)  # noqa: E731
    out = {"clip_seconds": round(speech_s, 2), "consent_given": not args.no_consent,
           "events_after_speech_end_s": [{k: (rel(v) if k == "t" else v) for k, v in e.items() if k != "_key"} for e in events],
           "approved_lines": sum(1 for e in events if e["event"] == "approved_line"),
           "bot": final["diagnostics"].get("bot", {}),
           "me_after": final["diagnostics"].get("me", {}),
           "models": final["diagnostics"].get("models", {}),
           "hold_seconds": final["diagnostics"].get("hold_seconds")}
    first_dec = next((e for e in events if e["event"] == "decoded"), None)
    first_line = next((e for e in events if e["event"] == "approved_line"), None)
    if first_dec and first_line:
        out["stt_latency_s"] = round(first_dec["t"] - t_end, 2)
        out["hold_latency_s"] = round(first_line["t"] - first_dec["t"], 2)
        out["end_to_end_s"] = round(first_line["t"] - t_end, 2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav")
    ap.add_argument("--app", default="http://127.0.0.1:8010")
    ap.add_argument("--name", default="Injected mic")
    ap.add_argument("--start", type=float, default=0.0, help="clip start, seconds")
    ap.add_argument("--end", type=float, default=None, help="clip end, seconds")
    ap.add_argument("--tail", type=float, default=2.0, help="seconds of silence sent after the clip")
    ap.add_argument("--settle", type=float, default=2.0, help="seconds between notes-on and speech")
    ap.add_argument("--wait", type=float, default=20.0, help="seconds to wait for approved lines after speech")
    ap.add_argument("--join-url", help="join an existing meeting as a guest (host must admit)")
    ap.add_argument("--legacy", action="store_true", help="use /api/join (single global room)")
    ap.add_argument("--no-consent", action="store_true", help="do not turn notes on (must produce nothing)")
    ap.add_argument("--stop-after-first", action="store_true")
    ap.add_argument("--show-text", action="store_true", help="include this participant's own approved text")
    args = ap.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
