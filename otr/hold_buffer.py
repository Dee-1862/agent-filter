"""Hold buffer: segments wait `hold_seconds` before commit. Clock is injected via `now`."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .types import Segment


@dataclass
class Item:
    seg: Segment
    seq: int
    arrival: float
    pending: bool = False          # awaiting confirm(); blocks release of itself and later items
    after_pending: Optional[str] = None   # id of the pending item this one queued behind


class HoldBuffer:
    def __init__(self, hold_seconds: float = 30.0):
        self.hold_seconds = hold_seconds
        self._items: list[Item] = []
        self._seq = 0

    def add(self, seg: Segment, now: float) -> Item:
        self._seq += 1
        it = Item(seg=seg, seq=self._seq, arrival=now)
        self._items.append(it)
        return it

    def items(self) -> list[Item]:
        return list(self._items)

    def get(self, segment_id: str) -> Optional[Item]:
        return next((i for i in self._items if i.seg.id == segment_id), None)

    def remove(self, segment_id: str) -> Optional[Item]:
        it = self.get(segment_id)
        if it:
            self._items.remove(it)
        return it

    def pending_items(self) -> list[Item]:
        return [i for i in self._items if i.pending]

    def release_due(self, now: float) -> list[Item]:
        """Pop items older than hold_seconds, in order. A pending item is a barrier:
        nothing at or after it is released until confirm() resolves it."""
        out = []
        for it in list(self._items):
            if it.pending:
                break
            if now - it.arrival >= self.hold_seconds:
                self._items.remove(it)
                out.append(it)
            else:
                break   # later items arrived later; keep order
        return out

    def drain(self) -> list[Item]:
        """Pop everything not pending (end of meeting)."""
        out = [i for i in self._items if not i.pending]
        self._items = [i for i in self._items if i.pending]
        return out

    def __len__(self):
        return len(self._items)
