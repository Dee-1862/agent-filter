"""Run local, synthetic multi-speaker WAV scenarios through the live demo.

Only loopback app/LiveKit URLs are accepted. The manifest must declare that all
speech is synthetic; this tool never reads or uploads meeting recordings.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

SAMPLE_RATE = 16000
FRAME_SAMPLES = 320  # 20 ms


def require_loopback(url: str, schemes: tuple[str, ...]) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in schemes or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(f"Only loopback {', '.join(schemes)} URLs are allowed")
    return url.rstrip("/")


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("synthetic") is not True:
        raise ValueError("Manifest must set synthetic: true")
    observations = data.get("observe_at", [])
    if not isinstance(observations, list) or any(
        isinstance(at, bool) or not isinstance(at, (int, float)) or at < 0
        for at in observations
    ) or observations != sorted(observations):
        raise ValueError("observe_at must be a sorted list of nonnegative second offsets")
    people = data.get("participants")
    if not isinstance(people, list) or not people:
        raise ValueError("participants must be a nonempty list")
    names = set()
    for person in people:
        name = person.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Participant names must be distinct, nonempty strings")
        names.add(name)
        if not isinstance(person.get("join_at", 0), (int, float)) or person.get("join_at", 0) < 0:
            raise ValueError(f"Invalid join_at for {name}")
        actions = person.get("actions")
        if not isinstance(actions, list) or not actions:
            raise ValueError(f"{name} needs actions")
        prior = -1.0
        for action in actions:
            at = action.get("at")
            if not isinstance(at, (int, float)) or at < 0 or at < prior:
                raise ValueError(f"{name} actions must have increasing nonnegative at values")
            prior = at
            if ("recording" in action) == ("wav" in action):
                raise ValueError(f"{name} action needs exactly one of recording or wav")
            if "recording" in action and not isinstance(action["recording"], bool):
                raise ValueError(f"{name} recording must be boolean")
            if "wav" in action:
                wav = action["wav"]
                if not isinstance(wav, str) or not wav.lower().endswith(".wav"):
                    raise ValueError(f"{name} wav must be a WAV filename")
                file = (path.parent / wav).resolve()
                if not file.is_file():
                    raise ValueError(f"Missing WAV for {name}: {wav}")
                action["_path"] = file
    return data


def pcm16(path: Path) -> bytes:
    """Decode/resample a WAV locally with ffmpeg; stdout is 16 kHz mono PCM16."""
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"],
        capture_output=True, check=True,
    )
    return result.stdout


async def wait_until(start: float, offset: float) -> None:
    await asyncio.sleep(max(0.0, start + offset - time.monotonic()))


async def play_wav(source, path: Path) -> float:
    from livekit import rtc

    pcm = pcm16(path)
    frame_bytes = FRAME_SAMPLES * 2
    start = time.monotonic()
    for i in range(0, len(pcm), frame_bytes):
        piece = pcm[i:i + frame_bytes]
        if len(piece) < frame_bytes:
            piece += b"\0" * (frame_bytes - len(piece))
        await source.capture_frame(rtc.AudioFrame(
            piece, sample_rate=SAMPLE_RATE, num_channels=1,
            samples_per_channel=FRAME_SAMPLES,
        ))
    # UtteranceChunker emits only after at least 700 ms of silence. AudioSource
    # stops producing frames when the file ends, so explicitly send a tail.
    silence = rtc.AudioFrame(
        b"\0" * frame_bytes, sample_rate=SAMPLE_RATE, num_channels=1,
        samples_per_channel=FRAME_SAMPLES,
    )
    for _ in range(50):
        await source.capture_frame(silence)
    # AudioSource.capture_frame paces frames, but wait for the SDK queue to drain.
    await source.wait_for_playout()
    return time.monotonic() - start


async def run_person(person: dict, base: str, room_url: str, start: float,
                     done: asyncio.Event, release: asyncio.Event) -> dict:
    from livekit import rtc

    await wait_until(start, person.get("join_at", 0))
    name = person["name"]
    async with httpx.AsyncClient(base_url=base, timeout=15) as client:
        joined = await client.post("/api/join", json={"name": name})
        joined.raise_for_status()
        access = joined.json()
        identity = access["identity"]
        room = rtc.Room()
        actions = []
        try:
            await room.connect(room_url, access["token"])
            source = rtc.AudioSource(SAMPLE_RATE, 1)
            track = rtc.LocalAudioTrack.create_audio_track("synthetic-voice", source)
            await room.local_participant.publish_track(track)
            for action in person["actions"]:
                await wait_until(start, person.get("join_at", 0) + action["at"])
                if "recording" in action:
                    response = await client.post("/api/consent", json={"recording": action["recording"]})
                    response.raise_for_status()
                    actions.append({"at": action["at"], "recording": action["recording"]})
                else:
                    duration = await play_wav(source, action["_path"])
                    actions.append({"at": action["at"], "wav": action["wav"],
                                    "playback_seconds": round(duration, 2)})
            done.set()
            await release.wait()
            return {"name": name, "identity": identity, "actions": actions}
        finally:
            done.set()
            # Explicitly turn OFF before disconnect, including error paths.
            try:
                await client.post("/api/consent", json={"recording": False})
            finally:
                await room.disconnect()


async def run(manifest: dict, base: str, settle: float) -> dict:
    require_loopback(base, ("http",))
    async with httpx.AsyncClient(base_url=base, timeout=10) as client:
        response = await client.get("/api/config")
        response.raise_for_status()
        config = response.json()
    room_url = require_loopback(config["url"], ("ws", "wss"))
    # Observer receives only server-approved /api/me data and publishes no audio.
    async with httpx.AsyncClient(base_url=base, timeout=10) as observer:
        joined = await observer.post("/api/join", json={"name": "Simulation observer"})
        joined.raise_for_status()
        observer_identity = joined.json()["identity"]
        start = time.monotonic() + 0.5
        done = [asyncio.Event() for _ in manifest["participants"]]
        release = asyncio.Event()
        tasks = [asyncio.create_task(run_person(p, base, room_url, start, finished, release))
                 for p, finished in zip(manifest["participants"], done)]
        async def observe(at: float) -> dict:
            await wait_until(start, at)
            response = await observer.get("/api/me")
            response.raise_for_status()
            view = response.json()
            status = view["participants"]
            status.pop(observer_identity, None)
            return {"at": at, "status": status, "approved_lines": view["lines"]}

        observation_tasks = [asyncio.create_task(observe(at))
                             for at in manifest.get("observe_at", [])]
        try:
            while not all(event.is_set() for event in done):
                finished, _ = await asyncio.wait(tasks, timeout=0.2,
                                                  return_when=asyncio.FIRST_EXCEPTION)
                errors = [task.exception() for task in finished if not task.cancelled()]
                if errors:
                    raise errors[0]
            await asyncio.sleep(settle)
            observations = await asyncio.gather(*observation_tasks)
            snapshot_response = await observer.get("/api/me")
            snapshot_response.raise_for_status()
            snapshot = snapshot_response.json()
            status = snapshot["participants"]
            status.pop(observer_identity, None)
            lines = snapshot["lines"]
            release.set()
            people = await asyncio.gather(*tasks)
            return {"participants": people, "status_at_snapshot": status,
                    "approved_lines": lines,
                    "observations": observations,
                    "approved_by_speaker": {p["name"]: [line for line in lines
                                           if line["speaker"] == p["identity"]] for p in people}}
        finally:
            for task in observation_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*observation_tasks, return_exceptions=True)
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await observer.post("/api/leave")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--app", default="http://127.0.0.1:8765")
    parser.add_argument("--settle", type=float, default=12.0,
                        help="Seconds to wait for policy commit after playback")
    parser.add_argument("--output", type=Path, help="Local sanitized JSON output")
    args = parser.parse_args()
    if args.settle < 0:
        parser.error("--settle must be nonnegative")
    result = asyncio.run(run(load_manifest(args.manifest), args.app, args.settle))
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
