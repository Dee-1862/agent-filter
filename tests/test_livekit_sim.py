import json
import wave
from pathlib import Path

import pytest

from experiments.livekit_sim import load_manifest, require_loopback


def test_manifest_accepts_distinct_synthetic_speakers_and_local_wav(tmp_path: Path):
    wav = tmp_path / "voice.wav"
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\0" * 640)
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"synthetic": True, "observe_at": [2, 5.5], "participants": [
        {"name": "Ada", "actions": [{"at": 0, "recording": True},
                                    {"at": 1, "wav": "voice.wav"}]},
        {"name": "Ben", "actions": [{"at": 0, "recording": False},
                                    {"at": 1, "wav": "voice.wav"}]},
    ]}))
    parsed = load_manifest(path)
    assert parsed["participants"][0]["actions"][1]["_path"] == wav
    assert parsed["observe_at"] == [2, 5.5]


def test_manifest_rejects_real_audio_and_remote_app(tmp_path: Path):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"participants": [{"name": "Ada", "actions": []}]}))
    with pytest.raises(ValueError, match="synthetic"):
        load_manifest(path)
    with pytest.raises(ValueError, match="loopback"):
        require_loopback("https://example.com", ("http",))


@pytest.mark.parametrize("observe_at", [[-1], [3, 2], "soon", [True]])
def test_manifest_rejects_invalid_observation_schedule(tmp_path: Path, observe_at):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"synthetic": True, "observe_at": observe_at,
                                "participants": [{"name": "Ada", "actions": [
                                    {"at": 0, "recording": True}]}]}))
    with pytest.raises(ValueError, match="observe_at"):
        load_manifest(path)
