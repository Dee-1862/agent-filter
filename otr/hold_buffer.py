"""Hold buffer: segments wait `hold_seconds` before commit. Clock is injected via `now`.

Items are kept ordered by (seg.t_start, seq) so out-of-order arrival from different
speakers still yields time-ordered release. `hold_seconds` is read live at release time.
"""
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
    tentative: bool = False        # OFF-scope utterance that may or may not be private yet; blocks release


class HoldBuffer:
    def __init__(self, hold_seconds: float = 30.0):
        self.hold_seconds = hold_seconds
        self._items: list[Item] = []
        self._seq = 0

    def add(self, seg: Segment, now: float, seq: Optional[int] = None) -> Item:
        if seq is None:
            self._seq += 1
            seq = self._seq
        else:
            self._seq = max(self._seq, seq)
        it = Item(seg=seg, seq=seq, arrival=now)
        key = (seg.t_start, seq)
        pos = len(self._items)
        while pos > 0 and (self._items[pos - 1].seg.t_start, self._items[pos - 1].seq) > key:
            pos -= 1
        self._items.insert(pos, it)
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

    def tentative_items(self) -> list[Item]:
        return [i for i in self._items if i.tentative]

    def release_due(self, now: float) -> list[Item]:
        """Pop items older than hold_seconds (read now, not at add time), in time order.
        A pending or tentative item is a barrier: nothing at or after it is released until
        confirm() / scope resolution clears it."""
        out = []
        for it in list(self._items):
            if it.pending or it.tentative:
                break
            if now - it.arrival >= self.hold_seconds:
                self._items.remove(it)
                out.append(it)
            else:
                break   # keep time order; later items wait for this one
        return out

    def drain(self) -> list[Item]:
        """Pop everything not pending/tentative (end of meeting)."""
        out = [i for i in self._items if not i.pending and not i.tentative]
        self._items = [i for i in self._items if i.pending or i.tentative]
        return out

    def __len__(self):
        return len(self._items)
