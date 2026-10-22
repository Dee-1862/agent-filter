"""otr.app preflight / start logic with fake probes (no network, docker, or models)."""
import wave
from pathlib import Path

import numpy as np

from otr import app
from otr.app import Env, Options, ensure_livekit, format_table, preflight


def env(**kw):
    base = dict(
        http_json=lambda url, timeout=2.0: {"models": [{"name": "qwen2.5:3b"}]},
        port_open=lambda h, p: False,
        docker_ok=lambda: True,
        run=lambda cmd, cwd=None: 0,
        has_module=lambda m: True,
        presidio=lambda: (True, "en_core_web_lg"),
        whisper_dir=lambda m: Path("/models/" + m),
        exists=lambda p: True,
        sleep=lambda s: None,
    )
    base.update(kw)
    return Env(**base)


def by_name(checks, prefix):
    return [c for c in checks if c.name.startswith(prefix)]


def test_replay_needs_no_whisper_docker_or_livekit():
    e = env(has_module=lambda m: m in ("fastapi", "uvicorn"), whisper_dir=lambda m: None,
            docker_ok=lambda: False)
    cs = preflight(Options(source="replay", script="s.txt"), e)
    assert not [c for c in cs if c.blocking]
    assert not by_name(cs, "faster") and not by_name(cs, "Whisper") and not by_name(cs, "Docker")


def test_replay_missing_script_blocks():
    cs = preflight(Options(source="replay", script="x.txt"), env(exists=lambda p: False))
    assert [c.name for c in cs if c.blocking] == ["script"]


def test_audio_requires_whisper_weights_with_fix_command():
    cs = preflight(Options(source="audio", audio=["d"]), env(whisper_dir=lambda m: None))
    bad = by_name(cs, "Whisper weights")[0]
    assert bad.blocking and "WhisperModel('base.en'" in bad.fix and "tiny.en" in bad.fix


def test_audio_model_option_and_env(monkeypatch):
    seen = []
    preflight(Options(source="audio", audio=["d"], model="tiny.en"),
              env(whisper_dir=lambda m: seen.append(m) or Path("x")))
    assert seen == ["tiny.en"]
    monkeypatch.setenv("OTR_WHISPER_MODEL", "small.en")
    assert app.whisper_model(Options()) == "small.en"


def test_audio_without_input_or_missing_path_blocks():
    assert any(c.blocking for c in preflight(Options(source="audio"), env()))
    cs = preflight(Options(source="audio", audio=["nope"]), env(exists=lambda p: False))
    assert by_name(cs, "audio input")[0].blocking


def test_ollama_is_soft_requirement():
    def boom(url, timeout=2.0):
        raise OSError("refused")
    cs = preflight(Options(source="replay", llm="ollama:qwen2.5:3b"), env(http_json=boom))
    c = by_name(cs, "Ollama")[0]
    assert c.status == "warn" and "ollama serve" in c.fix and not any(x.blocking for x in cs)


def test_ollama_model_installed_vs_missing():
    cs = preflight(Options(source="replay", llm="ollama:qwen2.5:3b"), env())
    assert by_name(cs, "Ollama model")[0].status == "ok"
    cs = preflight(Options(source="replay", llm="ollama:other:1b"), env())
    c = by_name(cs, "Ollama model")[0]
    assert c.status == "warn" and c.fix == "ollama pull other:1b"


def test_ollama_latest_tag_matches():
    e = env(http_json=lambda u, timeout=2.0: {"models": [{"name": "llama3:latest"}]})
    cs = preflight(Options(source="replay", llm="ollama:llama3"), e)
    assert by_name(cs, "Ollama model")[0].status == "ok"


def test_presidio_missing_is_warning():
    cs = preflight(Options(source="replay"), env(presidio=lambda: (False, "spaCy model missing")))
    assert by_name(cs, "Presidio")[0].status == "warn" and not any(c.blocking for c in cs)


def test_livekit_port_open_needs_no_docker():
    e = env(port_open=lambda h, p: p == app.LIVEKIT_PORT, docker_ok=lambda: False)
    cs = preflight(Options(source="livekit"), e)
    assert not [c for c in cs if c.blocking] and not by_name(cs, "Docker")


def test_livekit_closed_docker_up_is_warning_docker_down_blocks():
    cs = preflight(Options(source="livekit"), env())
    assert by_name(cs, "LiveKit port")[0].status == "warn"
    cs = preflight(Options(source="livekit-stream"), env(docker_ok=lambda: False))
    assert by_name(cs, "LiveKit port")[0].blocking and by_name(cs, "Docker")[0].blocking
    cs = preflight(Options(source="livekit", no_docker=True), env())
    assert by_name(cs, "LiveKit port")[0].blocking


def test_demo_port_in_use_blocks():
    cs = preflight(Options(source="replay", port=8000), env(port_open=lambda h, p: p == 8000))
    assert by_name(cs, "port 8000")[0].blocking


def test_ensure_livekit_runs_compose_then_waits_for_port():
    state = {"open": False, "cmds": []}

    def run(cmd, cwd=None):
        state["cmds"].append(cmd)
        return 0

    def sleep(s):
        state["open"] = True
    e = env(port_open=lambda h, p: state["open"], run=run, sleep=sleep)
    assert ensure_livekit(Options(source="livekit"), e)
    assert state["cmds"] == [["docker", "compose", "-f", "docker-compose.livekit.yml", "up", "-d"]]


def test_ensure_livekit_skips_compose_when_port_open_or_docker_down():
    cmds = []
    e = env(port_open=lambda h, p: True, run=lambda c, cwd=None: cmds.append(c) or 0)
    assert ensure_livekit(Options(), e) and cmds == []
    e = env(docker_ok=lambda: False, run=lambda c, cwd=None: cmds.append(c) or 0)
    assert not ensure_livekit(Options(), e) and cmds == []


def test_format_table_has_fix_lines():
    cs = preflight(Options(source="audio", audio=["d"]), env(whisper_dir=lambda m: None))
    t = format_table(cs)
    assert "FAIL" in t and "fix:" in t


def test_main_check_exit_codes_and_blocked_start():
    assert app.main(["--source", "replay", "--check"], env()) == 0
    assert app.main(["--source", "audio", "--audio", "d", "--check"], env(whisper_dir=lambda m: None)) == 1
    assert app.main(["--source", "audio", "--audio", "d"], env(whisper_dir=lambda m: None)) == 2


def test_audio_app_wiring_uses_audio_source_and_restores_server(tmp_path):
    """make_app('audio') routes demo.server's replay path to the AudioFileSource, then restores it."""
    from demo import server as ds
    from otr.ingest import replay_source as rs
    from otr.ingest.audio_file_source import AudioFileSource
    x = np.zeros(48000)
    x[8000:24000] = 0.5
    with wave.open(str(tmp_path / "alice.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    src = AudioFileSource([tmp_path / "alice.wav"], transcribe=lambda a: "hello there")
    src.transcribe_all()
    orig = (ds.load_script_segments, rs.ReplaySource)
    a = app.make_app(Options(source="audio", audio=[str(tmp_path)], speed=0, hold=1), None, src)
    assert (ds.load_script_segments, rs.ReplaySource) == orig
    r = a.state.runner
    assert r.source_name == "audio" and isinstance(r._source, AudioFileSource)
    assert [s.text for s in r._source._segments] == ["hello there"]
