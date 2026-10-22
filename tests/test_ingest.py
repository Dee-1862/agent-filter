import asyncio
import json
import struct
import sys
import types

import pytest

from otr.ingest import ReplaySource, parse_script, load_jsonl, collect
from otr.ingest.stt import UtteranceChunker, SR


def test_parse_script():
    segs = parse_script("# c\nAlice: Hello there team\n\nBob Smith: Off the record, salary talk\ncontinued line\nAlice: ok")
    assert [s.speaker for s in segs] == ["Alice", "Bob Smith", "Bob Smith", "Alice"]
    assert segs[1].text == "Off the record, salary talk"
    assert all(a.t_end <= b.t_start for a, b in zip(segs, segs[1:]))
    assert segs[0].id != segs[1].id


def test_jsonl_and_replay(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text(json.dumps({"id": "x1", "speaker": "A", "text": "hi", "t_start": 0, "t_end": 1}) + "\n"
                 + json.dumps({"speaker": "B", "text": "yo", "t_start": 1, "t_end": 2}) + "\n")
    assert [s.id for s in load_jsonl(p)] == ["x1", "s0002"]
    out = asyncio.run(collect(ReplaySource.from_file(p)))
    assert [s.speaker for s in out] == ["A", "B"]


def test_script_file_and_pacing(tmp_path):
    p = tmp_path / "m.txt"
    p.write_text("A: one\nB: two\n")
    import time
    t = time.monotonic()
    out = asyncio.run(collect(ReplaySource.from_file(p, speed=100)))
    assert len(out) == 2 and time.monotonic() - t < 1


def test_chunker_with_fake_transcriber():
    loud = struct.pack("<h", 8000) * (SR // 10)
    quiet = b"\x00\x00" * (SR // 10)
    calls = []

    def fake(audio):
        calls.append(1)
        return "hello world"

    ch = UtteranceChunker(fake, to_audio=lambda b: b)
    out = ch.feed(loud * 5 + quiet * 10)
    assert len(out) == 1 and out[0].text == "hello world"
    assert 0 <= out[0].t_start < out[0].t_end <= 1.0
    assert ch.feed(quiet * 5) == []


def test_modules_import_without_sdks():
    import otr.ingest.livekit_source, otr.ingest.diarize, otr.ingest.mint_token  # noqa
    from otr.ingest.diarize import energy_turns
    loud = struct.pack("<h", 8000) * SR
    quiet = b"\x00\x00" * SR
    turns = energy_turns(loud + quiet + loud)
    assert [t.speaker for t in turns] == ["SPEAKER_00", "SPEAKER_01"]


def test_livekit_consent_subscribes_only_opted_in_identity(monkeypatch):
    from otr.ingest.livekit_source import LiveKitSource
    from otr.types import Segment

    class TrackKind:
        KIND_AUDIO = "audio"
        KIND_VIDEO = "video"

    class RoomOptions:
        def __init__(self, auto_subscribe=True):
            self.auto_subscribe = auto_subscribe

    class Publication:
        kind = TrackKind.KIND_AUDIO
        sid = "mic"

        def __init__(self):
            self.calls = []

        def set_subscribed(self, value):
            self.calls.append(value)

    class Participant:
        def __init__(self, identity):
            self.identity = identity
            self.track_publications = {"mic": Publication()}

    class Room:
        latest = None

        def __init__(self):
            Room.latest = self
            self.handlers = {}
            self.remote_participants = {name: Participant(name) for name in ("alice", "bob")}
            self.connected = asyncio.Event()
            self.options = None

        def on(self, name):
            def register(callback):
                self.handlers[name] = callback
                return callback
            return register

        async def connect(self, url, token, options):
            self.options = options
            self.connected.set()

        async def disconnect(self):
            self.handlers["disconnected"]()

    fake_rtc = types.SimpleNamespace(Room=Room, RoomOptions=RoomOptions, TrackKind=TrackKind)
    monkeypatch.setitem(sys.modules, "livekit", types.SimpleNamespace(rtc=fake_rtc))
    departed = []
    src = LiveKitSource(transcribe=lambda audio: "", on_participant_left=departed.append)
    monkeypatch.setattr(src, "_token", lambda: "local-token")

    async def scenario():
        stream = src.segments()
        next_segment = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        room = Room.latest
        await room.connected.wait()
        alice = room.remote_participants["alice"]
        bob = room.remote_participants["bob"]
        assert room.options.auto_subscribe is False
        assert alice.track_publications["mic"].calls == []
        assert bob.track_publications["mic"].calls == []
        assert src.consent_snapshot() == {"alice": False, "bob": False}
        rogue = Publication()
        room.handlers["track_published"](rogue, bob)
        assert rogue.calls == [False]
        room.handlers["track_subscribed"](types.SimpleNamespace(kind=TrackKind.KIND_AUDIO), rogue, bob)
        assert rogue.calls == [False, False]
        assert src._tasks == {}

        src.set_consent("alice", True)
        assert alice.track_publications["mic"].calls == [True]
        assert bob.track_publications["mic"].calls == []
        epoch = src._epoch["alice"]
        src._queue.put_nowait(("alice", epoch, Segment("a", "alice", "before stop", 0, 1)))
        src.set_consent("alice", False)
        assert alice.track_publications["mic"].calls[-1] is False
        assert src._queue.empty()
        # A transcription already running in an executor may finish after OFF.
        src._queue.put_nowait(("alice", epoch, Segment("late", "alice", "stale", 1, 2)))
        await asyncio.sleep(0)
        assert not next_segment.done()
        src.set_consent("bob", True)
        bob_epoch = src._epoch["bob"]
        src._queue.put_nowait(("bob", bob_epoch, Segment("b", "bob", "allowed", 2, 3)))
        assert (await asyncio.wait_for(next_segment, 1)).speaker == "bob"

        room.remote_participants.pop("bob")
        room.handlers["participant_disconnected"](bob)
        assert src.consent_snapshot()["bob"] is False
        assert departed == ["bob"]
        await stream.aclose()

    asyncio.run(scenario())


def test_livekit_consent_preconnect_and_identity_validation():
    from otr.ingest.livekit_source import LiveKitSource

    src = LiveKitSource(transcribe=lambda audio: "")
    with pytest.raises(ValueError):
        src.set_consent("", True)
    with pytest.raises(ValueError):
        src.set_consent("otr-bot", True)
    src.set_consent("alice", True)
    assert src.consent_snapshot() == {"alice": True}
    src.set_consent("alice", False)
    assert src.consent_snapshot() == {"alice": False}


def test_whisper_loads_only_local_weights(tmp_path, monkeypatch):
    import otr.ingest.stt as stt
    from otr.ingest.stt import load_whisper

    model_dir = tmp_path / "whisper"
    model_dir.mkdir()
    model_dir.joinpath("model.bin").write_bytes(b"fake")
    calls = []

    class FakeWhisperModel:
        def __init__(self, path, **options):
            calls.append((path, options))

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisperModel))
    monkeypatch.setenv("OTR_WHISPER_MODEL_DIR", str(model_dir))
    load_whisper()
    assert calls == [(str(model_dir), {"device": "cpu", "compute_type": "int8"})]
    monkeypatch.setenv("OTR_WHISPER_MODEL_DIR", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="Local faster-whisper weights not found"):
        load_whisper()
    assert len(calls) == 1

    monkeypatch.delenv("OTR_WHISPER_MODEL_DIR")
    monkeypatch.setattr(stt, "__file__", str(tmp_path / "otr" / "ingest" / "stt.py"))
    snapshot = tmp_path / "models" / "faster-whisper" / "models--Systran--faster-whisper-base.en" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    snapshot.joinpath("model.bin").write_bytes(b"fake")
    load_whisper("base.en")
    assert calls[-1][0] == str(snapshot)


def test_livekit_waits_for_utterance_close_before_emitting(monkeypatch):
    import otr.ingest.livekit_source as livekit_source
    from otr.ingest.stt import UtteranceChunker

    paused = asyncio.Event()
    release = asyncio.Event()
    used_partial_every = []
    loud = struct.pack("<h", 8000) * (SR * 3 // 100)
    quiet = b"\x00\x00" * (SR * 3 // 100)

    def chunker_factory(transcribe, *, t0, partial_every):
        used_partial_every.append(partial_every)
        return UtteranceChunker(transcribe, t0=t0, partial_every=partial_every,
                                to_audio=lambda pcm: pcm)

    class AudioStream:
        def __init__(self, track, **kwargs):
            pass

        async def __aiter__(self):
            for _ in range(70):  # 2.1 s speech, beyond the usual partial interval
                yield types.SimpleNamespace(frame=types.SimpleNamespace(data=loud))
            paused.set()
            await release.wait()
            for _ in range(24):  # silence closes the utterance
                yield types.SimpleNamespace(frame=types.SimpleNamespace(data=quiet))

        async def aclose(self):
            pass

    monkeypatch.setattr(livekit_source, "UtteranceChunker", chunker_factory)
    monkeypatch.setitem(sys.modules, "livekit", types.SimpleNamespace(rtc=types.SimpleNamespace(AudioStream=AudioStream)))
    src = livekit_source.LiveKitSource(transcribe=lambda audio: "salary 12345")
    src.set_consent("alice", True)

    async def scenario():
        task = asyncio.create_task(src._consume(object(), "alice", src._epoch["alice"], 0))
        await paused.wait()
        await asyncio.sleep(0)
        assert src._queue.empty()  # no partial prefix can escape to policy/UI
        release.set()
        await task
        identity, _, segment = src._queue.get_nowait()
        assert identity == "alice" and segment.text == "salary 12345"

    asyncio.run(scenario())
    assert used_partial_every == [float("inf")]
