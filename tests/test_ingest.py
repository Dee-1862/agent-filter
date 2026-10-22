import asyncio
import json
import struct

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
