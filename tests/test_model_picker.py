"""The model picker: only the host machine may list and switch the local model."""
from fastapi.testclient import TestClient

from demo.server import create_app
from tests.test_demo import StubLiveSource


class FakeOllama:
    def __init__(self):
        self.model = "granite4.2:3b"
        self._cache = {"x": "y"}
        self.warmed = 0

    def installed(self):
        return ["granite4.2:3b", "qwen3.5:4b", "embeddinggemma:latest"]

    def warmup(self):
        self.warmed += 1
        return 0.1

    def complete(self, prompt, **kw):
        return "{}"


def make(llm):
    app = create_app("fake", source="livekit", live_source=StubLiveSource(), autostart=False, llm=llm)
    return app


def host(app):
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def test_host_sees_installed_models_without_embedding_models():
    llm = FakeOllama()
    with host(make(llm)) as c:
        body = c.get("/api/models").json()
    assert body["can_switch"] is True and body["active"] == "granite4.2:3b"
    assert body["installed"] == ["granite4.2:3b", "qwen3.5:4b"]


def test_host_can_switch_and_the_cache_is_cleared():
    llm = FakeOllama()
    with host(make(llm)) as c:
        r = c.post("/api/model", json={"model": "qwen3.5:4b"}, headers={"origin": "http://localhost"})
        assert r.status_code == 200 and r.json()["active"] == "qwen3.5:4b"
        assert c.post("/api/model", json={"model": "not-installed"}, headers={"origin": "http://localhost"}).status_code == 400
    assert llm.model == "qwen3.5:4b" and llm._cache == {}


def test_a_tunnelled_visitor_cannot_list_or_switch():
    llm = FakeOllama()
    with host(make(llm)) as c:
        h = {"X-Forwarded-For": "1.2.3.4", "host": "demo.ngrok-free.dev"}
        body = c.get("/api/models", headers=h).json()
        assert body == {"active": "granite4.2:3b", "can_switch": False, "installed": []}
        assert c.post("/api/model", json={"model": "qwen3.5:4b"}, headers=h).status_code == 403
    assert llm.model == "granite4.2:3b"


def test_no_model_configured():
    with host(make(None)) as c:
        assert c.get("/api/models").json() == {"active": None, "can_switch": False, "installed": []}
        assert c.post("/api/model", json={"model": "x"}).status_code == 403
