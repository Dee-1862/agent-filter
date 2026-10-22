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
    "Stop recording this meeting.",
    "Please stop recording",
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


def test_meeting_waiting_room_requires_host_admission_and_scopes_access():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as host, TestClient(app) as guest, TestClient(app) as outsider:
        created = host.post("/api/meetings", json={"name": "Host", "email": "host@example.test"})
        assert created.status_code == 200
        data = created.json()
        room = data["room_id"]
        assert data["join_url"].endswith("/m/" + room)
        assert host.get("/m/" + room).status_code == 200
        assert host.get("/api/meetings/other/status").status_code == 401
        assert outsider.get("/api/meetings/" + room + "/status").status_code == 401

        requested = guest.post("/api/meetings/" + room + "/request",
                               json={"name": "Guest", "email": "guest@example.test"})
        assert requested.status_code == 200
        assert requested.json()["status"] == "waiting"
        assert "token" not in requested.json()
        assert guest.get("/api/meetings/" + room + "/status").json()["status"] == "waiting"
        assert guest.get("/api/me").status_code == 403
        assert guest.post("/api/consent", json={"recording": True}).status_code == 403
        pending = host.get("/api/meetings/" + room + "/status").json()["pending"]
        assert len(pending) == 1 and pending[0]["name"] == "Guest"
        assert guest.post("/api/meetings/" + room + "/admit",
                          json={"request_id": pending[0]["request_id"]}).status_code == 403

        admitted = host.post("/api/meetings/" + room + "/admit",
                             json={"request_id": pending[0]["request_id"]})
        assert admitted.status_code == 200
        status = guest.get("/api/meetings/" + room + "/status").json()
        assert status["status"] == "admitted"
        assert status["room"] == room
        assert guest.get("/api/me").json()["identity"] == status["identity"]
        assert guest.post("/api/consent", json={"recording": True}).status_code == 200
        assert host.get("/api/me").json()["participants"][status["identity"]]["recording"] is True


def test_meeting_denial_never_issues_room_access():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as host, TestClient(app) as guest:
        room = host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"}).json()["room_id"]
        req = guest.post("/api/meetings/" + room + "/request",
                         json={"name": "Guest", "email": "g@example.test"}).json()
        assert host.post("/api/meetings/" + room + "/deny",
                         json={"request_id": req["request_id"]}).status_code == 200
        status = guest.get("/api/meetings/" + room + "/status").json()
        assert status["status"] == "denied" and "token" not in status
        assert guest.get("/api/me").status_code == 403


def test_meeting_guest_can_cancel_pending_request(monkeypatch):
    monkeypatch.setenv("MEETING_PUBLIC_ORIGIN", "http://192.0.2.10:8772")
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as host, TestClient(app) as guest:
        created = host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"}).json()
        room = created["room_id"]
        assert created["join_url"] == "http://192.0.2.10:8772/m/" + room
        guest.post("/api/meetings/" + room + "/request",
                   json={"name": "Guest", "email": "g@example.test"})
        assert len(host.get("/api/meetings/" + room + "/status").json()["pending"]) == 1
        assert guest.post("/api/meetings/" + room + "/cancel").status_code == 200
        assert host.get("/api/meetings/" + room + "/status").json()["pending"] == []
        assert guest.get("/api/meetings/" + room + "/status").status_code == 401


def test_meeting_cookies_keep_host_sessions_separate_across_tabs():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as browser:
        first = browser.post("/api/meetings", json={"name": "First", "email": "one@example.test"}).json()
        second = browser.post("/api/meetings", json={"name": "Second", "email": "two@example.test"}).json()
        first_id, second_id = first["room_id"], second["room_id"]
        assert browser.get("/api/meetings/" + first_id + "/status").json()["identity"] == first["identity"]
        assert browser.get("/api/meetings/" + second_id + "/status").json()["identity"] == second["identity"]
        first_page = {"referer": "http://testserver/m/" + first_id}
        second_page = {"referer": "http://testserver/m/" + second_id}
        assert browser.get("/api/me", headers=first_page).json()["identity"] == first["identity"]
        assert browser.get("/api/me", headers=second_page).json()["identity"] == second["identity"]
        assert browser.post("/api/leave", headers=first_page).status_code == 200
        assert browser.get("/api/meetings/" + first_id + "/status").status_code == 401
        assert browser.get("/api/meetings/" + second_id + "/status").status_code == 200


def test_host_end_purges_room_and_revokes_guest_access():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as host, TestClient(app) as guest, TestClient(app) as outsider:
        room_id = host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"}).json()["room_id"]
        requested = guest.post("/api/meetings/" + room_id + "/request",
                               json={"name": "Guest", "email": "g@example.test"}).json()
        assert outsider.post("/api/meetings/" + room_id + "/end").status_code == 401
        assert guest.post("/api/meetings/" + room_id + "/end").status_code == 403
        assert host.post("/api/meetings/" + room_id + "/admit",
                         json={"request_id": requested["request_id"]}).status_code == 200
        live = app.state.meetings[room_id]["session"]
        guest_id = guest.get("/api/me").json()["identity"]
        guest.post("/api/consent", json={"recording": True})
        live.approved["guest-line"] = {"id": "guest-line", "speaker": guest_id,
                                       "name": "Guest", "text": "Agenda item one"}
        live.line_owner["guest-line"] = guest_id
        assert live.approved

        ended = host.post("/api/meetings/" + room_id + "/end")
        assert ended.status_code == 200
        assert "no-store" in ended.headers["cache-control"]
        assert room_id not in app.state.meetings
        assert live.closed and live.approved == {} and live.messages == []
        assert live.sessions == {} and live.names == {} and live.pipes == {}
        assert host.get("/m/" + room_id).status_code == 404
        assert host.get("/api/me").status_code == 401
        assert guest.get("/api/me").status_code == 401
        assert guest.get("/api/meetings/" + room_id + "/status").status_code == 401
        assert host.post("/api/meetings/" + room_id + "/end").status_code == 401
        live.push(Segment("late", guest_id, "Too late", 0, 0))
        assert live.approved == {}


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


# ---------------------------------------------------------------- privacy-first seam
def live_app(hold_seconds=0.0):
    src = StubLiveSource()
    app = create_app("fake", source="livekit", live_source=src, autostart=False,
                     hold_seconds=hold_seconds)
    return app, src


def join_as(client, name):
    r = client.post("/api/join", json={"name": name})
    assert r.status_code == 200
    return r.json()["identity"]


def approve_line(session, identity, line_id, text, now=1.0):
    session.push(Segment(line_id, identity, text, now, now))
    session._publish_events(identity, session.pipes[identity].tick(now + 0.01))


def live_stream_messages(session, viewer, since=None):
    """Exercise the same visibility filter used by SSE without opening its endless HTTP stream."""
    msgs = [{"type": "participants", "participants": session.public_participants(viewer)},
            {"type": "snapshot", "lines": session.own_lines(viewer)}]
    for message in session.messages[since if since is not None else len(session.messages):]:
        visible = session.visible_message(viewer, message)
        if visible is not None:
            msgs.append(visible)
    return msgs


def test_live_two_clients_see_only_own_lines_and_statuses():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c, TestClient(app) as bob_c:
        alice, bob = join_as(alice_c, "Alice"), join_as(bob_c, "Bob")
        alice_c.post("/api/consent", json={"recording": True})
        bob_c.post("/api/consent", json={"recording": True})
        approve_line(session, alice, "a1", "Alice launch plan")
        approve_line(session, bob, "b1", "Bob budget notes")
        session.push(Segment("a2", alice, "Her salary is 150,000", 2, 2))  # sensitive pause

        me_a = alice_c.get("/api/me").json()
        me_b = bob_c.get("/api/me").json()
        assert [l["id"] for l in me_a["lines"]] == ["a1"]
        assert [l["id"] for l in me_b["lines"]] == ["b1"]
        assert me_a["lines"][0]["text"] == "Alice launch plan"
        assert me_b["lines"][0]["text"] == "Bob budget notes"
        # others expose only name + notes on/off; own status may expose the pause flag
        assert "sensitive_paused" not in me_b["participants"][alice]
        assert me_a["participants"][alice]["sensitive_paused"] is True
        assert me_a["participants"][bob] == {"name": "Bob", "recording": True}
        assert me_b["participants"][alice] == {"name": "Alice", "recording": False}


def test_live_stream_filters_other_speaker_text_and_ids():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c:
        alice = join_as(alice_c, "Alice")
        alice_c.post("/api/consent", json={"recording": True})
        session.names["bob"] = "Bob"
        session.set_consent("bob", True)
        approve_line(session, alice, "a1", "Alice line one")
        approve_line(session, "bob", "b1", "Bob secret one")

        msgs = live_stream_messages(session, alice)
        body = json.dumps(msgs)
        assert "Alice line one" in body
        assert "Bob secret one" not in body and '"id": "b1"' not in body
        snap = next(m for m in msgs if m["type"] == "snapshot")
        assert [l["id"] for l in snap["lines"]] == ["a1"]

        start = len(session.messages)
        approve_line(session, "bob", "b2", "Bob secret two")
        approve_line(session, alice, "a2", "Alice line two")
        live_msgs = live_stream_messages(session, alice, start)
        body = json.dumps(live_msgs)
        assert "Alice line two" in body
        assert "Bob secret two" not in body and '"id": "b2"' not in body


def test_live_stream_late_join_gets_only_own_lines():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c:
        alice = join_as(alice_c, "Alice")
        alice_c.post("/api/consent", json={"recording": True})
        approve_line(session, alice, "a1", "Alice early line")

    with TestClient(app) as bob_c:
        bob = join_as(bob_c, "Bob")
        msgs = live_stream_messages(session, bob)
        body = json.dumps(msgs)
        assert "Alice early line" not in body and '"id": "a1"' not in body
        snap = next(m for m in msgs if m["type"] == "snapshot")
        assert snap["lines"] == []


def test_live_notes_remove_authorization_and_stream_reflection():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c, TestClient(app) as bob_c:
        alice, bob = join_as(alice_c, "Alice"), join_as(bob_c, "Bob")
        alice_c.post("/api/consent", json={"recording": True})
        bob_c.post("/api/consent", json={"recording": True})
        approve_line(session, alice, "a1", "Alice line one")
        approve_line(session, bob, "b1", "Bob line one")

        # another speaker's line id: 404, text never leaks, line stays
        assert bob_c.post("/api/notes/remove", json={"id": "a1"}).status_code == 404
        assert alice_c.get("/api/me").json()["lines"][0]["text"] == "Alice line one"

        start = len(session.messages)
        assert alice_c.post("/api/notes/remove", json={"id": "a1"}).status_code == 200
        live_msgs = live_stream_messages(session, alice, start)
        removed = [m for m in live_msgs if m["type"] == "transcript"]
        assert any(c["kind"] == "removed" and c["id"] == "a1" for m in removed for c in m["changes"])
        assert alice_c.get("/api/me").json()["lines"] == []
        assert alice_c.post("/api/notes/remove", json={"id": "a1"}).status_code == 404
        assert bob_c.get("/api/me").json()["lines"][0]["id"] == "b1"
        assert bob_c.post("/api/notes/remove", json={}).status_code == 400


def test_live_notes_finalize_stops_capture_discards_held_and_blocks_consent():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as client:
        alice = join_as(client, "Alice")
        assert client.post("/api/consent", json={"recording": True}).status_code == 200
        approve_line(session, alice, "a1", "Alice approved line")
        session.push(Segment("held", alice, "Alice held line", 2, 2))

        r = client.post("/api/notes/finalize", json={})
        assert r.status_code == 200
        me = client.get("/api/me").json()
        assert me["finalized"] is True
        assert [l["id"] for l in me["lines"]] == ["a1"]
        assert alice not in session.pipes  # held text discarded
        assert client.post("/api/notes/finalize", json={}).status_code == 200  # idempotent
        assert client.post("/api/consent", json={"recording": True}).status_code == 409
        assert client.post("/api/consent", json={"recording": False}).status_code == 200
        session.push(Segment("late", alice, "Alice late line", 3, 3))
        assert client.get("/api/me").json()["lines"] == me["lines"]


def test_live_final_waits_for_present_speaker_without_approved_line():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c, TestClient(app) as bob_c:
        alice, bob = join_as(alice_c, "Alice"), join_as(bob_c, "Bob")
        alice_c.post("/api/consent", json={"recording": True})
        bob_c.post("/api/consent", json={"recording": True})
        approve_line(session, alice, "a1", "Alice agenda")
        assert alice_c.post("/api/notes/finalize", json={}).status_code == 200
        assert bob not in session.contributors()
        assert alice_c.get("/api/me").json()["ready_for_final"] is False
        assert alice_c.get("/api/notes/final").status_code == 409
        assert bob_c.post("/api/notes/finalize", json={}).status_code == 200
        assert alice_c.get("/api/notes/final").status_code == 200


def test_live_redaction_counts_are_aggregate_and_private():
    app, _ = live_app()
    live = app.state.session
    with TestClient(app) as alice_c, TestClient(app) as bob_c:
        alice, bob = join_as(alice_c, "Alice"), join_as(bob_c, "Bob")
        live.push(Segment("unconsented", alice, "Never transcribed", 0, 0))
        assert live.redaction_counts()["total"] == 0
        alice_c.post("/api/consent", json={"recording": True})
        bob_c.post("/api/consent", json={"recording": True})
        live.push(Segment("salary", alice, "Her salary is 150,000", 0, 0))
        assert alice_c.get("/api/me").json()["redaction_counts"] == {
            "suppressed": 1, "removed": 0, "total": 1,
        }
        assert bob_c.get("/api/me").json()["redaction_counts"]["total"] == 0
        approve_line(live, bob, "b1", "Bob budget notes")
        approve_line(live, bob, "b2", "Bob project timeline")
        assert bob_c.post("/api/notes/remove", json={"id": "b1"}).status_code == 200
        assert bob_c.get("/api/me").json()["redaction_counts"] == {
            "suppressed": 0, "removed": 1, "total": 1,
        }
        for message in live.messages:
            if message.get("type") == "redaction_counts":
                body = json.dumps(message)
                assert "150,000" not in body and "Bob budget notes" not in body
                assert '"id": "b1"' not in body and '"id": "salary"' not in body
                if message["owner"] == bob:
                    assert live.visible_message(alice, message) is None
        alice_c.post("/api/notes/finalize", json={})
        bob_c.post("/api/notes/finalize", json={})
        final = alice_c.get("/api/notes/final").json()
        assert final["redaction_counts"] == {"suppressed": 1, "removed": 1, "total": 2}
        assert [line["id"] for line in final["lines"]] == ["b2"]


def test_live_notes_final_gating_and_combined_transcript():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c, TestClient(app) as bob_c:
        alice, bob = join_as(alice_c, "Alice"), join_as(bob_c, "Bob")
        alice_c.post("/api/consent", json={"recording": True})
        bob_c.post("/api/consent", json={"recording": True})
        approve_line(session, alice, "a1", "Alice launch plan")
        approve_line(session, bob, "b1", "Bob budget notes")

        assert alice_c.get("/api/notes/final").status_code == 409
        me = alice_c.get("/api/me").json()
        assert me["contributor_count"] == 2 and me["finalized_count"] == 0
        assert me["ready_for_final"] is False

        assert alice_c.post("/api/notes/finalize", json={}).status_code == 200
        assert alice_c.get("/api/notes/final").status_code == 409

        assert bob_c.post("/api/notes/finalize", json={}).status_code == 200
        r = alice_c.get("/api/notes/final")
        assert r.status_code == 200
        assert "no-store" in r.headers["cache-control"]
        final = r.json()
        assert final["ready"] is True
        assert [(l["id"], l["name"], l["text"]) for l in final["lines"]] == [
            ("a1", "Alice", "Alice launch plan"), ("b1", "Bob", "Bob budget notes")]
        me = alice_c.get("/api/me").json()
        assert me["ready_for_final"] is True
        assert me["finalized_count"] == 2 and me["contributor_count"] == 2


def test_live_notes_final_requires_join():
    app, _ = live_app()
    with TestClient(app) as client:
        assert client.get("/api/notes/final").status_code == 401


def test_live_leave_drops_unfinalized_contribution():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c, TestClient(app) as bob_c:
        alice, bob = join_as(alice_c, "Alice"), join_as(bob_c, "Bob")
        alice_c.post("/api/consent", json={"recording": True})
        bob_c.post("/api/consent", json={"recording": True})
        approve_line(session, alice, "a1", "Alice line one")
        approve_line(session, bob, "b1", "Bob line one")

        assert bob_c.post("/api/leave", json={}).status_code == 200
        assert bob_c.get("/api/me").status_code == 401
        me = alice_c.get("/api/me").json()
        assert me["contributor_count"] == 1
        assert [l["id"] for l in me["lines"]] == ["a1"]
        assert alice_c.get("/api/notes/final").status_code == 409

        assert alice_c.post("/api/notes/finalize", json={}).status_code == 200
        r = alice_c.get("/api/notes/final")
        assert r.status_code == 200
        assert [l["id"] for l in r.json()["lines"]] == ["a1"]


def test_live_config_smoke():
    src = StubLiveSource()
    app = create_app("fake", source="livekit", live_source=src, autostart=False)
    with TestClient(app) as client:
        r = client.get("/api/config")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "livekit"
        assert body["url"] == src.url
        assert body["room"] == src.room_name


def test_live_load_pipeline_class_real_and_fake():
    from demo.live_session import load_pipeline_class
    real_cls, real_kind = load_pipeline_class("real")
    assert real_kind == "real" and real_cls.__module__ == "otr.pipeline"
    fake_cls, fake_kind = load_pipeline_class("fake")
    assert fake_kind == "fake" and fake_cls.__module__ == "demo.fake_pipeline"
