"""Dependency-free source: replay a JSONL of Segment dicts or a 'Alice: text' script."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator, Iterable

from otr.types import Segment


def load_jsonl(path) -> list[Segment]:
    segs = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d = json.loads(line)
        segs.append(Segment(id=str(d.get("id", f"s{n:04d}")), speaker=d["speaker"], text=d["text"],
                            t_start=float(d["t_start"]), t_end=float(d["t_end"])))
    return segs


def parse_script(text: str, words_per_sec: float = 2.5, gap: float = 0.5, t0: float = 0.0) -> list[Segment]:
    """'Speaker: text' per line -> Segments with synthetic timestamps.

    Blank lines and '#' comments are skipped. A line is treated as having a
    speaker when the part before the first ':' is 1-3 words and has no digits;
    otherwise it continues as the previous speaker.
    """
    segs, t, last = [], t0, "Unknown"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, rest = line.partition(":")
        name = name.strip()
        if sep and name and len(name.split()) <= 3 and not any(c.isdigit() for c in name):
            last, body = name, rest.strip()
        else:
            body = line
        if not body:
            continue
        dur = max(0.8, len(body.split()) / words_per_sec)
        segs.append(Segment(id=f"s{len(segs) + 1:04d}", speaker=last, text=body,
                            t_start=round(t, 3), t_end=round(t + dur, 3)))
        t += dur + gap
    return segs


class ReplaySource:
    """speed=0: no sleeping (tests); 1: real time; 4: 4x faster."""

    def __init__(self, segments: Iterable[Segment], speed: float = 0.0):
        self._segs, self.speed = list(segments), speed

    @classmethod
    def from_file(cls, path, speed: float = 0.0) -> "ReplaySource":
        p = Path(path)
        if p.suffix.lower() in (".jsonl", ".json"):
            return cls(load_jsonl(p), speed)
        return cls(parse_script(p.read_text(encoding="utf-8")), speed)

    async def segments(self) -> AsyncIterator[Segment]:
        clock = self._segs[0].t_start if self._segs else 0.0
        for seg in self._segs:
            if self.speed > 0:
                # a segment is only confirmed once the utterance ends
                wait = (seg.t_end - clock) / self.speed
                if wait > 0:
                    await asyncio.sleep(wait)
                clock = max(clock, seg.t_end)
            yield seg


if __name__ == "__main__":
    import sys

    async def _main():
        speed = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
        async for s in ReplaySource.from_file(sys.argv[1], speed).segments():
            print(json.dumps(s.to_dict()))
    asyncio.run(_main())
