import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demo import categories
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
        assert r.status_code == 200 and "Insights" in r.text
        assert "Presenter mode" in r.text and "pendcard" in r.text


def test_index_has_progressive_disclosure_levels():
    with TestClient(create_app("fake", autostart=False)) as c:
        r = c.get("/")
        assert r.status_code == 200
        for marker in ('id="tiles"', 'id="captions"', 'id="status-pill"', 'id="tab-insights"',
                       'id="tab-explain"', 'id="view-insights"', 'id="view-explain"', 'id="live-btn"',
                       'id="settings-menu"', 'id="banner"', "Keep that out of the notes?"):
            assert marker in r.text, marker
        # the overview renders no private text: only placeholder chips; the shared views are served
        assert c.get("/static/views.js").status_code == 200 and c.get("/static/views.css").status_code == 200
        assert "Show text" in c.get("/static/views.js").text


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
    api_secret = "otr-dev-secret-change-me-0123456789abcdef"

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
        home = client.get("/").text
        assert "Start or join a meeting" in home and 'id="notes-button"' in home
        assert "Notes stay off for you until you turn them on." in client.get("/live").text
        assert "Notes stay off for you until you turn them on." in client.get("/live.html").text
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


def test_new_meeting_defers_capture_until_a_speaker_consents(monkeypatch):
    started = []
    monkeypatch.setattr(LiveSession, "start", lambda self: started.append(self))
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=True)
    with TestClient(app) as host:
        assert started == [app.state.session]  # legacy single-room session
        created = host.post("/api/meetings", json={"name": "Host", "email": "host@example.test"})
        assert created.status_code == 200
        assert started == [app.state.session]
        assert host.post("/api/meetings/" + created.json()["room_id"] + "/end").status_code == 200
        assert started == [app.state.session]
        host.post("/api/meetings", json={"name": "Host", "email": "host@example.test"})
        assert host.post("/api/consent", json={"recording": True}).status_code == 200
        assert len(started) == 2


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


def test_public_demo_meeting_limit_releases_slot_on_end(monkeypatch):
    monkeypatch.setenv("OTR_MAX_ACTIVE_MEETINGS", "1")
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    body = {"name": "Host", "email": "host@example.test"}
    with TestClient(app) as host, TestClient(app) as other:
        first = host.post("/api/meetings", json=body)
        assert first.status_code == 200
        assert other.post("/api/meetings", json=body).status_code == 429
        assert len(app.state.meetings) == 1
        assert host.post("/api/meetings/" + first.json()["room_id"] + "/end").status_code == 200
        assert other.post("/api/meetings", json=body).status_code == 200


def test_diagnostics_requires_meeting_session_even_from_loopback():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    # A reverse proxy uses a loopback connection to the app for remote visitors.
    # That socket address alone must not unlock a cross-room operator view.
    with TestClient(app, client=("127.0.0.1", 50000)) as visitor, TestClient(app) as host:
        room = host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"}).json()["room_id"]
        assert visitor.get("/api/diagnostics").status_code == 401
        response = host.get("/api/diagnostics")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"models", "me", "hold_seconds"}
        assert "participants" not in body and "room" not in body


def test_insights_popout_is_served_with_the_strict_csp_and_no_store():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as client:
        page = client.get("/insights")
        assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
        html = page.text
        assert "default-src 'self'; script-src 'self'; style-src 'self'" in html
        assert 'id="tab-how"' in html and 'id="kinds"' in html and 'id="events"' in html and 'id="timeline"' in html
        import re
        assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)
        for path in ("/static/insights.js", "/static/insights.css", "/static/views.js", "/static/categories.js"):
            assert client.get(path).status_code == 200, path
        assert client.get("/m/anything/insights").status_code == 200
        assert client.get("/insights.html").status_code == 404
        # the page itself carries no meeting data; the data endpoints need a session
        assert client.get("/api/me").status_code == 401 and client.get("/api/diagnostics").status_code == 401


def test_public_demo_pending_request_limit_frees_slots(monkeypatch):
    monkeypatch.setenv("OTR_MAX_PENDING_JOIN_REQUESTS", "1")
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as host, TestClient(app) as first, TestClient(app) as second:
        room = host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"}).json()["room_id"]
        endpoint = "/api/meetings/" + room + "/request"
        body = {"name": "Guest", "email": "g@example.test"}
        requested = first.post(endpoint, json=body)
        assert requested.status_code == 200
        assert second.post(endpoint, json=body).status_code == 429
        assert len(host.get("/api/meetings/" + room + "/status").json()["pending"]) == 1
        assert first.post("/api/meetings/" + room + "/cancel").status_code == 200
        requested = second.post(endpoint, json=body)
        assert requested.status_code == 200
        assert host.post("/api/meetings/" + room + "/deny",
                         json={"request_id": requested.json()["request_id"]}).status_code == 200
        assert first.post(endpoint, json=body).status_code == 200


def test_me_summary_omits_approved_text_without_changing_full_view():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as host:
        created = host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"}).json()
        live = app.state.meetings[created["room_id"]]["session"]
        live.approved["line-1"] = {"id": "line-1", "name": "Host", "text": "Approved private line"}
        live.line_owner["line-1"] = created["identity"]
        host.post("/api/consent", json={"recording": True})
        full = host.get("/api/me").json()
        summary = host.get("/api/me?summary=1").json()
        assert full["lines"][0]["text"] == "Approved private line"
        assert "lines" not in summary
        assert summary == {key: value for key, value in full.items() if key != "lines"}
        assert "Approved private line" not in json.dumps(summary)


@pytest.mark.parametrize("path,body", [
    ("/api/notes/remove", {"id": "line-1"}),
    ("/api/notes/finalize", {}),
    ("/api/leave", {}),
])
def test_live_mutations_reject_foreign_origin(path, body):
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as host:
        host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"})
        assert host.post(path, json=body, headers={"origin": "https://evil.example"}).status_code == 403


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


def test_public_frontend_origin_is_explicitly_allowlisted(monkeypatch):
    public = "https://consentmeeting.vercel.app"
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as browser:
        body = {"name": "Host", "email": "host@example.test"}
        assert browser.post("/api/meetings", json=body, headers={"origin": public}).status_code == 403
        monkeypatch.setenv("OTR_PUBLIC_ORIGIN", public)
        created = browser.post("/api/meetings", json=body, headers={"origin": public})
        assert created.status_code == 200
        assert created.json()["join_url"].startswith(public + "/m/")
        room = created.json()["room_id"]
        assert browser.post("/api/meetings/" + room + "/end",
                            headers={"origin": public + ".evil"}).status_code == 403
        assert browser.post("/api/meetings/" + room + "/end",
                            headers={"origin": "https://other.example"}).status_code == 403
        assert browser.get("/api/meetings/" + room + "/status").status_code == 200
        assert browser.post("/api/meetings/" + room + "/end",
                            headers={"origin": public}).status_code == 200


def test_public_frontend_referer_selects_room_specific_cookie(monkeypatch):
    public = "https://consentmeeting.vercel.app"
    monkeypatch.setenv("OTR_PUBLIC_ORIGIN", public)
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as browser:
        first = browser.post("/api/meetings", json={"name": "First", "email": "one@example.test"}).json()
        second = browser.post("/api/meetings", json={"name": "Second", "email": "two@example.test"}).json()
        first_page = {"referer": public + "/m/" + first["room_id"] + "?view=notes"}
        second_page = {"referer": public + "/m/" + second["room_id"]}
        assert browser.get("/api/me", headers=first_page).json()["identity"] == first["identity"]
        assert browser.get("/api/me", headers=second_page).json()["identity"] == second["identity"]
        assert browser.get("/api/me", headers={"referer": "http://["}).status_code == 200
        assert browser.post("/api/consent", json={"recording": True},
                            headers={**first_page, "origin": public}).status_code == 200
        assert app.state.meetings[first["room_id"]]["session"].source.consent_snapshot()[first["identity"]] is True
        assert app.state.meetings[second["room_id"]]["session"].source.consent_snapshot()[second["identity"]] is False


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


def test_email_signup_requires_own_finalization_and_keeps_addresses_private():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as host, TestClient(app) as guest, TestClient(app) as outsider:
        room = host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"}).json()["room_id"]
        waiting = guest.post("/api/meetings/" + room + "/request",
                             json={"name": "Guest", "email": "g@example.test"}).json()
        assert guest.post("/api/notes/email-opt-in",
                          json={"email": "g@example.test", "enabled": True}).status_code == 403
        host.post("/api/meetings/" + room + "/admit", json={"request_id": waiting["request_id"]})
        before = guest.get("/api/me").json()
        assert before["delivery_email"] == "g@example.test"
        assert before["email_opted_in"] is False
        assert "h@example.test" not in json.dumps(before)
        assert guest.post("/api/notes/email-opt-in",
                          json={"email": "g@example.test", "enabled": True}).status_code == 409
        assert host.get("/api/meetings/" + room + "/mail-recipients").status_code == 409
        assert guest.get("/api/meetings/" + room + "/mail-recipients").status_code == 403
        assert outsider.get("/api/meetings/" + room + "/mail-recipients").status_code == 401

        guest.post("/api/notes/finalize", json={})
        for invalid in ("person@example.test\r\nBcc:leak@example.test", "bad address@example.test",
                        "person@example.test?subject=x", "a@localhost", "x" * 255):
            assert guest.post("/api/notes/email-opt-in",
                              json={"email": invalid, "enabled": True}).status_code == 400
        assert guest.post("/api/notes/email-opt-in",
                          json={"email": "g@example.test", "enabled": "true"}).status_code == 400
        selected = guest.post("/api/notes/email-opt-in",
                              json={"email": "guest+final@example.test", "enabled": True})
        assert selected.json() == {"email": "guest+final@example.test", "enabled": True}
        assert "no-store" in selected.headers["cache-control"]
        assert guest.get("/api/me").json()["email_opted_in"] is True
        assert "guest+final@example.test" not in json.dumps(host.get("/api/me").json())


def test_final_email_recipients_dedupe_opt_out_departure_and_end_purge():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as host, TestClient(app) as first, TestClient(app) as second:
        room = host.post("/api/meetings", json={"name": "Host", "email": "host@example.test"}).json()["room_id"]
        for client, name in ((first, "First"), (second, "Second")):
            waiting = client.post("/api/meetings/" + room + "/request",
                                  json={"name": name, "email": name.lower() + "@example.test"}).json()
            host.post("/api/meetings/" + room + "/admit", json={"request_id": waiting["request_id"]})
        live = app.state.meetings[room]["session"]
        host_id = host.get("/api/me").json()["identity"]
        live.approved["line-1"] = {"id": "line-1", "speaker": host_id, "name": "Host", "text": "Safe notes"}
        live.line_owner["line-1"] = host_id
        for client in (host, first, second):
            assert client.post("/api/notes/finalize", json={}).status_code == 200
        assert host.get("/api/meetings/" + room + "/mail-recipients").json() == {"recipients": []}
        host.post("/api/notes/email-opt-in", json={"email": "same@example.test", "enabled": True})
        first.post("/api/notes/email-opt-in", json={"email": "SAME@example.test", "enabled": True})
        second.post("/api/notes/email-opt-in", json={"email": "second@example.test", "enabled": True})
        assert first.post("/api/leave").status_code == 200
        response = host.get("/api/meetings/" + room + "/mail-recipients")
        assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
        assert response.json() == {"recipients": [
            {"name": "Host", "email": "same@example.test"},
            {"name": "Second", "email": "second@example.test"}]}
        assert "Safe notes" not in response.text
        host.post("/api/notes/email-opt-in", json={"email": "same@example.test", "enabled": False})
        assert host.get("/api/meetings/" + room + "/mail-recipients").json() == {"recipients": [
            {"name": "First", "email": "SAME@example.test"},
            {"name": "Second", "email": "second@example.test"}]}
        second.post("/api/notes/email-opt-in", json={"email": "second@example.test", "enabled": False})
        assert host.get("/api/meetings/" + room + "/mail-recipients").json() == {
            "recipients": [{"name": "First", "email": "SAME@example.test"}]}
        assert host.post("/api/meetings/" + room + "/end").status_code == 200
        assert live.delivery == {}
        assert host.get("/api/meetings/" + room + "/mail-recipients").status_code == 401


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


def test_live_config_and_replay_mode_detection():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as client:
        cfg = client.get("/api/config").json()
        assert cfg["mode"] == "livekit" and cfg["room"] == "demo"
        assert [c["key"] for c in cfg["categories"]] == categories.KEYS
        assert client.get("/static/livekit-client.umd.js").status_code == 200
        assert client.get("/static/not-a-file.js").status_code == 404
        # the server picks the page: consent mode serves the lobby / admission / three-view page at "/"
        assert 'id="create-button"' in client.get("/").text
    # replay and shared-stream modes serve the operator console and have no /api/config
    with TestClient(create_app("fake", autostart=False)) as client:
        assert client.get("/api/config").status_code == 404
        assert 'id="view-tabs"' in client.get("/").text


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
            {"type": "snapshot", "lines": session.shared_lines_for(viewer)}]
    for message in session.messages[since if since is not None else len(session.messages):]:
        visible = session.visible_message(viewer, message)
        if visible is not None:
            msgs.append(visible)
    return msgs


def test_live_two_clients_share_approved_lines_but_keep_statuses_private():
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
        assert [l["id"] for l in me_a["lines"]] == ["a1", "b1"]  # sensitive pause turns off capture, not viewing
        assert [l["id"] for l in me_b["lines"]] == ["a1", "b1"]
        assert "Alice launch plan" in json.dumps(me_a)
        assert me_b["lines"][1]["text"] == "Bob budget notes"
        # others expose only name + notes on/off; own status may expose the pause flag
        assert "sensitive_paused" not in me_b["participants"][alice]
        assert me_a["participants"][alice]["sensitive_paused"] is True
        assert me_a["participants"][bob] == {"name": "Bob", "recording": True}
        assert me_b["participants"][alice] == {"name": "Alice", "recording": False}


def test_live_stream_shares_approved_lines_but_not_withheld_text():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c:
        alice = join_as(alice_c, "Alice")
        alice_c.post("/api/consent", json={"recording": True})
        session.names["bob"] = "Bob"
        session.set_consent("bob", True)
        approve_line(session, alice, "a1", "Alice line one")
        approve_line(session, "bob", "b1", "Bob approved one")

        msgs = live_stream_messages(session, alice)
        body = json.dumps(msgs)
        assert "Alice line one" in body
        assert "Bob approved one" in body and '"id": "b1"' in body
        snap = next(m for m in msgs if m["type"] == "snapshot")
        assert [l["id"] for l in snap["lines"]] == ["a1", "b1"]

        start = len(session.messages)
        approve_line(session, "bob", "b2", "Bob approved two")
        approve_line(session, alice, "a2", "Alice line two")
        live_msgs = live_stream_messages(session, alice, start)
        body = json.dumps(live_msgs)
        assert "Alice line two" in body
        assert "Bob approved two" in body and '"id": "b2"' in body


def test_live_stream_late_join_sees_approved_room_lines_with_notes_off():
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
        assert "Alice early line" in body and '"id": "a1"' in body
        snap = next(m for m in msgs if m["type"] == "snapshot")
        assert [line["id"] for line in snap["lines"]] == ["a1"]
        assert [line["id"] for line in bob_c.get("/api/me").json()["lines"]] == ["a1"]
        assert [line["id"] for line in next(m for m in live_stream_messages(session, bob)
                                                   if m["type"] == "snapshot")["lines"]] == ["a1"]


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

        bob_c.post("/api/consent", json={"recording": False})
        start = len(session.messages)
        assert alice_c.post("/api/notes/remove", json={"id": "a1"}).status_code == 200
        live_msgs = live_stream_messages(session, alice, start)
        removed = [m for m in live_msgs if m["type"] == "transcript"]
        assert any(c["kind"] == "removed" and c["id"] == "a1" for m in removed for c in m["changes"])
        assert [line["id"] for line in alice_c.get("/api/me").json()["lines"]] == ["b1"]
        bob_msgs = live_stream_messages(session, bob, start)
        assert any(c["kind"] == "removed" and c["id"] == "a1"
                   for m in bob_msgs if m["type"] == "transcript" for c in m["changes"])
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
        assert [line["id"] for line in me["lines"]] == ["a1"]
        assert alice not in session.pipes  # held text discarded
        assert client.post("/api/notes/finalize", json={}).status_code == 200  # idempotent
        assert client.post("/api/consent", json={"recording": True}).status_code == 409
        assert client.post("/api/consent", json={"recording": False}).status_code == 200
        session.push(Segment("late", alice, "Alice late line", 3, 3))
        assert [line["id"] for line in client.get("/api/me").json()["lines"]] == ["a1"]


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


def test_live_shared_text_requires_admission_but_not_viewer_notes():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c, TestClient(app) as bob_c, TestClient(app) as outsider:
        alice, bob = join_as(alice_c, "Alice"), join_as(bob_c, "Bob")
        alice_c.post("/api/consent", json={"recording": True})
        approve_line(session, alice, "a1", "Approved agenda")
        assert outsider.get("/api/me").status_code == 401
        assert outsider.get("/stream").status_code == 401
        assert [line["id"] for line in bob_c.get("/api/me").json()["lines"]] == ["a1"]
        assert "Approved agenda" in json.dumps(live_stream_messages(session, bob))

        bob_c.post("/api/consent", json={"recording": True})
        assert [line["id"] for line in bob_c.get("/api/me").json()["lines"]] == ["a1"]
        assert "Approved agenda" in json.dumps(live_stream_messages(session, bob))
        bob_c.post("/api/consent", json={"recording": False})
        assert [line["id"] for line in bob_c.get("/api/me").json()["lines"]] == ["a1"]
        assert "Approved agenda" in json.dumps(live_stream_messages(session, bob))
        assert session.visible_message(bob, {"type": "transcript", "changes": [
            {"kind": "committed", "owner": alice, "line": session.approved["a1"]}]})["changes"][0]["line"]["id"] == "a1"
        # Pausing Alice stops future capture; her earlier approved line remains
        # available to every admitted viewer until she explicitly removes it.
        alice_c.post("/api/consent", json={"recording": False})
        assert [line["id"] for line in bob_c.get("/api/me").json()["lines"]] == ["a1"]
        session.push(Segment("off", alice, "Alice is off record", 3, 3))
        assert "Alice is off record" not in json.dumps(bob_c.get("/api/me").json())
        assert "Alice is off record" not in json.dumps(live_stream_messages(session, bob))
        assert alice_c.get("/api/me?summary=1").json().get("lines") is None


def test_hosted_room_shares_approved_lines_after_admission_with_notes_off():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(),
                     autostart=False, hold_seconds=0)
    with TestClient(app) as host, TestClient(app) as guest:
        created = host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"}).json()
        room = created["room_id"]
        live = app.state.meetings[room]["session"]
        requested = guest.post(f"/api/meetings/{room}/request",
                               json={"name": "Guest", "email": "g@example.test"}).json()
        assert guest.get("/api/me").status_code == 403
        assert guest.get("/stream").status_code == 403
        assert host.post(f"/api/meetings/{room}/admit",
                         json={"request_id": requested["request_id"]}).status_code == 200
        host.post("/api/consent", json={"recording": True})
        approve_line(live, created["identity"], "host-1", "Approved project update")
        assert [line["id"] for line in guest.get("/api/me").json()["lines"]] == ["host-1"]
        guest_identity = guest.get(f"/api/meetings/{room}/status").json()["identity"]
        assert "Approved project update" in json.dumps(live_stream_messages(live, guest_identity))


def test_live_withheld_and_retracted_text_never_reaches_other_viewer():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c, TestClient(app) as bob_c:
        alice, bob = join_as(alice_c, "Alice"), join_as(bob_c, "Bob")
        alice_c.post("/api/consent", json={"recording": True})
        bob_c.post("/api/consent", json={"recording": True})
        session.push(Segment("held", alice, "A draft line", 0, 0))
        assert "A draft line" not in json.dumps(bob_c.get("/api/me").json())
        assert "A draft line" not in json.dumps(live_stream_messages(session, bob))
        session.push(Segment("sensitive", alice, "Her salary is 150,000", 0.01, 0.01))
        for payload in (bob_c.get("/api/me").json(), live_stream_messages(session, bob)):
            body = json.dumps(payload)
            assert "A draft line" not in body and "150,000" not in body
            assert '"id": "sensitive"' not in body and '"id": "held"' not in body
        assert session.source.consent_snapshot()[bob] is True


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


def static_text(name):
    return (Path(__file__).resolve().parent.parent / "demo" / "static" / name).read_text(encoding="utf-8")


def test_live_page_is_lances_meeting_page_with_our_features_added():
    html, js, css = static_text("live.html"), static_text("live.js"), static_text("live.css")
    # The current meeting page owns the root route and has entry, lobby, call,
    # transcript, and end-meeting controls.
    for marker in ('id="home-screen"', 'id="create-button"', 'id="host-setup"', 'id="guest-setup"', 'id="waiting-screen"',
                   'id="share-screen"', 'id="host-lobby"', 'id="tile-grid"', 'id="mic-button"', 'id="camera-button"',
                   'id="notes-button"', 'id="notes-control"', 'id="leave-button"', 'id="agent-button"',
                   'id="side-panel"', 'id="captions"', 'id="transcript-status"',
                   'id="finalize-button"', 'id="email-choice"', 'id="end-dialog"', 'id="share-meeting-link-button"'):
        assert marker in html, marker
    # Privacy and device diagnostics remain available within the meeting UI.
    for marker in ('id="link-insights"', 'id="link-explain"', 'id="device-menu"',
                   'id="menu-meter"', 'id="check-meter"', 'id="check-mic"', 'id="check-cam"', 'id="engine"',
                   'id="engine-input"', "/static/categories.js", "/static/views.js"):
        assert marker in html, marker
    for gone in ('id="view-tabs"', 'id="tab-realtime"', 'id="status-pill"'):
        assert gone not in html, gone
    # strict CSP stays workable: no inline style attributes or inline event handlers in the consent page
    import re
    assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)
    assert "style-src 'self'" in html and "script-src 'self'" in html
    for marker in ("setMicrophoneEnabled", "ActiveSpeakersChanged", "/api/consent", "/api/leave", "/api/meetings",
                   "/api/diagnostics", "audioCaptureDefaults", "Not connected yet"):
        assert marker in js, marker
    # The consent page never offers a reveal or calls replay-only confirmation.
    assert "reveal:" not in js and "/api/confirm" not in js and "Reveal text" not in html


def test_meet_page_has_lobby_voice_and_one_side_panel():
    html, js = static_text("meet.html"), static_text("meet.js")
    for marker in ('id="create-button"', 'id="host-lobby"', 'id="camera-button"', 'id="mic-button"', 'id="notes-button"',
                   'id="captions-button"', 'id="leave-button"', 'id="people-button"', 'id="info-button"', 'id="agent-button"',
                   'id="side-panel"', 'id="panel-agent"', 'id="link-insights"', 'id="link-explain"', 'id="panel-back"',
                   'id="view-insights"', 'id="view-explain"', 'id="live-button"', 'id="captions"', 'id="stage-captions"',
                   "What was kept out", "How it decides", "/static/categories.js", "/static/views.js"):
        assert marker in html, marker
    # the agent is attached to the meeting: no tab bar, status pill, or presenter button on the stage
    for gone in ('id="view-tabs"', 'id="tab-realtime"', 'id="status-pill"', 'id="present-button"', "NOT RECORDING ME"):
        assert gone not in html, gone
    # strict CSP stays workable: no inline style attributes or inline event handlers in the consent page
    import re
    assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)
    assert "style-src 'self'" in html and "script-src 'self'" in html
    for marker in ("setMicrophoneEnabled", "ActiveSpeakersChanged", "/api/consent", "/api/join", "/api/leave",
                   "/api/me", "kept_out", "renderInsights", "renderExplain"):
        assert marker in js, marker
    # the consent page never offers a reveal, and never calls the replay-only confirm endpoint
    assert "reveal:" not in js and "/api/confirm" not in js and "Reveal text" not in html


def test_meet_page_is_served_as_separate_experimental_page():
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(app) as client:
        for path in ("/meet", "/meet.html"):
            r = client.get(path)
            assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
            assert "Back to the classic page" in r.text and "default-src 'self'; script-src 'self'" in r.text
        for path in ("/static/meet.js", "/static/meet.css"):
            assert client.get(path).status_code == 200
        home = client.get("/").text
        assert 'id="home-screen"' in home and 'id="notes-control"' in home
        assert 'id="side-panel"' in home and '/static/live.js' in home
        assert '/static/meet.js' not in home


def test_frontend_passes_ui_slop_audit():
    """No single-side accent borders, gradients, glass, glow, emoji, dashes or decorative motion (docs/UI_STYLE.md).

    live.html, live.css and live.js are Lance Streuber's own design and are deliberately not held to this audit
    (run `python scripts/ui_slop_audit.py` to list what it would flag there). Everything else we own is.
    """
    import subprocess
    import sys
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, str(root / "scripts" / "ui_slop_audit.py"), "--fail",
                        "--skip", "live.html", "--skip", "live.css", "--skip", "live.js"],
                       capture_output=True, text=True, cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_index_operator_console_has_three_views():
    html = static_text("index.html")
    for marker in ('id="tab-realtime"', 'id="tab-insights"', 'id="tab-explain"', 'id="view-insights"',
                   'id="view-explain"', 'id="live-btn"', 'id="status-pill"', 'id="pendcard"', "Presenter mode",
                   "/static/views.js", "/static/categories.js"):
        assert marker in html, marker
    # consent-mode machinery lives in live.html; the console has no mic, join or consent controls
    assert "setMicrophoneEnabled" not in html and "/api/join" not in html and "/api/consent" not in html


# ---------------------------------------------------------------- one taxonomy
@pytest.mark.parametrize("reason,kind,expected", [
    ("cue:off_the_record", "redacted", "off_record"),
    ("cue:between_us", "state_change", "off_record"),
    ("scope:off", "redacted", "off_record"),
    ("implicit_end:topic_shift", "state_change", "off_record"),
    ("flush:unresolved_scope", "redacted", "off_record"),
    ("cue:retro_meta", "redacted", "retracted"),
    ("cue:strike_that", "redacted", "retracted"),
    ("retro:match(keyword)", "retro_removed", "retracted"),
    ("retro:match(llm)", "redacted", "retracted"),
    ("", "retro_removed", "retracted"),
    ("kw:health", "pending_confirm", "personal_health"),
    ("llm:personal", "pending_confirm", "personal_health"),
    ("kw:salary", "pending_confirm", "pay_hr"),
    ("llm:hr", "pending_confirm", "pay_hr"),
    ("kw:layoffs", "pending_confirm", "pay_hr"),
    ("llm:legal", "pending_confirm", "legal_business"),
    ("llm:confidential", "pending_confirm", "legal_business"),
    ("presidio:EMAIL_ADDRESS,PHONE_NUMBER", "redacted", "contact"),
    ("regex:PII", "redacted", "contact"),
    ("hold_elapsed", "committed", "other"),
    ("flush:unconfirmed", "redacted", "other"),
    ("confirm:keep_out", "redacted", "other"),
    ("kw:something_new", "pending_confirm", "other"),
    ("totally:unknown", "redacted", "other"),
    ("", "redacted", "other"),
    (None, "redacted", "other"),
])
def test_taxonomy_maps_reason_codes(reason, kind, expected):
    assert categories.categorize(reason, kind) == expected


def test_taxonomy_is_one_table_with_seven_kinds_served_to_both_pages():
    assert categories.KEYS == ["retracted", "off_record", "contact", "personal_health", "pay_hr",
                               "legal_business", "other"]
    assert [categories.LABELS[k] for k in categories.KEYS] == [
        "Retracted by the speaker (strike that)", "Off the record (you asked)", "Contact details masked",
        "Personal and health", "Pay and HR", "Legal and confidential business", "Other sensitive"]
    prefix = "window.OTR_TAXONOMY = "
    with TestClient(create_app("fake", autostart=False)) as c:
        js = c.get("/static/categories.js")
        assert js.status_code == 200 and js.text.startswith(prefix)
        assert json.loads(js.text[len(prefix):].rstrip().rstrip(";")) == categories.taxonomy()
        assert c.get("/api/categories").json() == categories.taxonomy()
    live = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)
    with TestClient(live) as c:
        assert c.get("/static/categories.js").text == categories.js_source()


# ---------------------------------------------------------------- text-free status and insights
SECRET = "salary 150,000"


def walk_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from walk_strings(v)
    elif obj is not None:
        yield str(obj)


def test_live_status_messages_are_text_free_and_category_only():
    src = StubLiveSource()
    live = LiveSession(FakePipeline, "fake", src, hold_seconds=0)
    live.names.update({"alice": "Alice", "bob": "Bob"})
    live.set_consent("alice", True)
    live.set_consent("bob", True)
    live.push(Segment("s1", "alice", f"Her {SECRET}", 0, 0))   # sensitive hold -> pause
    live.push(Segment("b1", "bob", "Agenda item one", 0, 0))
    live._publish_events("bob", live.pipes["bob"].tick(1))
    live.push(Segment("b2", "bob", "bob@example.com is my email", 1, 1))   # masked contact detail
    seen_status = 0
    for who in ("alice", "bob"):
        for message in live.messages:
            visible = live.visible_message(who, message)
            if visible is None or visible["type"] not in {"status", "transcript"}:
                continue
            blob = json.dumps(visible)
            assert "150,000" not in blob and "salary" not in blob.lower() and "Her " not in blob
            if visible["type"] == "status":
                seen_status += 1
                assert who == message["owner"]
                allowed = {"approved", "kept_out", "total", "removed", "timeline", "now", "hold_seconds", "type"}
                assert set(visible) <= allowed
                assert set(visible["kept_out"]) <= set(categories.KEYS)
                assert all(isinstance(n, int) for n in visible["kept_out"].values())
                assert all(set(step) == {"t", "state"} for step in visible["timeline"])
    assert seen_status
    assert "150,000" not in json.dumps(live.messages)
    # the raw log holds only owner markers, no payload at all
    assert all(set(m) == {"type", "owner"} for m in live.messages if m["type"] == "status")


def test_live_insights_have_only_category_keys_and_counts():
    live = LiveSession(FakePipeline, "fake", StubLiveSource(), hold_seconds=0)
    live.names.update({"alice": "Alice", "bob": "Bob"})
    live.set_consent("alice", True)
    live.set_consent("bob", True)
    live.push(Segment("s1", "alice", f"Her {SECRET}", 0, 0))
    ins = live.insights_for("alice")
    assert ins["kept_out"] == {"pay_hr": 1} and ins["total"] == 1 and ins["approved"] == 0
    assert [step["state"] for step in ins["timeline"]] == ["recording", "paused"]
    assert live.insights_for("bob")["kept_out"] == {} and live.insights_for("bob")["total"] == 0
    for text in walk_strings(ins):
        assert "150,000" not in text and "salary" not in text.lower() and "Alice" not in text and text != "s1"
    # off the record is its own kind and its own timeline state
    live.push(Segment("b1", "bob", "off the record", 1, 1))
    live.push(Segment("b2", "bob", "the launch slipped", 2, 2))
    ins = live.insights_for("bob")
    assert ins["kept_out"] == {"off_record": 1} and ins["timeline"][-1]["state"] == "off_record"
    live.leave("alice")
    assert live.insights_for("alice")["kept_out"] == {} and "alice" not in live.kept_out


def test_live_kept_out_marker_has_generic_trail_without_text_and_goes_to_owner_only():
    live = LiveSession(FakePipeline, "fake", StubLiveSource(), hold_seconds=0)
    live.names.update({"alice": "Alice", "bob": "Bob"})
    live.set_consent("alice", True)
    live.set_consent("bob", True)
    live.push(Segment("s1", "alice", f"Her {SECRET}", 0, 0))
    chips = live.own_kept_out("alice")
    assert [c["id"] for c in chips] == ["s1"] and chips[0]["category"] == "pay_hr"
    assert set(chips[0]["trail"]) == {"family", "before", "after", "held_s"}
    assert chips[0]["trail"]["family"] == "llm" and chips[0]["trail"]["after"] == "PENDING_CONFIRM"
    assert live.own_kept_out("bob") == []
    changes = [c for m in live.messages if m["type"] == "transcript" for c in m["changes"] if c["kind"] == "kept_out"]
    assert len(changes) == 1 and changes[0]["owner"] == "alice"
    assert live.visible_message("bob", {"type": "transcript", "changes": changes}) is None
    assert "150,000" not in json.dumps(chips) + json.dumps(changes)


def test_live_stream_endpoints_expose_insights_without_text():
    app, _ = live_app()
    session = app.state.session
    with TestClient(app) as alice_c, TestClient(app) as bob_c:
        alice, bob = join_as(alice_c, "Alice"), join_as(bob_c, "Bob")
        alice_c.post("/api/consent", json={"recording": True})
        bob_c.post("/api/consent", json={"recording": True})
        session.push(Segment("s1", alice, f"Her {SECRET}", 0, 0))
        me_a, me_b = alice_c.get("/api/me").json(), bob_c.get("/api/me").json()
        assert me_a["insights"]["kept_out"] == {"pay_hr": 1}
        assert [c["category"] for c in me_a["kept_out"]] == ["pay_hr"]
        assert me_b["insights"]["kept_out"] == {} and me_b["kept_out"] == []
        for body in (json.dumps(me_a), json.dumps(me_b)):
            assert "150,000" not in body and "Her salary" not in body
        msgs = live_stream_messages(session, bob)
        assert "s1" not in json.dumps(msgs) and "pay_hr" not in json.dumps(msgs)


def test_live_consent_mode_has_no_reveal_or_confirm_surface():
    app, _ = live_app()
    with TestClient(app) as client:
        for path in ("/api/confirm", "/api/reveal", "/api/private", "/api/say"):
            assert client.post(path, json={}).status_code == 404
        assert "Reveal text" not in client.get("/").text
        assert "Reveal text" not in client.get("/static/live.js").text


def test_live_llm_is_passed_to_each_speaker_pipeline():
    class Spy(FakePipeline):
        def __init__(self, llm=None, hold_seconds=30.0):
            super().__init__(llm=llm, hold_seconds=hold_seconds)
            self.llm = llm
    marker = object()
    live = LiveSession(Spy, "fake", StubLiveSource(), hold_seconds=0, llm=marker)
    live.names["alice"] = "Alice"
    live.set_consent("alice", True)
    live.push(Segment("a1", "alice", "hello there", 0, 0))
    assert live.pipes["alice"].llm is marker


def test_build_llm_uses_parse_llm_spec_and_env_default(monkeypatch):
    import urllib.request
    from demo.server import build_llm
    from otr.llm import DEFAULT_MODEL
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: type("R", (), {"read": lambda self: b"{}"})())
    monkeypatch.delenv("OTR_LLM_MODEL", raising=False)
    assert build_llm("none") is None and build_llm("bogus:x") is None
    assert build_llm("ollama").model == DEFAULT_MODEL == "granite4.2:3b"
    assert build_llm("ollama:tiny:1b").model == "tiny:1b"
    monkeypatch.setenv("OTR_LLM_MODEL", "envmodel:7b")
    assert build_llm("ollama").model == "envmodel:7b"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert build_llm("ollama") is None


def test_warm_llm_runs_warmup_in_a_thread():
    import threading
    from demo.live_session import warm_llm
    seen = {}

    class Warm:
        def warmup(self):
            seen["thread"] = threading.current_thread().name
    t = warm_llm(Warm())
    t.join(2)
    assert seen["thread"] == "llm-warmup"
    assert warm_llm(None) is None and warm_llm(object()) is None


def test_live_js_dom_ids_all_exist_in_live_html():
    import re
    declared = set(re.findall(r'\bid="([^"]+)"', static_text("live.html")))
    used = set(re.findall(r'\$\("([^"]+)"\)', static_text("live.js")))
    assert used - declared == set(), used - declared
