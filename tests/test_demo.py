import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo.server import create_app, parse_script

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


@pytest.mark.parametrize("name", ["demo_main", "demo_retro_committed", "demo_false_alarm"])
def test_scripts_parse(name):
    lines = parse_script(SCRIPTS / f"{name}.txt")
    assert len(lines) >= 5
    assert all(sp and tx for sp, tx, _ in lines)


def test_main_script_has_four_speakers():
    assert len({sp for sp, _, _ in parse_script(SCRIPTS / "demo_main.txt")}) == 4


def test_index_served():
    with TestClient(create_app("fake", autostart=False)) as c:
        r = c.get("/")
        assert r.status_code == 200 and "Committed notes" in r.text


def test_session_replay_events_in_order():
    app = create_app("fake", script=SCRIPTS / "demo_main.txt", speed=500, hold_seconds=0.3)
    with TestClient(app) as c:
        msgs = read_stream(c)
    assert msgs[0]["type"] == "reset" and msgs[-1]["type"] == "done"
    events = kinds(msgs)
    ts = [e["t"] for e in events]
    assert ts == sorted(ts)
    ks = [e["kind"] for e in events]
    assert {"held", "committed", "redacted", "state_change", "pending_confirm"} <= set(ks)
    # every held segment appears before its resolution
    first = {}
    for i, e in enumerate(events):
        first.setdefault(e["segment_id"], i)
        if e["kind"] == "committed":
            assert events[first[e["segment_id"]]]["kind"] == "held"
    states = [e["state"] for e in events if e["kind"] == "state_change"]
    assert "OFF" in states and states.index("OFF") < len(states) - 1 and "ON" in states[states.index("OFF"):]


def test_say_and_confirm():
    app = create_app("fake", autostart=False, hold_seconds=0.2)
    with TestClient(app) as c:
        sid = c.post("/api/say", json={"speaker": "Dan", "text": "His salary is 150,000"}).json()["segment_id"]
        s = c.get("/api/state").json()
        assert s["audit"][-1]["kind"] == "pending_confirm"
        r = c.post("/api/confirm", json={"segment_id": sid, "keep_out": True})
        assert r.status_code == 200
        assert [e["kind"] for e in r.json()["events"]][0] == "redacted"
        assert c.get("/api/state").json()["notes"] == []
        # confirm "No" path commits
        sid2 = c.post("/api/say", json={"speaker": "Dan", "text": "the bonus plan"}).json()["segment_id"]
        r = c.post("/api/confirm", json={"segment_id": sid2, "keep_out": False})
        assert r.json()["events"][0]["kind"] == "committed"
        assert [n["id"] for n in c.get("/api/state").json()["notes"]] == [sid2]
        assert c.post("/api/confirm", json={"segment_id": "nope", "keep_out": True}).json()["events"] == []
        assert c.post("/api/confirm", json={}).status_code == 400
        assert c.post("/api/say", json={"text": " "}).status_code == 400


def test_hold_endpoint_and_retro():
    app = create_app("fake", autostart=False, hold_seconds=0.0)
    with TestClient(app) as c:
        assert c.post("/api/hold", json={"seconds": 5}).json()["hold_seconds"] == 5
        c.post("/api/hold", json={"seconds": 0})
        c.post("/api/say", json={"speaker": "A", "text": "we ship friday"})
        c.app.state.session.tick()
        assert len(c.get("/api/state").json()["notes"]) == 1
        c.post("/api/say", json={"speaker": "A", "text": "scratch that"})
        ks = [e["kind"] for e in c.get("/api/state").json()["audit"]]
        assert "retro_removed" in ks
        assert c.get("/api/state").json()["notes"] == []
