"""Edge key, egress ledger and loopback-only endpoints (demo/egress.py), through the real consent app."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from demo import egress
from demo.egress import ALLOWED_FIELDS, EdgeContext, classify, install_edge, walk_fields
from demo.server import create_app
from otr.types import Segment
from tests.test_demo import StubLiveSource

SECRET = "salary 150,000"
HELD_SECRET = "BLUEFALCON"
TUNNEL = {"x-forwarded-for": "203.0.113.9", "cf-connecting-ip": "203.0.113.9"}


def scope(client=("127.0.0.1", 5000), host="localhost:8765", **headers):
    hdrs = [(b"host", host.encode())] + [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return {"type": "http", "client": client, "headers": hdrs, "method": "GET", "path": "/"}


def make_app():
    return create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False)


def direct_client(app):
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


# ---------------------------------------------------------------- classification
@pytest.mark.parametrize("args,kind", [
    (dict(), "direct"),
    (dict(client=("::1", 1), host="[::1]:8765"), "direct"),
    (dict(client=("::ffff:127.0.0.1", 1)), "direct"),
    (dict(**{"X-Forwarded-For": "1.2.3.4"}), "tunnelled"),
    (dict(**{"CF-Connecting-IP": "1.2.3.4"}), "tunnelled"),
    (dict(Forwarded="for=1.2.3.4"), "tunnelled"),
    (dict(host="abc.trycloudflare.com"), "tunnelled"),        # loopback connector with no forwarding headers
    (dict(client=("8.8.8.8", 1)), "tunnelled"),
    (dict(client=("testclient", 1)), "tunnelled"),
    (dict(client=None), "tunnelled"),
    (dict(client=("192.168.1.20", 1), host="192.168.1.2:8765"), "lan"),
    (dict(client=("192.168.1.20", 1), **{"X-Forwarded-For": "1.2.3.4"}), "tunnelled"),
])
def test_classify(args, kind):
    assert classify(scope(**args)) == kind


# ---------------------------------------------------------------- internal endpoints are loopback only
def test_internal_endpoints_reject_tunnel_traffic_and_return_only_counts():
    app = make_app()
    with direct_client(app) as local, TestClient(app, headers=TUNNEL) as remote:
        created = local.post("/api/meetings", json={"name": "Alice Secretname", "email": "a@example.test"})
        assert created.status_code == 200
        for path in ("/api/_internal/activity", "/api/_internal/egress"):
            assert remote.get(path).status_code == 404
            assert TestClient(app, client=("8.8.8.8", 1)).get(path).status_code == 404
            assert local.get(path, headers=TUNNEL).status_code == 404         # forwarding header on a loopback socket
            assert local.get(path, headers={"Forwarded": "for=1.1.1.1"}).status_code == 404
        assert remote.post("/api/_internal/service", json={"state": "READY"}).status_code == 404
        act = local.get("/api/_internal/activity")
        assert act.status_code == 200
        body = act.json()
        assert body["active_meetings"] == 1 and body["participants"] == 1
        assert set(body) == {"active_meetings", "participants", "open_streams",
                             "seconds_since_last_request", "whisper_loaded", "service_state"}
        text = act.text
        assert "Alice" not in text and created.json()["identity"] not in text and "example.test" not in text


def test_activity_clock_ignores_health_internal_and_static():
    app = make_app()
    with direct_client(app) as local:
        edge = app.state.edge
        edge.activity.last_request -= 500
        local.get("/api/health")
        local.get("/api/_internal/activity")
        local.get("/static/live.css")
        assert local.get("/api/_internal/activity").json()["seconds_since_last_request"] >= 499
        local.get("/api/categories")
        assert local.get("/api/_internal/activity").json()["seconds_since_last_request"] < 5


# ---------------------------------------------------------------- edge key
def test_edge_key_required_for_tunnelled_requests_only(monkeypatch):
    monkeypatch.setenv("OTR_EDGE_KEY", "k-correct-horse")
    app = make_app()
    body = {"name": "Host", "email": "h@example.test"}
    with TestClient(app, headers=TUNNEL) as remote, direct_client(app) as local:
        assert remote.post("/api/meetings", json=body).status_code == 401
        assert remote.post("/api/meetings", json=body, headers={"X-OTR-Edge-Key": "wrong"}).status_code == 401
        assert remote.get("/api/categories").status_code == 401
        assert remote.get("/").status_code == 401
        # exempt: health and static assets
        assert remote.get("/api/health").status_code == 200
        assert remote.get("/static/live.css").status_code == 200
        ok = remote.post("/api/meetings", json=body, headers={"X-OTR-Edge-Key": "k-correct-horse"})
        assert ok.status_code == 200
        # direct loopback is unaffected
        assert local.post("/api/meetings", json=body).status_code == 200
        assert local.get("/api/categories").status_code == 200
        # the 401 reveals nothing
        assert remote.get("/api/categories").json() == {"detail": "Edge key required"}


def test_edge_key_unset_changes_nothing():
    app = make_app()
    with TestClient(app, headers=TUNNEL) as remote:
        assert remote.get("/api/categories").status_code == 200


def test_edge_key_uses_constant_time_compare(monkeypatch):
    seen = []
    real = egress.hmac.compare_digest
    monkeypatch.setattr(egress.hmac, "compare_digest", lambda a, b: seen.append((a, b)) or real(a, b))
    monkeypatch.setenv("OTR_EDGE_KEY", "abc")
    assert egress.edge_key_ok({"x-otr-edge-key": "abc"}, "POST", "/api/x")
    assert not egress.edge_key_ok({"x-otr-edge-key": "abd"}, "POST", "/api/x")
    assert not egress.edge_key_ok({}, "POST", "/api/x")
    assert len(seen) == 3


# ---------------------------------------------------------------- egress ledger with a scripted meeting
def run_meeting(host, guest, app):
    """Create, admit, speak, keep out and finalize. Returns every response body that crossed the wire."""
    seen = []
    keep = lambda r: (seen.append(r.text), r)[1]  # noqa: E731
    created = keep(host.post("/api/meetings", json={"name": "Host", "email": "h@example.test"})).json()
    room, ident = created["room_id"], created["identity"]
    keep(guest.post(f"/api/meetings/{room}/request", json={"name": "Guest", "email": "g@example.test"}))
    pending = keep(host.get(f"/api/meetings/{room}/status")).json()["pending"]
    keep(host.post(f"/api/meetings/{room}/admit", json={"request_id": pending[0]["request_id"]}))
    gstatus = keep(guest.get(f"/api/meetings/{room}/status")).json()
    gid = gstatus["identity"]
    keep(host.post("/api/consent", json={"recording": True}))
    keep(guest.post("/api/consent", json={"recording": True}))
    live = app.state.meetings[room]["session"]
    # Host says an ordinary line (approved) and then a salary line (kept out).
    live.push(Segment("h1", ident, "Plan the launch", 0, 0))
    live._publish_events(ident, live.pipes[ident].tick(100))
    live.push(Segment("h2", ident, "my " + SECRET, 1, 1))
    # Guest has a line still in the hold buffer when everything is read.
    live.push(Segment("g1", gid, "project codename " + HELD_SECRET, 2, 2))
    # A reason field that carries the secret exists server side; it must never be serialised.
    for owner in live.kept_out.values():
        for rec in owner.values():
            rec["reason"] = "kw:salary " + SECRET
            rec["text"] = SECRET
    for who in (host, guest):
        for path in ("/api/me", "/api/me?summary=1", "/api/diagnostics", "/api/config", "/api/categories",
                     f"/api/meetings/{room}/status", "/api/health"):
            keep(who.get(path))
    keep(host.post("/api/notes/finalize"))
    keep(host.get("/api/notes/final"))
    keep(host.post("/api/notes/email-opt-in", json={"enabled": True, "email": "h@example.test"}))
    keep(host.get(f"/api/meetings/{room}/mail-recipients"))
    for m in live.messages:                       # what /stream would send, per viewer
        for viewer in (ident, gid):
            v = live.visible_message(viewer, m)
            if v:
                seen.append(json.dumps(v))
    seen.append(json.dumps(live.visible_message(ident, {"type": "status", "owner": ident})))
    return seen, room


def test_scripted_meeting_leaks_no_secret_and_no_field_outside_the_allowlist():
    app = make_app()
    with TestClient(app, headers=TUNNEL) as host, TestClient(app, headers=TUNNEL) as guest, \
            direct_client(app) as local:
        seen, room = run_meeting(host, guest, app)
        blob = "\n".join(seen)
        assert SECRET not in blob and HELD_SECRET not in blob and "150,000" not in blob
        assert "Plan the launch" in blob                        # the approved line did cross
        ledger = local.get("/api/_internal/egress").json()
        assert ledger["totals"]["violations"] == 0, ledger["violations"]
        assert ledger["totals"]["requests"] >= 20 and ledger["totals"]["response_bytes"] > 1000
        routes = {r["route"]: r for r in ledger["routes"]}
        assert "POST /api/meetings" in routes and "GET /api/me" in routes
        assert "GET /api/meetings/{id}/status" in routes        # ids are normalised out of the key
        assert all(room not in r["route"] for r in ledger["routes"])
        every_field = {f for r in ledger["routes"] for f in r["fields"]}
        assert every_field and every_field <= ALLOWED_FIELDS
        # The ledger holds field paths only.
        dump = json.dumps(ledger)
        for needle in (SECRET, HELD_SECRET, "Plan the launch", "Host", "h@example.test", room):
            assert needle not in dump
        assert "lines[].text" in every_field and "kept_out[].category" in every_field


def test_direct_loopback_traffic_is_not_ledgered():
    app = make_app()
    with direct_client(app) as local:
        local.post("/api/meetings", json={"name": "Host", "email": "h@example.test"})
        assert local.get("/api/_internal/egress").json()["totals"]["requests"] == 0


def test_allowlist_is_deny_by_default():
    seen, bad = walk_fields({"identity": "x", "lines": [{"id": "1", "text": "t", "reason": "r"}],
                             "kept_out": [{"id": "1", "category": "c", "seq": 1, "raw": "r"}]})
    assert bad == {"lines[].reason", "kept_out[].raw"}
    _, bad = walk_fields({"participants": {"not an identity": {"name": "n"}}})
    assert bad == {"participants.<invalid key>"}                # the key itself is never recorded
    _, bad = walk_fields({"participants": {"person-" + "a" * 32: {"name": "n", "recording": True}}})
    assert not bad


def probe_app(payload):
    app = FastAPI()

    @app.get("/probe")
    async def probe():
        return JSONResponse(payload)

    @app.get("/sse")
    async def sse():
        async def gen():
            yield 'data: {"type": "status", "approved": 1}\n\n'
            yield 'data: {"type": "status", "reason": "' + SECRET + '"}\n\n'
            yield 'data: {"type": "status", "approved": 2}\n\n'
        return StreamingResponse(gen(), media_type="text/event-stream")

    ctx = install_edge(app, EdgeContext(meetings={}))
    return app, ctx


def test_audit_mode_logs_and_counts_but_passes(capsys, monkeypatch):
    monkeypatch.delenv("OTR_EGRESS_ENFORCE", raising=False)
    app, ctx = probe_app({"identity": "x", "reason": SECRET})
    with TestClient(app, headers=TUNNEL) as c:
        r = c.get("/probe")
        assert r.status_code == 200 and SECRET in r.text
    snap = ctx.ledger.snapshot(False)
    assert snap["violations"] == {"reason": 1} and snap["totals"]["blocked"] == 0
    err = capsys.readouterr().err
    assert "[egress] GET /probe" in err and "reason" in err and SECRET not in err


def test_enforce_mode_blocks_with_500_and_clear_log(capsys, monkeypatch):
    monkeypatch.setenv("OTR_EGRESS_ENFORCE", "1")
    app, ctx = probe_app({"identity": "x", "reason": SECRET})
    with TestClient(app, headers=TUNNEL) as c:
        r = c.get("/probe")
        assert r.status_code == 500 and SECRET not in r.text
        assert r.json() == {"detail": "Blocked by egress policy"}
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 9)) as direct:
            assert direct.get("/probe").status_code == 200       # not a tunnelled request
    assert ctx.ledger.snapshot(True)["totals"]["blocked"] == 1
    assert "not on the allowlist: reason" in capsys.readouterr().err


def test_enforce_mode_cuts_an_event_stream_at_the_bad_message(monkeypatch):
    monkeypatch.setenv("OTR_EGRESS_ENFORCE", "1")
    app, ctx = probe_app({})
    with TestClient(app, headers=TUNNEL) as c:
        text = c.get("/sse").text
    assert '"approved": 1' in text and SECRET not in text and '"approved": 2' not in text
    assert ctx.ledger.snapshot(True)["violations"] == {"reason": 1}


# ---------------------------------------------------------------- service mode surfaces
def test_diagnostics_carries_service_state_only_in_service_mode(monkeypatch):
    from otr.service import GATE
    app = make_app()
    with direct_client(app) as c:
        c.post("/api/meetings", json={"name": "Host", "email": "h@example.test"})
        assert "service" not in c.get("/api/diagnostics").json()
    monkeypatch.setenv("OTR_SERVICE", "1")
    app = make_app()
    old = (GATE.state, GATE.model_loaded)
    try:
        with direct_client(app) as c:
            c.post("/api/meetings", json={"name": "Host", "email": "h@example.test"})
            d = c.get("/api/diagnostics").json()
            assert d["service"] == {"state": "SLEEPING", "model_loaded": False, "idle_seconds": d["service"]["idle_seconds"]}
            assert c.post("/api/_internal/service", json={"state": "READY", "model_loaded": True}).status_code == 200
            d = c.get("/api/diagnostics").json()
            assert d["service"]["state"] == "READY" and d["service"]["model_loaded"] is True
            assert d["models"]["llm"]["warm"] is True
            assert c.post("/api/_internal/service", json={"state": "bogus"}).json()["service"]["state"] == "READY"
    finally:
        GATE.state, GATE.model_loaded = old


def test_capture_stop_turns_notes_off_for_everyone(monkeypatch):
    monkeypatch.setenv("OTR_SERVICE", "1")
    app = make_app()
    with direct_client(app) as c:
        room = c.post("/api/meetings", json={"name": "Host", "email": "h@example.test"}).json()["room_id"]
        c.post("/api/consent", json={"recording": True})
        src = app.state.meetings[room]["session"].source
        assert any(src.consent_snapshot().values())
        assert c.post("/api/_internal/service", json={"capture": False}).status_code == 200
        assert not any(src.consent_snapshot().values())


def test_health_route_is_available_and_minimal():
    app = make_app()
    with TestClient(app, headers=TUNNEL) as c:
        r = c.get("/api/health")
        assert r.status_code == 200 and r.json() == {"ok": True}
