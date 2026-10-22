import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo.live_session import LiveSession
from demo.server import build_livekit_source, create_app, load_script_segments
from demo.fake_pipeline import Pipeline as FakePipeline
from otr.types import Segment

SCRIPTS = Path(__file__).resolve().parent.parent / "demo" / "scripts"


def read_stream(client, **params):
    msgs = []
    with client.stream("GET", "/stream", params={"once": 1, **params}) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                msgs.append(json.loads(line[6:]))
    return msgs


def kinds(msgs):
    return [e for m in msgs if m["type"] == "events" for e in m["events"]]


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.02)


@pytest.mark.parametrize("name", ["demo_main", "demo_retro_committed", "demo_false_alarm"])
def test_scripts_parse(name):
    segs = load_script_segments(SCRIPTS / f"{name}.txt")
    assert len(segs) >= 5
    assert all(s.speaker and s.text and not s.text.startswith("@") for s in segs)
    assert len({s.id for s in segs}) == len(segs)
    assert all(a.t_end <= b.t_start for a, b in zip(segs, segs[1:]))


def test_pause_directive_shifts_time_and_is_not_text(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text("A: one\n@pause 5\nB: two\n", encoding="utf-8")
    a, b = load_script_segments(p)
    assert b.text == "two" and b.t_start - a.t_end >= 5


def test_main_script_has_four_speakers():
    assert len({s.speaker for s in load_script_segments(SCRIPTS / "demo_main.txt")}) == 4


def test_index_served():
    with TestClient(create_app("fake", autostart=False)) as c:
        r = c.get("/")
        assert r.status_code == 200 and "Final notes" in r.text
        assert "Presenter mode" in r.text and "pendcard" in r.text


def test_index_has_progressive_disclosure_levels():
    with TestClient(create_app("fake", autostart=False)) as c:
        r = c.get("/")
        assert r.status_code == 200
        for marker in ('id="tiles"', 'id="captions"', 'id="status-pill"', 'id="insights-btn"',
                       'id="insights-panel"', 'id="explain-panel"', 'id="live-btn"',
                       'id="settings-menu"', 'id="banner"', "Keep that out of the notes?"):
            assert marker in r.text, marker
        # the overview must not render private text: only a placeholder chip
        assert "kept out of notes" in r.text and "Reveal text" in r.text


def test_index_dom_ids_all_exist():
    import re
    html = (Path(__file__).resolve().parent.parent / "demo" / "static" / "index.html").read_text(encoding="utf-8")
    declared = set(re.findall(r'\bid="([^"]+)"', html))
    used = set(re.findall(r'\$\("([^"]+)"\)', html))
    assert used - declared == set(), used - declared


def test_session_replay_events_in_order():
    app = create_app("fake", script=SCRIPTS / "demo_main.txt", speed=500, hold_seconds=0.3)
    with TestClient(app) as c:
        msgs = read_stream(c)
    assert msgs[0]["type"] == "reset" and msgs[-1]["type"] == "done"
    assert any(m["type"] == "segment" for m in msgs)
    events = kinds(msgs)
    ts = [e["t"] for e in events]
    assert ts == sorted(ts)
    ks = [e["kind"] for e in events]
    assert {"held", "committed", "redacted", "state_change", "pending_confirm"} <= set(ks)
    first = {}
    for i, e in enumerate(events):
        first.setdefault(e["segment_id"], i)
        if e["kind"] == "committed":
            assert events[first[e["segment_id"]]]["kind"] == "held"
    states = [e["state"] for e in events if e["kind"] == "state_change"]
    assert "OFF" in states and "ON" in states[states.index("OFF"):]


def test_state_has_health_and_source():
    with TestClient(create_app("fake", autostart=False)) as c:
        s = c.get("/api/state").json()
        assert s["source"] == "typed" and s["health"]["queue_depth"] == 0
        assert c.get("/api/health").json()["type"] == "health"


def test_say_and_confirm():
    app = create_app("fake", autostart=False, hold_seconds=0.2)
    with TestClient(app) as c:
        sid = c.post("/api/say", json={"speaker": "Dan", "text": "His salary is 150,000"}).json()["segment_id"]
        s = c.get("/api/state").json()
        assert s["audit"][-1]["kind"] == "pending_confirm"
        assert [p["segment_id"] for p in s["pending"]] == [sid]
        r = c.post("/api/confirm", json={"segment_id": sid, "keep_out": True})
        assert r.status_code == 200
        assert [e["kind"] for e in r.json()["events"]][0] == "redacted"
        assert c.get("/api/state").json()["notes"] == []
        sid2 = c.post("/api/say", json={"speaker": "Dan", "text": "the bonus plan"}).json()["segment_id"]
        r = c.post("/api/confirm", json={"segment_id": sid2, "keep_out": False})
        assert r.json()["events"][0]["kind"] == "committed"
        assert [n["id"] for n in c.get("/api/state").json()["notes"]] == [sid2]
        assert c.post("/api/confirm", json={"segment_id": "nope", "keep_out": True}).json()["events"] == []
        assert c.post("/api/confirm", json={}).status_code == 400
        assert c.post("/api/say", json={"text": " "}).status_code == 400


def test_hold_endpoint_and_retro():
    app = create_app("fake", autostart=False, hold_seconds=0.0, tick_interval=0.02)
    with TestClient(app) as c:
        assert c.post("/api/hold", json={"seconds": 5}).json()["hold_seconds"] == 5
        c.post("/api/hold", json={"seconds": 0})
        c.post("/api/say", json={"speaker": "A", "text": "we ship friday"})
        wait_for(lambda: len(c.get("/api/state").json()["notes"]) == 1)
        c.post("/api/say", json={"speaker": "A", "text": "scratch that"})
        ks = [e["kind"] for e in c.get("/api/state").json()["audit"]]
        assert "retro_removed" in ks
        assert c.get("/api/state").json()["notes"] == []
        assert c.post("/api/hold", json={}).status_code == 400


def test_restart_replays_script():
    app = create_app("fake", script=SCRIPTS / "demo_false_alarm.txt", speed=500, hold_seconds=0.2)
    with TestClient(app) as c:
        read_stream(c)
        assert c.post("/api/restart").status_code == 200
        msgs = read_stream(c)
        assert msgs[0]["type"] == "reset" and msgs[-1]["type"] == "done"


def test_livekit_missing_sdk_gives_clear_error(monkeypatch):
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: None if n == "livekit" else real(n, *a))
    with pytest.raises(RuntimeError, match="livekit"):
        build_livekit_source("demo")


class StubLiveSource:
    url = "ws://127.0.0.1:7880"
    room_name = "demo"
    api_key = "devkey"
    api_secret = "secret"

    def __init__(self):
        self.consent = {}

    def set_consent(self, identity, enabled):
        self.consent[identity] = enabled

    def consent_snapshot(self):
        return dict(self.consent)


def test_live_uses_per_person_consent_and_publishes_approved_only():
    src = StubLiveSource()
    live = LiveSession(FakePipeline, "fake", src, hold_seconds=0)
    live.names.update({"alice": "Alice", "bob": "Bob"})
    live.set_consent("alice", True)
    live.push(Segment("off", "bob", "private words", 0, 0))
    assert "private words" not in json.dumps(live.messages)
    live.push(Segment("a1", "alice", "Plan the launch", 0, 0))
    assert "Plan the launch" not in json.dumps(live.messages)
    live._publish_events("alice", live.pipes["alice"].tick(1))
    assert live.approved["a1"]["text"] == "Plan the launch"
    live.set_consent("bob", True)
    live.push(Segment("b1", "bob", "off the record", 1, 1))
    assert src.consent["bob"] is False
    assert src.consent["alice"] is True
    assert "off the record" not in json.dumps(live.messages)
    live.push(Segment("a2", "alice", "stop recording me", 1, 1))
    assert src.consent["alice"] is False
    assert "stop recording me" not in json.dumps(live.messages)


@pytest.mark.parametrize("spoken", [
    "Please stop recording the...",  # observed local TTS -> Whisper output
    "Stop recording.",
    "Hey, please stop recording me.",
])
def test_live_spoken_stop_tolerates_misheard_ending_and_discards_text(spoken):
    src = StubLiveSource()
    live = LiveSession(FakePipeline, "fake", src, hold_seconds=0)
    live.names.update({"alice": "Alice", "bob": "Bob"})
    live.set_consent("alice", True)
    live.set_consent("bob", True)
    live.push(Segment("request", "alice", spoken, 0, 0))
    live.push(Segment("after", "alice", "This must stay out", 1, 1))
    assert src.consent == {"alice": False, "bob": True}
    assert live.approved == {}
    assert spoken not in json.dumps(live.messages)
    assert "This must stay out" not in json.dumps(live.messages)


@pytest.mark.parametrize("spoken", [
    "I said, 'stop recording me' as an example.",
    "Don't stop recording me.",
    "We should discuss the stop recording button.",
])
def test_live_spoken_stop_ignores_quoted_or_negated_mentions(spoken):
    src = StubLiveSource()
    live = LiveSession(FakePipeline, "fake", src, hold_seconds=0)
    live.names["alice"] = "Alice"
    live.set_consent("alice", True)
    live.push(Segment("mention", "alice", spoken, 0, 0))
    assert src.consent["alice"] is True


def test_live_endpoints_never_offer_replay_controls_or_raw_state():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as client:
        assert "Your voice, your choice" in client.get("/").text
        assert client.get("/api/state").status_code == 404
        assert client.post("/api/say", json={"speaker": "a", "text": "secret"}).status_code == 404
        assert client.post("/api/consent", json={"recording": True}).status_code == 401
        assert client.get("/stream").status_code == 401


def test_live_consent_is_bound_to_server_issued_identity():
    src = StubLiveSource()
    app = create_app("fake", source="livekit", live_source=src, autostart=False)
    with TestClient(app) as first, TestClient(app) as second:
        a = first.post("/api/join", json={"name": "Alice", "identity": "chosen"})
        b = second.post("/api/join", json={"name": "Bob", "identity": a.json()["identity"]})
        assert a.status_code == b.status_code == 200
        alice, bob = a.json()["identity"], b.json()["identity"]
        assert alice != bob and alice != "chosen"
        assert not src.consent[alice] and not src.consent[bob]
        assert first.post("/api/consent", json={"recording": True, "identity": bob}).json() == {
            "identity": alice, "recording": True,
        }
        assert src.consent[alice] and not src.consent[bob]
        assert second.get("/api/me").json()["identity"] == bob
        assert first.post("/api/consent", json={"recording": "false"}).status_code == 400


def test_live_explicit_consent_off_discards_pending_and_blocks_later_segments():
    src = StubLiveSource()
    app = create_app("fake", source="livekit", live_source=src, autostart=False, hold_seconds=10)
    with TestClient(app) as client:
        identity = client.post("/api/join", json={"name": "Alice"}).json()["identity"]
        assert client.post("/api/consent", json={"recording": True}).status_code == 200
        session = app.state.session
        session.push(Segment("pending", identity, "Private pending line", 0, 0))
        assert identity in session.pipes
        assert client.post("/api/consent", json={"recording": False}).status_code == 200
        assert src.consent[identity] is False
        assert identity not in session.pipes
        session.push(Segment("later", identity, "Private later line", 1, 1))
        assert client.get("/api/me").json()["lines"] == []
        assert "Private pending line" not in json.dumps(session.messages)
        assert "Private later line" not in json.dumps(session.messages)


def test_live_sensitive_hold_pauses_only_that_speaker_and_never_allows_publication():
    src = StubLiveSource()
    live = LiveSession(FakePipeline, "fake", src, hold_seconds=0)
    live.names.update({"alice": "Alice", "bob": "Bob"})
    live.set_consent("alice", True)
    live.set_consent("bob", True)
    live.push(Segment("sensitive", "alice", "Her salary is 150,000", 0, 0))
    assert src.consent == {"alice": False, "bob": True}
    assert live.snapshot()["alice"]["sensitive_paused"] is True
    assert live.snapshot()["bob"]["sensitive_paused"] is False
    assert "alice" not in live.pipes
    assert "150,000" not in json.dumps(live.messages)
    assert live.approved == {}
    live.push(Segment("safe", "bob", "Agenda item one", 0, 0))
    live._publish_events("bob", live.pipes["bob"].tick(1))
    assert live.approved["safe"]["text"] == "Agenda item one"
    live.set_consent("alice", True)
    assert live.snapshot()["alice"]["sensitive_paused"] is False
    assert "150,000" not in json.dumps(live.messages)


def test_live_sensitive_confirmation_endpoint_is_absent():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as client:
        assert client.post("/api/confirm", json={"segment_id": "sensitive", "keep_out": False}).status_code == 404
        assert client.get("/api/private").status_code == 404
