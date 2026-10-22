"""OllamaLLM against a fake local Ollama (http.server thread); never touches the real one."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from otr.llm import (LLMError, OllamaLLM, classify_sensitivity, clean_reply, default_host,
                     default_model, extract_json, parse_llm_spec)


class Fake:
    def __init__(self):
        self.requests = []
        self.reply = {"response": '{"sensitive": true, "category": "health"}'}
        self.status = 200
        self.delay = 0.0
        self.reject_think = False
        self.conn_ids = set()


@pytest.fixture
def fake():
    st = Fake()

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))
            st.requests.append(body)
            st.conn_ids.add(self.client_address)
            time.sleep(st.delay)
            if st.reject_think and "think" in body:
                code, data = 400, b'{"error":"\\"x\\" does not support thinking"}'
            else:
                code, data = st.status, json.dumps(st.reply).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    st.url = f"http://127.0.0.1:{srv.server_address[1]}"
    yield st
    srv.shutdown()
    srv.server_close()


def test_request_shape_and_connection_reuse(fake):
    llm = OllamaLLM(model="m", host=fake.url)
    llm.complete('Reply with JSON: "a"')
    llm.complete('Reply with JSON: "b"')
    r = fake.requests[0]
    assert r["format"] == "json" and r["think"] is False and r["keep_alive"] == "30m"
    assert r["options"]["temperature"] == 0 and r["options"]["num_predict"] <= 128
    assert r["options"]["num_ctx"] <= 4096 and r["stream"] is False
    assert len(fake.conn_ids) == 1                      # one persistent connection


def test_no_json_format_for_plain_prompt(fake):
    OllamaLLM(model="m", host=fake.url).complete("Say hello")
    assert "format" not in fake.requests[0]


def test_cache(fake):
    llm = OllamaLLM(model="m", host=fake.url)
    assert llm.complete("p JSON") == llm.complete("p JSON")
    assert len(fake.requests) == 1
    llm.complete("p JSON", use_cache=False)
    assert len(fake.requests) == 2


def test_think_tags_and_fences_stripped(fake):
    fake.reply = {"response": '<think>hmm {"sensitive": false}</think>\n```json\n{"sensitive": true, "category": "hr"}\n```'}
    llm = OllamaLLM(model="m", host=fake.url)
    assert extract_json(llm.complete("x JSON")) == {"sensitive": True, "category": "hr"}
    assert classify_sensitivity(llm, "x") == (True, "hr")


def test_clean_reply_variants():
    assert clean_reply('reasoning...</think>{"a":1}') == '{"a":1}'
    assert clean_reply('<THINK>\nx\n</THINK> {"a":1}') == '{"a":1}'
    assert clean_reply("") == ""
    assert extract_json('<think>{"x":0}</think>```\n[1,2]\n```') == [1, 2]


def test_thinking_only_reply_falls_back_to_thinking_field(fake):
    fake.reply = {"response": "", "thinking": 'so... {"sensitive": false, "category": "none"}'}
    llm = OllamaLLM(model="m", host=fake.url)
    assert classify_sensitivity(llm, "x")[0] is False


def test_think_unsupported_retries_without_flag(fake):
    fake.reject_think = True
    llm = OllamaLLM(model="m", host=fake.url)
    assert "sensitive" in llm.complete("x JSON")
    assert "think" in fake.requests[0] and "think" not in fake.requests[1]
    llm.complete("y JSON")
    assert "think" not in fake.requests[2]              # remembered


def test_http_error_raises_then_fast_fails_and_classify_falls_back(fake):
    fake.status = 500
    llm = OllamaLLM(model="m", host=fake.url, cooldown=60)
    with pytest.raises(LLMError):
        llm.complete("a")
    n = len(fake.requests)
    with pytest.raises(LLMError):
        llm.complete("b")
    assert len(fake.requests) == n                      # circuit open: no network call
    assert classify_sensitivity(llm, "She has cancer.") == (True, "health")   # keyword fallback


def test_timeout_is_graceful(fake):
    fake.delay = 1.0
    llm = OllamaLLM(model="m", host=fake.url, timeout=0.2)
    t0 = time.time()
    with pytest.raises(LLMError):
        llm.complete("a")
    assert time.time() - t0 < 0.9
    assert classify_sensitivity(llm, "The meeting is at noon.") == (False, "none")


def test_unreachable_server():
    llm = OllamaLLM(model="m", host="http://127.0.0.1:1", timeout=1)
    with pytest.raises(LLMError):
        llm.complete("a")


def test_env_defaults(monkeypatch):
    monkeypatch.delenv("OTR_LLM_MODEL", raising=False)
    monkeypatch.delenv("OTR_LLM_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert default_model() == "granite4.2:3b" and default_host() == "http://localhost:11434"
    monkeypatch.setenv("OLLAMA_HOST", "10.0.0.5:9999")
    assert default_host() == "http://10.0.0.5:9999"
    monkeypatch.setenv("OTR_LLM_HOST", "http://h:1")
    monkeypatch.setenv("OTR_LLM_MODEL", "qwen3.5:4b")
    llm = OllamaLLM()
    assert llm.host == "http://h:1" and llm.model == "qwen3.5:4b"


def test_spec_parsing(monkeypatch):
    monkeypatch.delenv("OTR_LLM_MODEL", raising=False)
    assert parse_llm_spec("none") is None
    assert parse_llm_spec("ollama:qwen3.5:4b").model == "qwen3.5:4b"
    assert parse_llm_spec("ollama").model == "granite4.2:3b"
