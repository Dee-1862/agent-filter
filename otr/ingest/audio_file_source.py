"""Audio files -> Segments (SegmentSource), the offline twin of LiveKitSource.

Two input shapes:

* per-speaker tracks: a folder or a list of audio files (``alice.wav bob.wav``). The
  speaker is the file stem, exactly like a LiveKit participant identity. Each track can
  start at an offset (seconds) taken from, in order of priority: the ``offsets`` argument,
  ``offsets.json`` next to the files (``{"alice": 0.0, "bob": 3.2}``), or the file name
  (``bob@3.2.wav``). Segments of all tracks are merged by end time.
* one mixed file: optional speaker turns (``[{"speaker","start","end"}]`` JSON or a list of
  ``Turn``); without them ``otr.ingest.diarize`` is used (pyannote if installed and HF_TOKEN
  is set, else the energy-based placeholder labelled SPEAKER_00, SPEAKER_01 ...).

STT is otr.ingest.stt (faster-whisper CPU int8 + UtteranceChunker), loaded lazily on first
use. Audio is read as 16-bit PCM WAV with ``wave`` + numpy and resampled to 16 kHz mono in
pure numpy; other formats (flac/ogg/float or 24-bit wav) work if ``soundfile`` is installed.
No ffmpeg needed.

Pacing: ``speed=0`` emits as fast as possible, ``1`` plays in real time (a segment is
emitted when its utterance ended on the audio clock), ``4`` is four times faster.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import wave
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, Iterable, Optional, Sequence

from otr.types import Segment
from .diarize import Turn
from .stt import SR, UtteranceChunker

AUDIO_EXTS = {".wav", ".flac", ".ogg", ".opus", ".mp3"}
DEFAULT_MODEL = "base.en"
_OFFSET_NAME = re.compile(r"^(?P<name>.+?)@(?P<off>\d+(?:\.\d+)?)$")


def _log(msg: str) -> None:
    print(f"[audio] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- audio io
def resample_mono16k(x, sr: int):
    """float32 mono array at `sr` -> float32 at 16 kHz (box low-pass + linear interpolation)."""
    import numpy as np
    x = np.asarray(x, dtype="float32")
    if sr == SR or x.size == 0:
        return x
    if sr > SR:
        k = max(1, int(round(sr / SR)))
        if sr % SR == 0 and k > 1:
            n = x.size // k * k
            return x[:n].reshape(-1, k).mean(axis=1).astype("float32")
        if k > 1:  # crude anti-alias before interpolating
            kern = np.ones(k, dtype="float32") / k
            x = np.convolve(x, kern, mode="same")
    n_out = int(round(x.size * SR / sr))
    t_out = np.arange(n_out) * (sr / SR)
    return np.interp(t_out, np.arange(x.size), x).astype("float32")


def _read_wave(path: Path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        ch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        a = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    elif width == 1:
        a = (np.frombuffer(raw, dtype="u1").astype("float32") - 128.0) / 128.0
    elif width == 3:
        b = np.frombuffer(raw, dtype="u1").reshape(-1, 3)
        v = (b[:, 0].astype("int32") | (b[:, 1].astype("int32") << 8) | (b[:, 2].astype("int32") << 16))
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        a = v.astype("float32") / float(1 << 23)
    elif width == 4:
        a = np.frombuffer(raw, dtype="<i4").astype("float32") / float(1 << 31)
    else:
        raise ValueError(f"unsupported WAV sample width {width} in {path}")
    if ch > 1:
        a = a[: a.size // ch * ch].reshape(-1, ch).mean(axis=1)
    return a, sr


def _read_soundfile(path: Path):
    try:
        import soundfile as sf
    except ImportError as e:
        raise RuntimeError(f"cannot read {path.name}: only 8/16/24/32-bit PCM .wav works without "
                           "the optional 'soundfile' package (pip install soundfile) "
                           "or convert it: ffmpeg -i in.mp3 -ar 16000 -ac 1 out.wav") from e
    a, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return a.mean(axis=1), sr


def read_audio_16k(path) -> bytes:
    """Any supported file -> 16 kHz mono int16 PCM bytes."""
    import numpy as np
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"audio file not found: {p}")
    if p.suffix.lower() == ".wav":
        try:
            a, sr = _read_wave(p)
        except (wave.Error, EOFError):  # float / extensible WAV
            a, sr = _read_soundfile(p)
    else:
        a, sr = _read_soundfile(p)
    a = resample_mono16k(a, sr)
    return (np.clip(a, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


# ---------------------------------------------------------------- inputs
def _split_offset(stem: str) -> tuple[str, Optional[float]]:
    m = _OFFSET_NAME.match(stem)
    return (m.group("name"), float(m.group("off"))) if m else (stem, None)


def expand_inputs(paths: Sequence) -> list[Path]:
    """Folders -> their audio files (sorted, a lone-extra 'mixed.*' mixdown skipped); files pass through."""
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files = sorted(f for f in p.iterdir() if f.suffix.lower() in AUDIO_EXTS)
            if len(files) > 1:  # a mixdown next to the tracks would double every line
                files = [f for f in files if f.stem.lower() != "mixed"]
            out += files
        else:
            out.append(p)
    return out


def load_turns(path) -> list[Turn]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("turns", [])
    return [Turn(str(d["speaker"]), float(d["start"]), float(d["end"])) for d in data]


# ---------------------------------------------------------------- source
class AudioFileSource:
    """SegmentSource over audio files. See module docstring.

    transcribe: ``fn(float32 audio) -> str``; default loads faster-whisper lazily.
    sleep: injectable awaitable sleep (tests).
    """

    def __init__(self, paths: Sequence, *, turns: "Sequence[Turn] | str | os.PathLike | None" = None,
                 offsets: Optional[dict] = None, speed: float = 0.0, model: Optional[str] = None,
                 transcribe: Optional[Callable[[object], str]] = None, energy_thresh: float = 500.0,
                 silence_ms: int = 700, diarize: Optional[Callable[[bytes], list]] = None,
                 sleep: Callable[[float], Awaitable] = asyncio.sleep):
        self.files = expand_inputs(paths)
        if not self.files:
            raise ValueError("no audio files given (expected .wav files or a folder containing them)")
        missing = [str(f) for f in self.files if not f.is_file()]
        if missing:
            raise FileNotFoundError("audio file not found: " + ", ".join(missing))
        self.mixed = len(self.files) == 1
        if turns is not None and not self.mixed:
            raise ValueError("speaker turns only apply to a single mixed audio file")
        self.turns = load_turns(turns) if isinstance(turns, (str, os.PathLike)) else (
            list(turns) if turns is not None else None)
        self.speed = speed
        self.model = model or os.environ.get("OTR_WHISPER_MODEL") or DEFAULT_MODEL
        self._transcribe = transcribe
        self.energy_thresh, self.silence_ms = energy_thresh, silence_ms
        self._diarize = diarize
        self._sleep = sleep
        self._offsets = self._resolve_offsets(offsets)
        self._segments: Optional[list[Segment]] = None

    # -- construction helpers
    @classmethod
    def from_paths(cls, paths: Sequence, turns=None, **kw) -> "AudioFileSource":
        return cls(paths, turns=turns, **kw)

    def clone(self, speed: Optional[float] = None) -> "AudioFileSource":
        """Fresh source over the same (already transcribed) segments; used by restart."""
        c = object.__new__(AudioFileSource)
        c.__dict__.update(self.__dict__)
        if speed is not None:
            c.speed = speed
        return c

    def _resolve_offsets(self, given: Optional[dict]) -> dict[str, float]:
        offs: dict[str, float] = {}
        if self.mixed:
            return offs
        side = self.files[0].parent / "offsets.json"
        if side.is_file():
            try:
                offs.update({str(k): float(v) for k, v in json.loads(side.read_text("utf-8")).items()})
            except (ValueError, TypeError, AttributeError) as e:
                raise ValueError(f"bad offsets.json ({side}): {e}") from e
        for f in self.files:
            name, off = _split_offset(f.stem)
            if off is not None:
                offs[name] = off
        if given:
            offs.update({str(k): float(v) for k, v in given.items()})
        return offs

    def speakers(self) -> list[str]:
        if self.mixed:
            return sorted({t.speaker for t in self.turns}) if self.turns else []
        return [_split_offset(f.stem)[0] for f in self.files]

    # -- model
    def load_model(self) -> None:
        """Load Whisper now (otherwise lazily on first use)."""
        if self._transcribe is not None:
            return
        from .stt import load_whisper
        resolve_whisper_dir(self.model)  # may set OTR_WHISPER_MODEL_DIR from the HF cache
        _log(f"loading faster-whisper '{self.model}' (CPU int8)")
        self._transcribe = load_whisper(self.model)

    # -- transcription
    def _chunk(self, pcm: bytes, speaker: str, t0: float) -> list[tuple[float, float, str, str]]:
        ch = UtteranceChunker(self._transcribe, energy_thresh=self.energy_thresh,
                              silence_ms=self.silence_ms, partial_every=1e9, t0=t0)
        out = []
        step = SR * 2  # 1 s blocks
        utts = []
        for i in range(0, len(pcm), step):
            utts += ch.feed(pcm[i:i + step])
        utts += ch.feed(b"\x00\x00" * int(SR * (self.silence_ms / 1000 + 0.1)))  # close the last utterance
        utts += ch.flush()
        for u in utts:
            if u.text.strip():
                out.append((u.t_start, u.t_end, speaker, u.text.strip()))
        return out

    def _tracks_raw(self) -> list[tuple[float, float, str, str]]:
        raw: list[tuple[float, float, str, str]] = []
        for f in self.files:
            name, _ = _split_offset(f.stem)
            _log(f"transcribing {f.name} (speaker '{name}')")
            raw += self._chunk(read_audio_16k(f), name, self._offsets.get(name, 0.0))
        return raw

    def _mixed_raw(self) -> list[tuple[float, float, str, str]]:
        import numpy as np
        pcm = read_audio_16k(self.files[0])
        turns = self.turns
        if turns is None:
            turns = self._auto_turns(pcm)
        raw: list[tuple[float, float, str, str]] = []
        for t in sorted(turns, key=lambda t: t.t_start):
            a, b = int(max(0.0, t.t_start) * SR) * 2, int(max(0.0, t.t_end) * SR) * 2
            chunk = pcm[a:b]
            if len(chunk) < SR // 5 * 2:
                continue
            raw += self._chunk(chunk, t.speaker, max(0.0, t.t_start))
        _ = np  # numpy is a hard requirement of this module; keep import error early
        return raw

    def _auto_turns(self, pcm: bytes) -> list[Turn]:
        if self._diarize is not None:
            return self._diarize(pcm)
        from . import diarize as d
        if os.environ.get("HF_TOKEN"):
            try:
                _log("diarizing with pyannote")
                return d.diarize_pyannote(str(self.files[0]))
            except Exception as e:
                _log(f"pyannote unavailable ({e}); using the energy-based placeholder")
        else:
            _log("no turn JSON and no HF_TOKEN: using the energy-based placeholder diarizer "
                 "(round-robin SPEAKER_00/01, NOT real speaker recognition)")
        return d.energy_turns(pcm)

    def transcribe_all(self) -> list[Segment]:
        """Blocking: transcribe every track and return merged Segments (cached)."""
        if self._segments is not None:
            return self._segments
        self.load_model()
        raw = self._mixed_raw() if self.mixed else self._tracks_raw()
        raw.sort(key=lambda r: (r[1], r[0], r[2]))  # by end time: when the utterance was confirmed
        self._segments = [Segment(id=f"a{n:04d}", speaker=sp, text=tx,
                                  t_start=round(a, 3), t_end=round(b, 3))
                          for n, (a, b, sp, tx) in enumerate(raw, 1)]
        _log(f"{len(self._segments)} segments from {len(self.files)} file(s)")
        return self._segments

    async def segments(self) -> AsyncIterator[Segment]:
        segs = self._segments
        if segs is None:
            segs = await asyncio.to_thread(self.transcribe_all)
        clock = 0.0
        for seg in segs:
            if self.speed > 0:
                wait = (seg.t_end - clock) / self.speed
                if wait > 0:
                    await self._sleep(wait)
                clock = max(clock, seg.t_end)
            yield seg


# ---------------------------------------------------------------- whisper weights
def hf_cache_dirs() -> list[Path]:
    roots = []
    if os.environ.get("HF_HOME"):
        roots.append(Path(os.environ["HF_HOME"]) / "hub")
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    return roots


def find_whisper_dir(model: str) -> Optional[Path]:
    """Directory with model.bin for `model`, or None. Checks otr.ingest.stt's locations
    (OTR_WHISPER_MODEL_DIR, ./models/faster-whisper) and then the HuggingFace cache."""
    from .stt import _local_whisper_model
    try:
        return _local_whisper_model(model)
    except RuntimeError:
        pass
    for root in hf_cache_dirs():
        snaps = root / f"models--Systran--faster-whisper-{model}" / "snapshots"
        if snaps.is_dir():
            for s in sorted(snaps.iterdir()):
                if (s / "model.bin").is_file():
                    return s.resolve()
    return None


def resolve_whisper_dir(model: str) -> Path:
    """Like find_whisper_dir but raises a RuntimeError with the download command, and exports
    OTR_WHISPER_MODEL_DIR so otr.ingest.stt.load_whisper finds a HF-cache copy."""
    d = find_whisper_dir(model)
    if d is None:
        raise RuntimeError(
            f"Whisper model '{model}' is not on disk and OTR never downloads at runtime. "
            "One-time download (about 150 MB for base.en, 75 MB for tiny.en; slow on a slow network): "
            f"python -c \"from faster_whisper import WhisperModel; WhisperModel('{model}', device='cpu', "
            "compute_type='int8', download_root='models/faster-whisper')\"  "
            "or point OTR_WHISPER_MODEL_DIR at a folder containing model.bin")
    if not os.environ.get("OTR_WHISPER_MODEL_DIR"):
        os.environ["OTR_WHISPER_MODEL_DIR"] = str(d)
    return d


# ---------------------------------------------------------------- CLI
def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Transcribe audio files to Segments (JSONL on stdout)")
    ap.add_argument("audio", nargs="+", help="folder, per-speaker files, or one mixed file")
    ap.add_argument("--turns", help="speaker-turn JSON for a mixed file")
    ap.add_argument("--speed", type=float, default=0.0, help="0 = as fast as possible, 1 = real time")
    ap.add_argument("--model", default=None, help="faster-whisper model (default $OTR_WHISPER_MODEL or base.en)")
    a = ap.parse_args(argv)
    try:
        src = AudioFileSource(a.audio, turns=a.turns, speed=a.speed, model=a.model)

        async def run():
            async for s in src.segments():
                print(json.dumps(s.to_dict()), flush=True)
        asyncio.run(run())
    except (RuntimeError, ValueError, OSError) as e:
        print(f"[audio] {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
