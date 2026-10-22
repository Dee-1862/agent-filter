"""LiveKit audio ingest with explicit, per-participant consent.

The bot never auto-subscribes. Only LiveKit participant identities explicitly
enabled through ``set_consent`` may have audio subscribed or yield Segments.
SDK imports are lazy so replay mode works without LiveKit installed.
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
                 transcribe: Optional[Callable[[object], str]] = None,
                 on_participant_left: Optional[Callable[[str], None]] = None):
        self.room_name, self.identity, self.model = room, identity, model
        self.url = url or os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
        self.api_key = api_key or os.environ.get("LIVEKIT_API_KEY", "devkey")
        self.api_secret = api_secret or os.environ.get("LIVEKIT_API_SECRET", "secret")
        self._transcribe = transcribe
        self.on_participant_left = on_participant_left
        self._room = None
        self._consent: dict[str, bool] = {}
        self._epoch: dict[str, int] = {}
        self._queue: asyncio.Queue[tuple[str, int, Segment] | None] = asyncio.Queue()
        self._tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._closed = False

    def consent_snapshot(self) -> dict[str, bool]:
        """Return a copy of consent states keyed by LiveKit identity."""
        return dict(self._consent)

    def _participant(self, identity: str):
        return self._room.remote_participants.get(identity) if self._room is not None else None

    def _cancel_identity(self, identity: str) -> None:
        for (owner, _), task in list(self._tasks.items()):
            if owner == identity:
                task.cancel()

    def _discard_identity(self, identity: str) -> None:
        kept = []
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if item is None or item[0] != identity:
                kept.append(item)
        for item in kept:
            self._queue.put_nowait(item)

    def _set_participant_subscription(self, participant, enabled: bool) -> None:
        from livekit import rtc
        for publication in participant.track_publications.values():
            if publication.kind == rtc.TrackKind.KIND_AUDIO:
                try:
                    publication.set_subscribed(enabled)
                except Exception:
                    if not enabled and self._room is not None:
                        asyncio.create_task(self._room.disconnect())
                    raise

    def set_consent(self, identity: str, enabled: bool) -> None:
        """Set consent for a trusted LiveKit identity, before or during connection.

        The caller must authenticate and bind identity to a participant. Display
        names or untrusted client-provided identity strings are insufficient.
        A departing participant's consent is revoked before a future rejoin.
        """
        if not isinstance(identity, str) or not identity or identity == self.identity:
            raise ValueError("consent requires a nonempty human LiveKit identity")
        enabled = bool(enabled)
        old = self._consent.get(identity, False)
        self._consent[identity] = enabled
        if old == enabled:
            return
        self._epoch[identity] = self._epoch.get(identity, 0) + 1
        if not enabled:
            self._cancel_identity(identity)
            self._discard_identity(identity)
        participant = self._participant(identity)
        if participant is not None:
            self._set_participant_subscription(participant, enabled)

    def _current(self, identity: str, epoch: int) -> bool:
        return not self._closed and self._consent.get(identity, False) and self._epoch.get(identity, 0) == epoch

    def _token(self) -> str:
        from livekit import api  # lazy
        return (api.AccessToken(self.api_key, self.api_secret).with_identity(self.identity)
                .with_name(self.identity)
                .with_grants(api.VideoGrants(room_join=True, room=self.room_name,
                                             can_publish=False, can_subscribe=True))
                .to_jwt())

    async def _consume(self, track, identity: str, epoch: int, t0: float) -> None:
        from livekit import rtc  # lazy
        loop = asyncio.get_running_loop()
        # Do not release a confirmed partial prefix before later words can
        # reveal sensitive context (e.g. an employee number or salary).
        # The policy layer receives only a closed chunk (silence or the
        # chunker's 20-second safety cap), never a speculative partial prefix.
        chunker = UtteranceChunker(self._transcribe, t0=t0, partial_every=float("inf"))
        stream = rtc.AudioStream(track, sample_rate=SR, num_channels=1)

        async def emit(utts):
            if not self._current(identity, epoch):
                return
            for u in utts:
                if u.text and self._current(identity, epoch):
                    self._queue.put_nowait((identity, epoch, Segment(next_id(), identity, u.text,
                                                round(u.t_start, 3), round(u.t_end, 3))))
        try:
            async for ev in stream:
                if not self._current(identity, epoch):
                    break
                pcm = bytes(ev.frame.data)
                utts = await loop.run_in_executor(None, chunker.feed, pcm)
                await emit(utts)
            if self._current(identity, epoch):
                await emit(await loop.run_in_executor(None, chunker.flush))
        finally:
            if hasattr(stream, "aclose"):
                await stream.aclose()

    async def segments(self) -> AsyncIterator[Segment]:
        try:
            from livekit import rtc  # lazy
        except ImportError as e:
            raise RuntimeError("livekit not installed: pip install -r requirements-ingest.txt") from e
        if self._transcribe is None:
            self._transcribe = load_whisper(self.model)
        room = rtc.Room()
        self._room = room
        self._closed = False
        start = time.monotonic()

        @room.on("participant_connected")
        def on_participant(participant):
            self._consent.setdefault(participant.identity, False)

        @room.on("participant_disconnected")
        def on_departure(participant):
            self.set_consent(participant.identity, False)
            if self.on_participant_left is not None:
                self.on_participant_left(participant.identity)

        @room.on("track_published")
        def on_published(publication, participant):
            if publication.kind == rtc.TrackKind.KIND_AUDIO:
                publication.set_subscribed(self._consent.get(participant.identity, False))

        @room.on("track_subscribed")
        def on_subscribed(track, publication, participant):
            identity = participant.identity
            if track.kind != rtc.TrackKind.KIND_AUDIO:
                return
            if not self._consent.get(identity, False) or self._participant(identity) is not participant:
                publication.set_subscribed(False)
                return
            key = (identity, publication.sid)
            old = self._tasks.pop(key, None)
            if old is not None:
                old.cancel()
            task = asyncio.create_task(self._consume(track, identity, self._epoch.get(identity, 0),
                                                      time.monotonic() - start))
            self._tasks[key] = task
            task.add_done_callback(lambda finished, k=key: self._tasks.pop(k, None)
                                   if self._tasks.get(k) is finished else None)

        @room.on("track_unsubscribed")
        def on_unsubscribed(track, publication, participant):
            task = self._tasks.pop((participant.identity, publication.sid), None)
            if task is not None:
                task.cancel()

        @room.on("disconnected")
        def on_disc(*_):
            self._closed = True
            for identity in list(self._consent):
                self._consent[identity] = False
                self._epoch[identity] = self._epoch.get(identity, 0) + 1
            for task in self._tasks.values():
                task.cancel()
            self._queue.put_nowait(None)

        try:
            await room.connect(self.url, self._token(), options=rtc.RoomOptions(auto_subscribe=False))
            for participant in room.remote_participants.values():
                self._consent.setdefault(participant.identity, False)
                if self._consent[participant.identity]:
                    self._set_participant_subscription(participant, True)
            while True:
                item = await self._queue.get()
                if item is None:
                    break
                identity, epoch, seg = item
                if self._current(identity, epoch):
                    yield seg
        finally:
            self._closed = True
            for identity in list(self._consent):
                self._consent[identity] = False
                self._epoch[identity] = self._epoch.get(identity, 0) + 1
            for t in list(self._tasks.values()):
                t.cancel()
            self._tasks.clear()
            self._queue = asyncio.Queue()
            self._room = None
            await room.disconnect()


async def _amain(args) -> None:
    src = LiveKitSource(room=args.room, model=args.model)
    for identity in args.consent_identity:
        src.set_consent(identity, True)
    async for seg in src.segments():
        print(json.dumps(seg.to_dict()), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Join a LiveKit room and print Segments as JSONL")
    ap.add_argument("--room", default="demo")
    ap.add_argument("--model", default="base.en")
    ap.add_argument("--consent-identity", action="append", default=[],
                    help="Explicitly opt in this authenticated LiveKit identity (repeatable)")
    try:
        asyncio.run(_amain(ap.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
