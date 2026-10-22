"""AudioFileSource with synthetic WAVs and a fake transcriber (no Whisper, no downloads)."""
import asyncio
import json
import wave

import numpy as np
import pytest

from otr.ingest.audio_file_source import AudioFileSource, read_audio_16k, resample_mono16k
from otr.ingest.base import SegmentSource, collect
from otr.ingest.diarize import Turn

SR = 16000


def tone(dur, freq=300.0, amp=0.5):
    t = np.arange(int(dur * SR)) / SR
    return amp * np.sin(2 * np.pi * freq * t)


def track(parts, total):
    """parts: [(start_s, dur_s)] of a loud tone inside `total` seconds of silence."""
    x = np.zeros(int(total * SR))
    for s, d in parts:
        x[int(s * SR):int(s * SR) + int(d * SR)] = tone(d)
    return x


def write_wav(path, x, sr=SR, ch=1):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    if ch > 1:
        pcm = np.repeat(pcm[:, None], ch, axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def fake_transcribe(audio):
    return f"words{len(audio) // 1600}"


def src(paths, **kw):
    kw.setdefault("transcribe", fake_transcribe)
    return AudioFileSource(paths, **kw)


def run(coro):
    return asyncio.run(coro)


def test_is_segment_source_and_speaker_from_stem(tmp_path):
    write_wav(tmp_path / "alice.wav", track([(0.5, 1.0)], 3))
    s = src([tmp_path / "alice.wav"], turns=[Turn("alice", 0, 3)])
    assert isinstance(s, SegmentSource)
    segs = run(collect(s))
    assert [x.speaker for x in segs] == ["alice"] and segs[0].id == "a0001"
    assert 0.4 < segs[0].t_start < 0.7 and 1.4 < segs[0].t_end < 1.8


def test_per_speaker_files_merge_in_time_order(tmp_path):
    write_wav(tmp_path / "alice.wav", track([(0.2, 1.0), (6.0, 1.0)], 8))
    write_wav(tmp_path / "bob.wav", track([(3.0, 1.0)], 8))
    segs = run(collect(src([tmp_path])))
    assert [s.speaker for s in segs] == ["alice", "bob", "alice"]
    ends = [s.t_end for s in segs]
    assert ends == sorted(ends)


def test_mixed_named_file_in_folder_is_skipped(tmp_path):
    write_wav(tmp_path / "alice.wav", track([(0.2, 1.0)], 3))
    write_wav(tmp_path / "bob.wav", track([(1.8, 1.0)], 3))
    write_wav(tmp_path / "mixed.wav", track([(0.2, 1.0), (1.8, 1.0)], 3))
    assert sorted(s.speaker for s in run(collect(src([tmp_path])))) == ["alice", "bob"]


def test_offsets_from_arg_sidecar_and_filename(tmp_path):
    for n in ("alice", "bob@10", "carol"):
        write_wav(tmp_path / f"{n}.wav", track([(0.2, 1.0)], 2))
    (tmp_path / "offsets.json").write_text(json.dumps({"carol": 5.0}))
    segs = run(collect(src([tmp_path], offsets={"alice": 20.0})))
    by = {s.speaker: s for s in segs}
    assert 20.1 < by["alice"].t_start < 20.5      # argument
    assert 10.1 < by["bob"].t_start < 10.5        # file name; speaker is 'bob', not 'bob@10'
    assert 5.1 < by["carol"].t_start < 5.5        # sidecar json
    assert [s.speaker for s in segs] == ["carol", "bob", "alice"]


def test_mixed_file_with_turn_json(tmp_path):
    write_wav(tmp_path / "m.wav", track([(0.5, 1.0), (3.0, 1.5)], 6))
    tj = tmp_path / "turns.json"
    tj.write_text(json.dumps([{"speaker": "Ann", "start": 0.0, "end": 2.0},
                              {"speaker": "Ben", "start": 2.5, "end": 5.0}]))
    segs = run(collect(src([tmp_path / "m.wav"], turns=tj)))
    assert [s.speaker for s in segs] == ["Ann", "Ben"]
    assert segs[1].t_start > 2.5


def test_mixed_file_without_turns_uses_diarizer_labels(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    write_wav(tmp_path / "m.wav", track([(0.5, 1.0), (3.0, 1.0)], 5))
    segs = run(collect(src([tmp_path / "m.wav"])))
    assert [s.speaker for s in segs] == ["SPEAKER_00", "SPEAKER_01"]


def test_turns_with_multiple_files_rejected(tmp_path):
    write_wav(tmp_path / "a.wav", track([(0, 1)], 2))
    write_wav(tmp_path / "b.wav", track([(0, 1)], 2))
    with pytest.raises(ValueError):
        src([tmp_path / "a.wav", tmp_path / "b.wav"], turns=[Turn("x", 0, 1)])


def test_pacing_real_time_speed_and_unpaced(tmp_path):
    write_wav(tmp_path / "alice.wav", track([(0.5, 1.0), (4.0, 1.0)], 7))
    waits = []

    async def fake_sleep(s):
        waits.append(s)
    segs = run(collect(src([tmp_path / "alice.wav"], speed=1.0, sleep=fake_sleep)))
    assert len(waits) == 2 and sum(waits) == pytest.approx(segs[-1].t_end, abs=1e-6)
    waits.clear()
    run(collect(src([tmp_path / "alice.wav"], speed=4.0, sleep=fake_sleep)))
    assert sum(waits) == pytest.approx(segs[-1].t_end / 4, abs=1e-6)
    waits.clear()
    run(collect(src([tmp_path / "alice.wav"], speed=0, sleep=fake_sleep)))
    assert waits == []


def test_clone_shares_transcription(tmp_path):
    write_wav(tmp_path / "alice.wav", track([(0.5, 1.0)], 3))
    calls = []
    s = src([tmp_path / "alice.wav"], transcribe=lambda a: calls.append(1) or "hi")
    s.transcribe_all()
    n = len(calls)
    assert len(run(collect(s.clone(speed=0)))) == 1 and len(calls) == n


def test_silence_only_track_yields_nothing(tmp_path):
    write_wav(tmp_path / "quiet.wav", np.zeros(SR * 3))
    assert run(collect(src([tmp_path / "quiet.wav"], turns=[Turn("quiet", 0, 3)]))) == []


def test_resample_and_stereo_read(tmp_path):
    write_wav(tmp_path / "s48.wav", 0.3 * np.sin(np.arange(48000) / 20.0), sr=48000, ch=2)
    assert abs(len(read_audio_16k(tmp_path / "s48.wav")) // 2 - SR) < 4
    assert abs(len(resample_mono16k(np.zeros(44100), 44100)) - SR) <= 1


def test_missing_and_empty_inputs(tmp_path):
    with pytest.raises(FileNotFoundError):
        src([tmp_path / "nope.wav"])
    with pytest.raises(ValueError):
        src([tmp_path])
