"""StreamRunner: live Segment stream -> Pipeline -> Events -> subscribers.

Design points
  * The pipeline is synchronous and may call a slow LLM. EVERY pipeline call
    (push / tick / confirm / flush / set_hold) runs in one dedicated worker thread, so
    the event loop (SSE, HTTP, the source itself) never blocks and pipeline calls
    never overlap.
  * Pipeline clock = seconds since runner start on `clock` (wall time by default).
    A segment is stamped with its ARRIVAL time, so held segments release by real time
    even if nobody is talking, and a slow push does not shift the hold window.
  * Segments are queued as they arrive (a 'segment' message goes out immediately,
    before the pipeline sees it); a single pusher task feeds the worker thread.
  * Errors in the pipeline or the source become 'error' messages; the runner keeps going.
  * Subscribers get bounded asyncio queues, pre-filled from a bounded history.
    A subscriber that falls behind loses its oldest messages (counted in `dropped`).

Messages (dicts, JSON-serialisable; persistent ones carry an increasing "seq"):
  reset | segment | events{events,notes,audit} | config | source | error | done   (persistent)
  health                                                                      (ephemeral)
"""
from __future__ import annotations

import asyncio
import collections
import concurrent.futures
import time
from typing import Any, Callable, Optional

from otr.types import Event, Segment

PERSISTENT = ("reset", "segment", "events", "config", "source", "error", "done")


class Subscription:
    def __init__(self, maxsize: int):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0
        self.closed = False

    def offer(self, msg: dict) -> None:
        while True:
            try:
                self.queue.put_nowait(msg)
                return
            except asyncio.QueueFull:
                try:
                    self.queue.get_nowait()
                    self.dropped += 1
                except asyncio.QueueEmpty:
                    return

    async def get(self) -> dict:
        return await self.queue.get()


class StreamRunner:
    def __init__(self, source=None, pipeline=None, clock: Callable[[], float] = time.monotonic,
                 tick_interval: float = 0.25, *, hold_seconds: Optional[float] = None,
                 source_name: Optional[str] = None, pipeline_kind: str = "",
                 source_factory: Optional[Callable[[], Any]] = None, reconnect: bool = False,
                 reconnect_delay: float = 2.0, history: int = 3000, queue_size: int = 2000,
                 audit_cap: int = 300, health_interval: float = 1.0, finish_margin: float = 0.5):
        self._source, self._pipe = source, pipeline
        self.clock, self.tick_interval = clock, tick_interval
        self.hold_seconds = float(hold_seconds if hold_seconds is not None
                                  else getattr(pipeline, "hold_seconds", 10.0))
        self.source_name = source_name or (type(source).__name__ if source is not None else "typed")
        self.pipeline_kind = pipeline_kind
        self._factory, self._reconnect, self._reconnect_delay = source_factory, reconnect, reconnect_delay
        self._say_n = 0
        self._queue_size, self._audit_cap = queue_size, audit_cap
        self._health_interval, self._finish_margin = health_interval, finish_margin
        self._history: collections.deque = collections.deque(maxlen=history)
        self._subs: set[Subscription] = set()
        self._seq = 0
        self._t0 = 0.0
        self._tasks: list[asyncio.Task] = []
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._lock: Optional[asyncio.Lock] = None
        self._inbox: Optional[asyncio.Queue] = None
        self._reset_stats()

    # ------------------------------------------------------------ state
    def _reset_stats(self) -> None:
        self._waiting = 0
        self._max_depth = 0
        self.pushes = self.errors = self.ticks = self.ticks_skipped = 0
        self.last_push_ms: Optional[float] = None
        self.max_push_ms = 0.0
        self.state = "ON"
        self.source_state = "none" if self._source is None else "starting"
        self.source_error = ""
        self.done = False
        self._last_arrival = 0.0
        self._notes: list[dict] = []
        self._audit: list[dict] = []
        self._pending: dict[str, dict] = {}

    def now(self) -> float:
        return self.clock() - self._t0

    @property
    def queue_depth(self) -> int:
        return self._waiting + (self._inbox.qsize() if self._inbox is not None else 0)

    def notes(self) -> list[dict]:
        return list(self._notes)

    def audit(self) -> list[dict]:
        return list(self._audit)

    def pending_confirms(self) -> list[dict]:
        return list(self._pending.values())

    def health(self) -> dict:
        return {"type": "health", "state": self.state, "queue_depth": self.queue_depth,
                "max_queue_depth": self._max_depth, "last_push_ms": self.last_push_ms,
                "max_push_ms": round(self.max_push_ms, 1), "pushes": self.pushes,
                "ticks": self.ticks, "ticks_skipped": self.ticks_skipped, "errors": self.errors,
                "source": self.source_name, "source_state": self.source_state,
                "source_error": self.source_error, "pipeline": self.pipeline_kind,
                "hold_seconds": self.hold_seconds, "uptime": round(self.now(), 1) if self._t0 else 0.0,
                "dropped": sum(s.dropped for s in self._subs), "subscribers": len(self._subs),
                "pending": len(self._pending), "done": self.done}

    # ------------------------------------------------------------ pub/sub
    def _publish(self, msg: dict) -> dict:
        if msg["type"] in PERSISTENT:
            self._seq += 1
            msg["seq"] = self._seq
            self._history.append(msg)
        for s in list(self._subs):
            s.offer(msg)
        return msg

    def subscribe(self, since: Optional[int] = None) -> Subscription:
        """Register a subscriber, pre-filled with history after seq `since` (None = all)."""
        sub = Subscription(self._queue_size)
        for m in self._history:
            if since is None or m["seq"] > since:
                sub.offer(m)
        sub.offer(self.health())
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        sub.closed = True
        self._subs.discard(sub)

    def _notice(self, where: str, exc: BaseException | str, segment_id: Optional[str] = None) -> None:
        self.errors += 1
        msg = f"{type(exc).__name__}: {exc}" if isinstance(exc, BaseException) else str(exc)
        self._publish({"type": "error", "where": where, "message": msg, "segment_id": segment_id})

    def _set_source_state(self, st: str, err: str = "") -> None:
        if st == self.source_state and err == self.source_error:
            return
        self.source_state, self.source_error = st, err
        self._publish({"type": "source", "source": self.source_name, "state": st, "error": err})

    # ------------------------------------------------------------ worker-thread calls
    async def _call(self, name: str, fn: Callable[[], Any], segment_id: Optional[str] = None,
                    *, snapshot_always: bool = False) -> Optional[list[Event]]:
        """Run fn() (returns list[Event]) in the pipeline thread, publish the result.
        Returns the events, or None if the pipeline raised (an 'error' message is published)."""
        pipe, cap = self._pipe, self._audit_cap
        loop = asyncio.get_running_loop()

        def work():
            evs = fn() or []
            snap = None
            if evs or snapshot_always:
                snap = ([s.to_dict() for s in pipe.notes()], [e.to_dict() for e in pipe.audit_log()][-cap:])
            return evs, snap

        self._waiting += 1
        self._max_depth = max(self._max_depth, self.queue_depth)
        try:
            async with self._lock:
                t = time.perf_counter()
                try:
                    evs, snap = await loop.run_in_executor(self._executor, work)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # error isolation: keep running
                    self._notice(name, e, segment_id)
                    return None
                ms = (time.perf_counter() - t) * 1000
                if name == "push":
                    self.pushes += 1
                    self.last_push_ms = round(ms, 1)
                    self.max_push_ms = max(self.max_push_ms, ms)
                if snap is not None:
                    self._notes, self._audit = snap
                if evs:
                    self._record(evs)
                    self._publish({"type": "events", "events": [e.to_dict() for e in evs],
                                   "notes": self._notes, "audit": self._audit})
                return evs
        finally:
            self._waiting -= 1

    def _record(self, evs: list[Event]) -> None:
        for e in evs:
            if e.state:
                self.state = e.state
            if e.kind == "pending_confirm" and e.segment_id:
                self._pending[e.segment_id] = {"segment_id": e.segment_id, "speaker": e.speaker,
                                               "text": e.text, "reason": e.reason}
            elif e.kind in ("committed", "redacted", "retro_removed") and e.segment_id:
                self._pending.pop(e.segment_id, None)

    # ------------------------------------------------------------ public control
    async def confirm(self, segment_id: str, keep_out: bool) -> list[Event]:
        evs = await self._call("confirm", lambda: self._pipe.confirm(segment_id, keep_out), segment_id)
        return evs or []

    def set_hold_seconds(self, seconds: float) -> None:
        """Apply immediately to display state, and in the worker thread to the pipeline."""
        self.hold_seconds = float(seconds)
        self._publish({"type": "config", "hold_seconds": self.hold_seconds})
        pipe = self._pipe

        def apply():
            pipe.hold_seconds = self.hold_seconds
            buf = getattr(pipe, "buf", None)
            if buf is not None and hasattr(buf, "hold_seconds"):
                buf.hold_seconds = self.hold_seconds
            return []
        if self._executor is not None:
            asyncio.ensure_future(self._call("set_hold", apply))
        else:
            apply()

    async def flush(self) -> list[Event]:
        return (await self._call("flush", lambda: self._pipe.flush())) or []

    async def say(self, speaker: str, text: str) -> Segment:
        """Typed line: same path as a source segment, but waits until the pipeline has handled it."""
        t = self.now()
        self._say_n += 1
        seg = Segment(id=f"u{self._say_n}", speaker=speaker,
                      text=text, t_start=t, t_end=t)
        fut = asyncio.get_running_loop().create_future()
        self._arrive(seg, fut)
        await fut
        return seg

    def _arrive(self, seg: Segment, fut: Optional[asyncio.Future] = None) -> None:
        now = self.now()
        self._last_arrival = now
        self._publish({"type": "segment", "segment": seg.to_dict(), "t": round(now, 3)})
        self._inbox.put_nowait((seg, now, fut))
        self._max_depth = max(self._max_depth, self.queue_depth)

    # ------------------------------------------------------------ tasks
    async def _pusher(self) -> None:
        while True:
            seg, now, fut = await self._inbox.get()
            try:
                await self._call("push", lambda s=seg, n=now: self._pipe.push(s, now=n), seg.id)
            finally:
                if fut is not None and not fut.done():
                    fut.set_result(None)
                self._inbox.task_done()

    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(self.tick_interval)
            if self.queue_depth > 0:
                # pipeline busy; a push releases due segments itself, don't pile up ticks
                self.ticks_skipped += 1
                continue
            self.ticks += 1
            await self._call("tick", lambda: self._pipe.tick(self.now()))

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(self._health_interval)
            self._publish(self.health())

    async def _consume(self) -> None:
        while True:
            self._set_source_state("connected")
            try:
                async for seg in self._source.segments():
                    self._arrive(seg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._notice("source", e)
                self._set_source_state("error", f"{type(e).__name__}: {e}")
            else:
                self._set_source_state("disconnected" if self._reconnect else "ended")
            if self._reconnect and self._factory is not None:
                self._set_source_state("reconnecting", self.source_error)
                await asyncio.sleep(self._reconnect_delay)
                self._source = self._factory()
                continue
            break
        await self._finish()

    async def _finish(self) -> None:
        """Finite source ended: let held segments age out on the clock, then flush."""
        await self._inbox.join()
        while self.now() - self._last_arrival < self.hold_seconds + self._finish_margin:
            await asyncio.sleep(self.tick_interval)
        await self._inbox.join()
        await self.flush()
        self._mark_done()

    def _mark_done(self) -> None:
        if not self.done:
            self.done = True
            self._publish({"type": "done"})

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._tasks:
            return
        self._lock, self._inbox = asyncio.Lock(), asyncio.Queue()
        self._executor = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="otr-pipeline")
        self._t0 = self.clock()
        self._publish({"type": "reset", "hold_seconds": self.hold_seconds, "pipeline": self.pipeline_kind,
                       "source": self.source_name})
        self._tasks = [asyncio.ensure_future(self._pusher()), asyncio.ensure_future(self._ticker()),
                       asyncio.ensure_future(self._health_loop())]
        if self._source is not None:
            self._tasks.append(asyncio.ensure_future(self._consume()))
        else:
            self._set_source_state("none")

    async def stop(self, flush: bool = True, timeout: float = 5.0) -> None:
        tasks, self._tasks = self._tasks, []
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except BaseException:
                pass
        if self._executor is not None:
            if flush and not self.done and self._pipe is not None:
                try:
                    await asyncio.wait_for(self.flush(), timeout)
                except BaseException as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        if self._t0:
            self._mark_done()

    async def restart(self, pipeline, source=None, source_factory=None) -> None:
        """Replace pipeline (and source); subscribers stay connected and get a fresh 'reset'."""
        await self.stop(flush=False)
        self._pipe, self._source, self._factory = pipeline, source, source_factory
        self.hold_seconds = float(getattr(pipeline, "hold_seconds", self.hold_seconds))
        self._history.clear()
        self._reset_stats()
        self.start()
