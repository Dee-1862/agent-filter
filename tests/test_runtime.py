import asyncio
import time

from demo.fake_pipeline import Pipeline as FakePipeline
from otr.ingest.replay_source import ReplaySource, parse_script
from otr.runtime import StreamRunner
from otr.types import Segment


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


async def until(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        await asyncio.sleep(0.01)


def drain(sub):
    out = []
    while not sub.queue.empty():
        out.append(sub.queue.get_nowait())
    return out


def kinds(msgs):
    return [e["kind"] for m in msgs if m["type"] == "events" for e in m["events"]]


SCRIPT = "Ann: we ship on friday\nBob: the roadmap looks fine\nAnn: his salary is 150,000\n"


def make(source=None, pipe=None, clock=None, **kw):
    pipe = pipe or FakePipeline(hold_seconds=5)
    return StreamRunner(source, pipe, clock=clock or FakeClock(), tick_interval=0.02, health_interval=0.05, **kw)


def test_replay_hold_release_by_fake_clock_then_done():
    async def go():
        clock = FakeClock()
        r = make(ReplaySource(parse_script(SCRIPT)), clock=clock)
        sub = r.subscribe()
        r.start()
        await until(lambda: r.pushes == 3)
        got = drain(sub)
        assert any(m["type"] == "reset" for m in got)
        assert kinds(got).count("held") == 3 and "committed" not in kinds(got)
        assert [p["segment_id"] for p in r.pending_confirms()] == ["s0003"]
        clock.advance(100)          # nobody is talking, held segments still release by clock
        await until(lambda: r.notes() and r.state != "x")
        await r.confirm("s0003", True)
        await until(lambda: r.done)
        msgs = drain(sub)
        assert msgs[-1]["type"] == "done" or any(m["type"] == "done" for m in msgs)
        assert [n["id"] for n in r.notes()] == ["s0001", "s0002"]
        assert not r.pending_confirms()
        await r.stop()
    asyncio.run(go())


def test_events_use_arrival_time_on_pipeline_clock():
    async def go():
        clock = FakeClock()
        r = make(None, clock=clock)
        r.start()
        clock.advance(7.5)
        await r.say("Ann", "hello there")
        held = [e for e in r.audit() if e["kind"] == "held"][0]
        assert abs(held["t"] - 7.5) < 1e-6
        await r.stop()
    asyncio.run(go())


def test_confirm_and_set_hold_seconds():
    async def go():
        clock = FakeClock()
        pipe = FakePipeline(hold_seconds=50)
        r = make(None, pipe, clock)
        r.start()
        sub = r.subscribe()
        await r.say("Ann", "the bonus plan")
        assert r.state == "PENDING_CONFIRM"
        evs = await r.confirm("u1", False)
        assert evs[0].kind == "committed"
        await r.say("Ann", "ship it")
        clock.advance(10)
        r.set_hold_seconds(5)
        await until(lambda: pipe.hold_seconds == 5)
        await until(lambda: any(a["kind"] == "committed" and a["segment_id"] == "u2" for a in r.audit()))
        assert any(m["type"] == "config" and m["hold_seconds"] == 5 for m in drain(sub))
        await r.stop()
    asyncio.run(go())


class SlowPipeline(FakePipeline):
    def __init__(self, delay, **kw):
        super().__init__(**kw)
        self.delay = delay

    def push(self, seg, now=None):
        time.sleep(self.delay)
        return super().push(seg, now)


def test_slow_pipeline_does_not_block_loop_subscribers_or_ticker():
    async def go():
        r = make(ReplaySource(parse_script("Ann: one\nBob: two\nAnn: three\n")),
                 SlowPipeline(0.4, hold_seconds=5))
        sub = r.subscribe()
        gaps, stop = [], False

        async def heartbeat():
            last = time.monotonic()
            while not stop:
                await asyncio.sleep(0.01)
                n = time.monotonic()
                gaps.append(n - last)
                last = n
        hb = asyncio.ensure_future(heartbeat())
        r.start()
        # all three arrivals are published while the first push is still sleeping
        await until(lambda: sum(1 for m in drain_peek(sub) if m["type"] == "segment") == 3, 1.0)
        assert r.pushes < 3 and r.queue_depth >= 2
        await until(lambda: r.pushes == 3, 5)
        stop = True
        await hb
        assert max(gaps) < 0.25, max(gaps)          # loop never blocked by the 0.4s pushes
        msgs = drain(sub)
        assert any(m["type"] == "health" for m in msgs)  # health kept flowing during slow pushes
        assert r.ticks_skipped > 0                       # ticker skipped instead of piling up
        assert r.last_push_ms >= 350 and r.health()["max_queue_depth"] >= 2
        await r.stop()

    def drain_peek(sub):
        return list(sub.queue._queue)
    asyncio.run(go())


class Boom(FakePipeline):
    def push(self, seg, now=None):
        if "boom" in seg.text:
            raise ValueError("kaput")
        return super().push(seg, now)


def test_pipeline_exception_is_isolated():
    async def go():
        r = make(None, Boom(hold_seconds=5))
        sub = r.subscribe()
        r.start()
        await r.say("Ann", "boom now")
        await r.say("Ann", "fine after")
        msgs = drain(sub)
        errs = [m for m in msgs if m["type"] == "error"]
        assert len(errs) == 1 and "kaput" in errs[0]["message"] and errs[0]["segment_id"] == "u1"
        assert r.errors == 1 and kinds(msgs).count("held") == 1
        await r.stop()
    asyncio.run(go())


class Dying:
    async def segments(self):
        yield Segment("a1", "Ann", "hello", 0, 1)
        raise RuntimeError("socket closed")


def test_source_error_is_reported_and_reconnect_retries():
    async def go():
        made = []

        def factory():
            made.append(1)
            return Dying()
        r = make(Dying(), source_factory=factory, reconnect=True, reconnect_delay=0.05)
        sub = r.subscribe()
        r.start()
        await until(lambda: len(made) >= 1)
        await until(lambda: r.pushes >= 2)
        states = [m["state"] for m in drain(sub) if m["type"] == "source"]
        assert "error" in states and "reconnecting" in states and "connected" in states
        await r.stop()
    asyncio.run(go())


def test_subscriber_replay_and_bounded_queue():
    async def go():
        r = make(None, queue_size=5, history=50)
        r.start()
        for i in range(10):
            await r.say("Ann", f"line {i}")
        late = r.subscribe(since=0)           # replays history
        assert late.queue.qsize() == 5 and late.dropped > 0   # bounded: oldest dropped
        mid = r.subscribe(since=r._seq - 1)
        assert [m["type"] for m in drain(mid) if "seq" in m][-1] in ("events", "segment")
        await r.stop()
        assert r.done
    asyncio.run(go())


def test_restart_resets_state_keeps_subscribers():
    async def go():
        r = make(None)
        sub = r.subscribe()
        r.start()
        await r.say("Ann", "hello")
        await r.restart(FakePipeline(hold_seconds=3))
        assert r.notes() == [] and r.hold_seconds == 3
        msgs = drain(sub)
        assert [m["type"] for m in msgs if m["type"] == "reset"] == ["reset", "reset"]
        await r.stop()
    asyncio.run(go())
