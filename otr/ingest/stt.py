"""Streaming STT: VAD-chunked utterances through faster-whisper (optional dep).

Strategy: an adaptive energy VAD splits 16 kHz mono int16 PCM into utterances.
The VAD tracks the room noise floor (fast down, slow up) and uses hysteresis, so
it works with browser microphones that apply auto gain and noise suppression
(a fixed constant cannot). An utterance closes after `silence_ms` of quiet (or
earlier at a pause once it is long) and is transcribed once, whole. The consent
path (livekit_source) never asks for partials; the optional LocalAgreement-2
partial mode (`partial_every`) is kept for the file-based sources only.
The chunking logic is tested with an injected fake transcriber; the model path
was exercised against real audio with faster-whisper base.en (docs/LIVE_PATH.md).
"""
from __future__ import annotations

import array
import itertools
import math
import os
import threading
import time
from collections import deque
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


def stt_threads() -> int:
    """ctranslate2 CPU threads: $OTR_STT_THREADS, else 4 (measured; see docs/LIVE_PATH.md)."""
    try:
        return max(1, int(os.environ.get("OTR_STT_THREADS", "") or 4))
    except ValueError:
        return 4


def load_whisper(model: str = "base.en", cpu_threads: Optional[int] = None,
                 warmup: bool = True) -> Callable[[object], str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("faster-whisper not installed: pip install -r requirements-ingest.txt") from e
    options = {"device": "cpu", "compute_type": "int8"}
    threads = cpu_threads if cpu_threads is not None else stt_threads()
    if threads:
        options["cpu_threads"] = threads
    t_load = time.perf_counter()
    m = WhisperModel(str(_local_whisper_model(model)), **options)
    stats = {"model": model, "load_seconds": None, "rtf": None, "threads": threads}
    lock = threading.Lock()   # one decode at a time per model; a second speaker waits its turn

    def transcribe(audio_f32) -> str:
        with lock:
            t = time.perf_counter()
            segs, _ = m.transcribe(audio_f32, language="en", beam_size=1, vad_filter=False,
                                   condition_on_previous_text=False)
            text = " ".join(s.text.strip() for s in segs).strip()
            n = len(audio_f32)
            if n >= SR:   # real-time factor of the last decode (ignore tiny clips)
                stats["rtf"] = round((time.perf_counter() - t) / (n / SR), 3)
            return text
    transcribe.stats = stats

    stats["load_seconds"] = round(time.perf_counter() - t_load, 2)
    if warmup:
        try:   # first call allocates buffers; pay it at startup, not on the first sentence
            import numpy as np
            transcribe(np.zeros(SR, dtype="float32"))
            stats["rtf"] = None
        except Exception:  # noqa: BLE001 - warm-up is best effort
            pass
    return transcribe


_shared: dict[str, Callable[[object], str]] = {}
_shared_lock = threading.Lock()


def shared_whisper(model: str = "base.en") -> Callable[[object], str]:
    """One loaded, warmed model per process, shared by every meeting room."""
    with _shared_lock:
        if model not in _shared:
            _shared[model] = load_whisper(model)
        return _shared[model]


def to_mono16k(data, sample_rate: int, channels: int = 1) -> bytes:
    """Interleaved int16 PCM at any rate/channel count -> 16 kHz mono int16 bytes.

    Defensive: LiveKit's AudioStream already resamples to the requested format,
    so this only runs if a frame arrives in another format. Stateless per call
    (no filter memory across frames), which is adequate for speech recognition.
    """
    import numpy as np
    a = np.frombuffer(data, dtype=np.int16).astype("float32")
    channels = max(1, int(channels))
    if channels > 1:
        a = a[: len(a) // channels * channels].reshape(-1, channels).mean(axis=1)
    if sample_rate != SR and len(a):
        if sample_rate % SR == 0:
            k = sample_rate // SR
            a = a[: len(a) // k * k].reshape(-1, k).mean(axis=1)
        else:
            width = max(1, round(sample_rate / SR))
            if width > 1:
                a = np.convolve(a, np.ones(width, dtype="float32") / width, mode="same")
            n_new = int(len(a) * SR / sample_rate)
            a = np.interp(np.arange(n_new) / SR, np.arange(len(a)) / sample_rate, a)
    return np.clip(np.rint(a), -32768, 32767).astype(np.int16).tobytes()


def _rms(pcm: bytes) -> float:
    a = array.array("h", pcm[: len(pcm) // 2 * 2])
    if not a:
        return 0.0
    return math.sqrt(sum(x * x for x in a) / len(a))


def _to_float(pcm: bytes):
    import numpy as np  # installed with faster-whisper
    return np.frombuffer(pcm, dtype=np.int16).astype("float32") / 32768.0


class AdaptiveVAD:
    """Energy VAD with a tracked noise floor and hysteresis (RMS on the int16 scale).

    floor: seeded from the quietest of the first `warmup_frames` frames (capped at
    `seed_cap`), then falls quickly toward quieter frames and rises slowly while the
    frame is not speech. Speech must exceed `start_ratio * floor` (and `min_start`) to
    open an utterance and stay above `cont_ratio * floor` (and `min_cont`) to keep it open.
    """

    def __init__(self, *, start_ratio: float = 3.0, cont_ratio: float = 1.8, min_start: float = 200.0,
                 min_cont: float = 120.0, init_floor: float = 40.0, seed_cap: float = 800.0,
                 max_floor: float = 1500.0, warmup_frames: int = 10, tau_up_s: float = 4.0,
                 tau_down_s: float = 0.15):
        self.start_ratio, self.cont_ratio = start_ratio, cont_ratio
        self.min_start, self.min_cont = min_start, min_cont
        self.seed_cap, self.max_floor = seed_cap, max_floor
        self.warmup_frames, self.tau_up_s, self.tau_down_s = warmup_frames, tau_up_s, tau_down_s
        self.floor = init_floor
        self.frames = 0

    @property
    def start_threshold(self) -> float:
        return max(self.min_start, self.start_ratio * self.floor)

    @property
    def cont_threshold(self) -> float:
        return max(self.min_cont, self.cont_ratio * self.floor)

    def update(self, rms: float, dur: float, in_speech: bool) -> bool:
        """Classify one frame and adapt the floor. Returns True if the frame is speech."""
        self.frames += 1
        if self.frames <= self.warmup_frames:
            self.floor = min(rms, self.seed_cap) if self.frames == 1 else min(self.floor, rms, self.seed_cap)
            self.floor = max(self.floor, 1.0)
        thr = self.cont_threshold if in_speech else self.start_threshold
        voiced = rms >= thr
        if self.frames > self.warmup_frames:
            if rms < self.floor:
                self.floor += (rms - self.floor) * (1 - math.exp(-dur / self.tau_down_s))
                self.floor = max(self.floor, 1.0)
            elif not voiced:
                self.floor = min(self.max_floor,
                                 self.floor + (rms - self.floor) * (1 - math.exp(-dur / self.tau_up_s)))
        return voiced


@dataclass
class Utterance:
    text: str
    t_start: float
    t_end: float


class UtteranceChunker:
    """Feed 16 kHz mono int16 PCM bytes; get confirmed Utterances.

    `transcribe(audio)->str`; `to_audio(bytes)->audio` is injectable for tests.
    `energy_thresh=None` (default) uses the adaptive VAD; a number forces a fixed
    RMS threshold (used by tests and file sources with known levels).
    """

    def __init__(self, transcribe: Callable[[object], str], *, energy_thresh: Optional[float] = None,
                 silence_ms: int = 700, min_speech_ms: int = 300, partial_every: float = 2.0,
                 max_utt_s: float = 20.0, soft_utt_s: float = 8.0, soft_silence_ms: int = 350,
                 preroll_ms: Optional[int] = None, to_audio: Callable[[bytes], object] = _to_float,
                 t0: float = 0.0, vad: Optional[AdaptiveVAD] = None):
        self.transcribe, self.to_audio = transcribe, to_audio
        self.energy_thresh, self.silence_ms = energy_thresh, silence_ms
        self.min_speech_ms, self.partial_every, self.max_utt_s = min_speech_ms, partial_every, max_utt_s
        self.soft_utt_s, self.soft_silence_ms = soft_utt_s, soft_silence_ms
        # Lead-in audio so soft word onsets survive; off for fixed-threshold file sources (exact offsets).
        self.preroll_ms = preroll_ms if preroll_ms is not None else (240 if energy_thresh is None else 0)
        self.vad = vad or AdaptiveVAD()
        self._pos = 0.0
        self._t0 = t0
        self._buf = bytearray()
        self._pre: deque = deque()          # (bytes, dur) of recent non-speech frames
        self._pre_dur = 0.0
        self._start: Optional[float] = None
        self._silence = 0.0
        self._last_partial = 0.0
        self._prev_words: list[str] = []
        self._emitted_words = 0
        # text-free telemetry
        self.last_rms = 0.0
        self.last_transcribe_s = 0.0
        self.last_audio_s = 0.0
        self.transcribe_count = 0

    @property
    def in_utterance(self) -> bool:
        return self._start is not None

    @property
    def noise_floor(self) -> float:
        return self.vad.floor

    def _classify(self, rms: float, dur: float) -> bool:
        if self.energy_thresh is not None:
            return rms >= self.energy_thresh
        return self.vad.update(rms, dur, self._start is not None)

    def feed(self, pcm: bytes, frame_ms: int = 30) -> list[Utterance]:
        out: list[Utterance] = []
        step = SR * frame_ms // 1000 * 2
        for i in range(0, len(pcm), step):
            fr = pcm[i:i + step]
            dur = len(fr) / 2 / SR
            self.last_rms = _rms(fr)
            voiced = self._classify(self.last_rms, dur)
            if self._start is None:
                if voiced:
                    lead = self._pre_dur
                    self._start, self._silence, self._last_partial = max(0.0, self._pos - lead), 0.0, 0.0
                    self._prev_words, self._emitted_words = [], 0
                    self._buf = bytearray(b"".join(p for p, _ in self._pre)) + fr
                    self._pre.clear()
                    self._pre_dur = 0.0
                else:
                    self._pre.append((fr, dur))
                    self._pre_dur += dur
                    while self._pre and self._pre_dur - self._pre[0][1] >= self.preroll_ms / 1000:
                        self._pre_dur -= self._pre.popleft()[1]
            else:
                self._buf += fr
                self._silence = 0.0 if voiced else self._silence + dur
            self._pos += dur
            if self._start is None:
                continue
            length = self._pos - self._start
            quiet_ms = self._silence * 1000
            limit = self.soft_silence_ms if length >= self.soft_utt_s else self.silence_ms
            if quiet_ms >= limit or length >= self.max_utt_s:
                out += self._close()
            elif length - self._last_partial >= self.partial_every:
                self._last_partial = length
                out += self._partial()
        return out

    def flush(self) -> list[Utterance]:
        return self._close() if self._start is not None else []

    def discard(self) -> None:
        """Forget any open utterance without transcribing it (consent withdrawn)."""
        self._start, self._buf, self._silence = None, bytearray(), 0.0
        self._pre.clear()
        self._pre_dur = 0.0

    def _run(self, buf: bytes) -> list[str]:
        t = time.perf_counter()
        words = self.transcribe(self.to_audio(buf)).split()
        self.last_transcribe_s = time.perf_counter() - t
        self.last_audio_s = len(buf) / 2 / SR
        self.transcribe_count += 1
        return words

    def _partial(self) -> list[Utterance]:
        words = self._run(bytes(self._buf))
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
        trailing = max(0, int((self._silence - 0.2) * SR)) * 2   # keep 200 ms of tail, drop the rest
        if trailing:
            buf = buf[: len(buf) - trailing]
        self._start, self._buf, self._silence = None, bytearray(), 0.0
        if (end - start) * 1000 < self.min_speech_ms:
            return []
        words = self._run(buf)
        rest = words[self._emitted_words:]
        return [Utterance(" ".join(rest), self._t0 + start, self._t0 + end)] if rest else []


_ids = itertools.count(1)


def next_id(prefix: str = "s") -> str:
    return f"{prefix}{next(_ids):04d}"
