"""SegmentSource protocol: anything that yields Segments asynchronously."""
from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from otr.types import Segment


@runtime_checkable
class SegmentSource(Protocol):
    def segments(self) -> AsyncIterator[Segment]: ...


async def collect(source: SegmentSource, limit: int | None = None) -> list[Segment]:
    out: list[Segment] = []
    async for seg in source.segments():
        out.append(seg)
        if limit is not None and len(out) >= limit:
            break
    return out
