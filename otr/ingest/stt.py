"""Streaming STT: VAD-chunked utterances through faster-whisper (optional dep).

Strategy: energy VAD splits 16 kHz mono int16 PCM into utterances. While an
utterance is open the growing buffer is re-transcribed every `partial_every`
seconds and a LocalAgreement-2 prefix (words identical in two consecutive
passes) is emitted. On silence the whole utterance is transcribed once more and
the not-yet-emitted remainder is emitted. Text is therefore only emitted when
confirmed. Not exercised against real audio here (needs faster-whisper + model);
the chunking logic is tested with an injected fake transcriber.
"""
from __future__ import annotations

import array
import itertools
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

SR = 16000


def _local_whisper_model(model: str) -> Path:
    """Resolve weights on disk; never ask faster-whisper to fetch at runtime."""
    override = os.environ.get("OTR_WHISPER_MODEL_DIR")
    repo_model = Path(__file__).resolve().parents[2] / "models" / "faster-whisper"
    if override:
        candidates = [Path(override).expanduser()]
    else:
        snapshot_root = repo_model / f"models--Systran--faster-whisper-{model}" / "snapshots"
        snapshots = sorted(snapshot_root.iterdir()) if snapshot_root.is_dir() else []
        # Weights already on disk in the Hugging Face cache are local too: no network is used.
        hf_home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
        hf_root = hf_home / "hub" / f"models--Systran--faster-whisper-{model}" / "snapshots"
        hf_snapshots = sorted(hf_root.iterdir()) if hf_root.is_dir() else []
        candidates = [Path(model).expanduser(), repo_model, *snapshots, *hf_snapshots]
    for candidate in candidates:
        if (candidate / "model.bin").is_file():
            return candidate.resolve()
    location = override or str(repo_model)
    raise RuntimeError(f"Local faster-whisper weights not found at {location}; "
                       "set OTR_WHISPER_MODEL_DIR to a directory containing model.bin")


def load_whisper(model: str = "base.en") -> Callable[[object], str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("faster-whisper not installed: pip install -r requirements-ingest.txt") from e
    m = WhisperModel(str(_local_whisper_model(model)), device="cpu", compute_type="int8")

    def transcribe(audio_f32) -> str:
        segs, _ = m.transcribe(audio_f32, language="en", beam_size=1, vad_filter=False,
                               condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segs).strip()
    return transcribe


def _rms(pcm: bytes) -> float:
    a = array.array("h", pcm[: len(pcm) // 2 * 2])
    if not a:
        return 0.0
    return math.sqrt(sum(x * x for x in a) / len(a))


def _to_float(pcm: bytes):
    import numpy as np  # installed with faster-whisper
    return np.frombuffer(pcm, dtype=np.int16).astype("float32") / 32768.0


@dataclass
class Utterance:
    text: str
    t_start: float
    t_end: float


class UtteranceChunker:
    """Feed 16 kHz mono int16 PCM bytes; get confirmed Utterances.

    `transcribe(audio)->str`; `to_audio(bytes)->audio` is injectable for tests.
    """

    def __init__(self, transcribe: Callable[[object], str], *, energy_thresh: float = 500.0,
                 silence_ms: int = 700, min_speech_ms: int = 300, partial_every: float = 2.0,
                 max_utt_s: float = 20.0, to_audio: Callable[[bytes], object] = _to_float,
                 t0: float = 0.0):
        self.transcribe, self.to_audio = transcribe, to_audio
        self.energy_thresh, self.silence_ms = energy_thresh, silence_ms
        self.min_speech_ms, self.partial_every, self.max_utt_s = min_speech_ms, partial_every, max_utt_s
        self._pos = 0.0
        self._t0 = t0
        self._buf = bytearray()
        self._start: Optional[float] = None
        self._silence = 0.0
        self._last_partial = 0.0
        self._prev_words: list[str] = []
        self._emitted_words = 0

    def feed(self, pcm: bytes, frame_ms: int = 30) -> list[Utterance]:
        out: list[Utterance] = []
        step = SR * frame_ms // 1000 * 2
        for i in range(0, len(pcm), step):
            fr = pcm[i:i + step]
            dur = len(fr) / 2 / SR
            voiced = _rms(fr) >= self.energy_thresh
            if self._start is None:
                if voiced:
                    self._start, self._silence, self._last_partial = self._pos, 0.0, 0.0
                    self._prev_words, self._emitted_words = [], 0
                    self._buf = bytearray(fr)
            else:
                self._buf += fr
                self._silence = 0.0 if voiced else self._silence + dur
            self._pos += dur
            if self._start is None:
                continue
            length = self._pos - self._start
            if self._silence * 1000 >= self.silence_ms or length >= self.max_utt_s:
                out += self._close()
            elif length - self._last_partial >= self.partial_every:
                self._last_partial = length
                out += self._partial()
        return out

    def flush(self) -> list[Utterance]:
        return self._close() if self._start is not None else []

    def _partial(self) -> list[Utterance]:
        words = self.transcribe(self.to_audio(bytes(self._buf))).split()
        n = 0
        for a, b in zip(self._prev_words, words):
            if a != b:
                break
            n += 1
        self._prev_words = words
        if n > self._emitted_words:
            txt = " ".join(words[self._emitted_words:n])
            self._emitted_words = n
            return [Utterance(txt, self._t0 + self._start, self._t0 + self._pos)]
        return []

    def _close(self) -> list[Utterance]:
        start, end = self._start, self._pos - self._silence
        buf = bytes(self._buf)
        self._start, self._buf = None, bytearray()
        if (end - start) * 1000 < self.min_speech_ms:
            return []
        words = self.transcribe(self.to_audio(buf)).split()
        rest = words[self._emitted_words:]
        return [Utterance(" ".join(rest), self._t0 + start, self._t0 + end)] if rest else []


_ids = itertools.count(1)


def next_id(prefix: str = "s") -> str:
    return f"{prefix}{next(_ids):04d}"
