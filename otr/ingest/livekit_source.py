"""LiveKit audio ingest with explicit, per-participant consent.

The bot never auto-subscribes. Only LiveKit participant identities explicitly
enabled through ``set_consent`` may have audio subscribed or yield Segments.
SDK imports are lazy so replay mode works without LiveKit installed.

Audio path: browser mic (48 kHz, usually mono, auto gain + noise suppression) ->
LiveKit SFU -> rtc.AudioStream(sample_rate=16000, num_channels=1), which resamples
inside the SDK -> 60 ms batches -> UtteranceChunker (adaptive VAD, 700 ms silence
close) -> faster-whisper in a worker thread -> Segment. Frames in any other format
are converted defensively with stt.to_mono16k. A muted or stalled track flushes the
open utterance after IDLE_FLUSH_S so the last words are not stuck waiting for silence.
`diagnostics()` exposes text-free health numbers for scripts/mic_check.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import AsyncIterator, Callable, Optional

from otr.types import Segment
from . import defaults as _defaults
from .stt import SR, UtteranceChunker, load_whisper, next_id, shared_whisper, to_mono16k


BATCH_BYTES = SR * 60 // 1000 * 2   # feed the VAD in 60 ms batches, not 100 executor hops per second
IDLE_FLUSH_S = 0.9                  # no frames for this long (mute, stall) closes an open utterance
RECONNECT_BACKOFF_S = (1.0, 2.0, 4.0, 8.0)


class LiveKitSource:
    def __init__(self, room: str = "demo", url: Optional[str] = None, api_key: Optional[str] = None,
                 api_secret: Optional[str] = None, identity: str = "otr-bot", model: str = "base.en",
                 transcribe: Optional[Callable[[object], str]] = None,
                 on_participant_left: Optional[Callable[[str], None]] = None):
        self.room_name, self.identity, self.model = room, identity, model
        self.url = url or os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
        self.api_key = api_key or _defaults.api_key()
        self.api_secret = api_secret or _defaults.api_secret()
        self._transcribe = transcribe
        self.on_participant_left = on_participant_left
        self._room = None
        self._consent: dict[str, bool] = {}
        self._epoch: dict[str, int] = {}
        self._queue: asyncio.Queue[tuple[str, int, Segment] | None] = asyncio.Queue()
        self._tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._closed = False
        self._stopping = False
        # Health, text-free: read by diagnostics() only.
        self.state = "idle"          # idle | loading_model | connecting | connected | reconnecting | failed
        self.error = ""
        self._stats: dict[str, dict] = {}

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
            self._stats.pop(identity, None)
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

    async def preload(self) -> None:
        """Load and warm the Whisper model now (server start), not on the first sentence."""
        if self._transcribe is not None:
            return
        self.state = "loading_model"
        loop = asyncio.get_running_loop()
        try:
            self._transcribe = await loop.run_in_executor(None, shared_whisper, self.model)
        except Exception as e:  # noqa: BLE001
            self.state, self.error = "failed", f"stt: {e}"[:300]
            raise
        if self.state == "loading_model":
            self.state = "idle"

    def _stat(self, identity: str) -> dict:
        return self._stats.setdefault(identity, {"frames": 0, "last_frame": None, "rms": 0.0, "floor": 0.0,
                                                 "last_stt": None, "stt_s": 0.0, "stt_audio_s": 0.0,
                                                 "utterances": 0, "rate": 0, "channels": 0, "in_utterance": False})

    @staticmethod
    def _is_audio(pub) -> bool:
        kind = getattr(pub, "kind", None)
        try:
            from livekit import rtc
            return kind == rtc.TrackKind.KIND_AUDIO
        except Exception:  # noqa: BLE001 - SDK absent (tests with fakes)
            return "audio" in str(kind).lower()

    def diagnostics(self) -> dict:
        """Numbers only: no transcript text. Ages are seconds since the event, None if it never happened."""
        now = time.monotonic()
        age = lambda t: None if t is None else round(now - t, 2)  # noqa: E731
        people = {}
        for identity in set(self._consent) | set(self._stats):
            p = self._participant(identity)
            pubs = [pub for pub in (p.track_publications.values() if p is not None else [])
                    if self._is_audio(pub)]
            st = self._stats.get(identity, {})
            people[identity] = {
                "in_room": p is not None, "consent": bool(self._consent.get(identity, False)),
                "audio_published": bool(pubs),
                "subscribed": any(bool(getattr(pub, "subscribed", False)) or getattr(pub, "track", None) is not None
                                  for pub in pubs),
                "muted": bool(pubs) and all(bool(getattr(pub, "muted", False)) for pub in pubs),
                "frames": st.get("frames", 0), "last_frame_age_s": age(st.get("last_frame")),
                "rms": round(st.get("rms", 0.0), 1), "noise_floor": round(st.get("floor", 0.0), 1),
                "sample_rate": st.get("rate", 0), "channels": st.get("channels", 0),
                "speaking": bool(st.get("in_utterance", False)),
                "stt_last_age_s": age(st.get("last_stt")), "stt_last_decode_s": round(st.get("stt_s", 0.0), 3),
                "stt_last_audio_s": round(st.get("stt_audio_s", 0.0), 2), "utterances": st.get("utterances", 0)}
        return {"bot": {"state": self.state, "error": self.error, "model": self.model,
                        "model_loaded": self._transcribe is not None, "room": self.room_name},
                "participants": people}

    async def _consume(self, track, identity: str, epoch: int, t0: float) -> None:
        from livekit import rtc  # lazy
        loop = asyncio.get_running_loop()
        # Do not release a confirmed partial prefix before later words can
        # reveal sensitive context (e.g. an employee number or salary).
        # The policy layer receives only a closed chunk (silence or the
        # chunker's safety cap), never a speculative partial prefix.
        chunker = UtteranceChunker(self._transcribe, t0=t0, partial_every=float("inf"))
        stream = rtc.AudioStream(track, sample_rate=SR, num_channels=1)
        st = self._stat(identity)
        st["last_frame"] = time.monotonic()
        lock = asyncio.Lock()   # the stream loop and the idle watchdog never touch the chunker together

        async def emit(utts, decoded: bool):
            if decoded:
                st["last_stt"] = time.monotonic()
                st["stt_s"] = getattr(chunker, "last_transcribe_s", 0.0)
                st["stt_audio_s"] = getattr(chunker, "last_audio_s", 0.0)
            st["in_utterance"] = bool(getattr(chunker, "in_utterance", False))
            st["rms"], st["floor"] = getattr(chunker, "last_rms", 0.0), getattr(chunker, "noise_floor", 0.0)
            if not self._current(identity, epoch):
                return
            for u in utts:
                if u.text and self._current(identity, epoch):
                    st["utterances"] += 1
                    self._queue.put_nowait((identity, epoch, Segment(next_id(), identity, u.text,
                                                round(u.t_start, 3), round(u.t_end, 3))))

        async def run(fn, *args):
            async with lock:
                before = getattr(chunker, "transcribe_count", 0)
                utts = await loop.run_in_executor(None, fn, *args)
            await emit(utts, getattr(chunker, "transcribe_count", 0) != before)

        async def watchdog():
            # A muted or stalled mic sends no silence, so the VAD would wait forever. Close the utterance.
            while True:
                await asyncio.sleep(0.25)
                if (getattr(chunker, "in_utterance", False) and self._current(identity, epoch)
                        and time.monotonic() - st["last_frame"] > IDLE_FLUSH_S):
                    await run(chunker.flush)

        pending = bytearray()
        guard = asyncio.create_task(watchdog())
        try:
            async for ev in stream:
                if not self._current(identity, epoch):
                    break
                frame = ev.frame
                rate, chans = getattr(frame, "sample_rate", SR), getattr(frame, "num_channels", 1)
                pcm = bytes(frame.data)
                if rate != SR or chans != 1:
                    pcm = to_mono16k(pcm, rate, chans)
                st["frames"] += 1
                st["last_frame"] = time.monotonic()
                st["rate"], st["channels"] = rate, chans
                pending += pcm
                if len(pending) >= BATCH_BYTES:
                    batch, pending = bytes(pending), bytearray()
                    await run(chunker.feed, batch)
            if self._current(identity, epoch):
                if pending:
                    await run(chunker.feed, bytes(pending))
                await run(chunker.flush)
        finally:
            guard.cancel()
            if hasattr(stream, "aclose"):
                await stream.aclose()

    def _attach(self, room, rtc, start: float) -> None:
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

        @room.on("reconnected")
        def on_reconnected(*_):
            # After a transport resume, re-assert the (unchanged) opt-in subscriptions.
            for participant in list(room.remote_participants.values()):
                if self._consent.get(participant.identity, False):
                    try:
                        self._set_participant_subscription(participant, True)
                    except Exception:  # noqa: BLE001
                        pass

        @room.on("disconnected")
        def on_disc(*_):
            if self._stopping:
                self._closed = True
                for identity in list(self._consent):
                    self._consent[identity] = False
            else:
                # Unexpected loss (server restart, network): stop all capture now, keep each
                # person's own opt-in, and let segments() rejoin and re-subscribe only them.
                self.state = "reconnecting"
            for identity in list(self._consent):
                self._epoch[identity] = self._epoch.get(identity, 0) + 1
            for task in self._tasks.values():
                task.cancel()
            self._queue.put_nowait(None)

    async def segments(self) -> AsyncIterator[Segment]:
        try:
            from livekit import rtc  # lazy
        except ImportError as e:
            self.state, self.error = "failed", "livekit sdk missing"
            raise RuntimeError("livekit not installed: pip install -r requirements-ingest.txt") from e
        self._stopping = False
        if self._transcribe is None:
            self.state = "loading_model"
            try:
                self._transcribe = await asyncio.get_running_loop().run_in_executor(None, shared_whisper, self.model)
            except Exception as e:  # noqa: BLE001
                self.state, self.error = "failed", f"stt: {e}"[:300]
                raise
        start = time.monotonic()
        room = None
        attempt = 0
        try:
            while True:
                room = rtc.Room()
                self._room = room
                self._closed = False
                self._attach(room, rtc, start)
                self.state = "connecting" if attempt == 0 else "reconnecting"
                try:
                    await room.connect(self.url, self._token(), options=rtc.RoomOptions(auto_subscribe=False))
                except Exception as e:  # noqa: BLE001
                    self.error = f"connect: {type(e).__name__}"
                    print(f"[livekit] connect failed ({type(e).__name__}); retrying", flush=True)
                    self._room = None
                    await asyncio.sleep(RECONNECT_BACKOFF_S[min(attempt, len(RECONNECT_BACKOFF_S) - 1)])
                    attempt += 1
                    continue
                attempt, self.error, self.state = 0, "", "connected"
                self._queue = asyncio.Queue()
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
                if self._closed:
                    return
                # Lost the room: drop the dead one, wait, rejoin.
                self._room = None
                for t in list(self._tasks.values()):
                    t.cancel()
                self._tasks.clear()
                try:
                    await room.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(RECONNECT_BACKOFF_S[0])
        finally:
            self._stopping = True
            self._closed = True
            if self.state != "failed":
                self.state = "idle"
            for identity in list(self._consent):
                self._consent[identity] = False
                self._epoch[identity] = self._epoch.get(identity, 0) + 1
            for t in list(self._tasks.values()):
                t.cancel()
            self._tasks.clear()
            self._stats.clear()
            self._queue = asyncio.Queue()
            self._room = None
            if room is not None:
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
