"""LiveKit bot: join a room, transcribe each participant's audio track separately.

Speaker identity = participant.identity (no diarization needed: one track per
participant). The livekit SDK is imported lazily so this module imports without it.

NOT VERIFIED END-TO-END in the authoring environment (no LiveKit server / SDK
available). API usage follows the documented livekit.rtc / livekit.api Python SDK.

    python -m otr.ingest.livekit_source --room demo
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import AsyncIterator, Callable, Optional

from otr.types import Segment
from .stt import SR, UtteranceChunker, load_whisper, next_id


class LiveKitSource:
    def __init__(self, room: str = "demo", url: Optional[str] = None, api_key: Optional[str] = None,
                 api_secret: Optional[str] = None, identity: str = "otr-bot", model: str = "base.en",
                 transcribe: Optional[Callable[[object], str]] = None):
        self.room_name, self.identity, self.model = room, identity, model
        self.url = url or os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
        self.api_key = api_key or os.environ.get("LIVEKIT_API_KEY", "devkey")
        self.api_secret = api_secret or os.environ.get("LIVEKIT_API_SECRET", "secret")
        self._transcribe = transcribe
        self._queue: "asyncio.Queue[Optional[Segment]]" = asyncio.Queue()
        self._tasks: set = set()

    def _token(self) -> str:
        from livekit import api  # lazy
        return (api.AccessToken(self.api_key, self.api_secret).with_identity(self.identity)
                .with_name(self.identity)
                .with_grants(api.VideoGrants(room_join=True, room=self.room_name,
                                             can_publish=False, can_subscribe=True))
                .to_jwt())

    async def _consume(self, track, participant, t0: float) -> None:
        from livekit import rtc  # lazy
        loop = asyncio.get_running_loop()
        # t0 = seconds since bot start when this track was subscribed; utterance
        # times are t0 + position in the participant's audio stream.
        chunker = UtteranceChunker(self._transcribe, t0=t0)
        stream = rtc.AudioStream(track, sample_rate=SR, num_channels=1)
        speaker = participant.identity

        async def emit(utts):
            for u in utts:
                if u.text:
                    await self._queue.put(Segment(next_id(), speaker, u.text,
                                                  round(u.t_start, 3), round(u.t_end, 3)))
        async for ev in stream:
            pcm = bytes(ev.frame.data)  # int16 interleaved
            # whisper is CPU-bound: run off the event loop
            utts = await loop.run_in_executor(None, chunker.feed, pcm)
            await emit(utts)
        await emit(await loop.run_in_executor(None, chunker.flush))

    async def segments(self) -> AsyncIterator[Segment]:
        try:
            from livekit import rtc  # lazy
        except ImportError as e:
            raise RuntimeError("livekit not installed: pip install -r requirements-ingest.txt") from e
        if self._transcribe is None:
            self._transcribe = load_whisper(self.model)
        room = rtc.Room()
        start = time.monotonic()

        @room.on("track_subscribed")
        def on_track(track, publication, participant):
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                t = asyncio.ensure_future(self._consume(track, participant, time.monotonic() - start))
                self._tasks.add(t)
                t.add_done_callback(self._tasks.discard)

        @room.on("disconnected")
        def on_disc(*_):
            self._queue.put_nowait(None)

        await room.connect(self.url, self._token(), options=rtc.RoomOptions(auto_subscribe=True))
        try:
            while True:
                seg = await self._queue.get()
                if seg is None:
                    break
                yield seg
        finally:
            for t in list(self._tasks):
                t.cancel()
            await room.disconnect()


async def _amain(args) -> None:
    src = LiveKitSource(room=args.room, model=args.model)
    async for seg in src.segments():
        print(json.dumps(seg.to_dict()), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Join a LiveKit room and print Segments as JSONL")
    ap.add_argument("--room", default="demo")
    ap.add_argument("--model", default="base.en")
    try:
        asyncio.run(_amain(ap.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
