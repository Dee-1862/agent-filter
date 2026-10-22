"""Speaker labelling for MIXED single-channel audio (e.g. a Zoom/Meet recording).

Prefer LiveKit (one track per participant) whenever possible; this is a fallback.
Labels are SPEAKER_00, SPEAKER_01, ...
"""
from __future__ import annotations

import array
import math
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Turn:
    speaker: str
    t_start: float
    t_end: float


def diarize_pyannote(wav_path: str, hf_token: Optional[str] = None,
                     model: str = "pyannote/speaker-diarization-3.1") -> list[Turn]:
    """Real diarization. Needs `pip install pyannote.audio`, a HuggingFace token
    (HF_TOKEN env or arg) and acceptance of the model's terms on huggingface.co.
    Untested here."""
    try:
        from pyannote.audio import Pipeline
    except ImportError as e:
        raise RuntimeError("pyannote.audio is not installed (pip install pyannote.audio). "
                           "Use energy_turns() for a crude placeholder, or use LiveKit.") from e
    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("pyannote needs a HuggingFace token: set HF_TOKEN and accept the "
                           f"terms for {model} on huggingface.co.")
    pipe = Pipeline.from_pretrained(model, use_auth_token=token)
    if pipe is None:
        raise RuntimeError(f"Could not load {model}; check the token and that you accepted its terms.")
    diar = pipe(wav_path)
    labels: dict[str, str] = {}
    out = []
    for seg, _, spk in diar.itertracks(yield_label=True):
        lab = labels.setdefault(spk, f"SPEAKER_{len(labels):02d}")
        out.append(Turn(lab, float(seg.start), float(seg.end)))
    return out


def energy_turns(pcm16: bytes, sr: int = 16000, frame_ms: int = 30, pause_ms: int = 600,
                 energy_thresh: float = 500.0, alternate: bool = True, n_speakers: int = 2) -> list[Turn]:
    """PLACEHOLDER, NOT real diarization. Splits on pauses >= pause_ms and
    (if `alternate`) assigns speakers round-robin, which is only right for a
    strictly turn-taking two-person conversation. No voice features are used.
    """
    step = sr * frame_ms // 1000 * 2
    turns: list[Turn] = []
    cur_start: Optional[float] = None
    last_voiced = 0.0
    for i in range(0, len(pcm16) - step + 1, step):
        a = array.array("h", pcm16[i:i + step])
        rms = math.sqrt(sum(x * x for x in a) / len(a))
        t = i / 2 / sr
        if rms >= energy_thresh:
            if cur_start is None:
                cur_start = t
            last_voiced = t + frame_ms / 1000
        elif cur_start is not None and (t - last_voiced) * 1000 >= pause_ms:
            turns.append((cur_start, last_voiced))
            cur_start = None
    if cur_start is not None:
        turns.append((cur_start, last_voiced))
    return [Turn(f"SPEAKER_{(k % n_speakers if alternate else 0):02d}", s, e) for k, (s, e) in enumerate(turns)]
