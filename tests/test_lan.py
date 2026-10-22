"""Checks for the two TLS configurations of the same-Wi-Fi launcher."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from demo.lan import caddyfile_text, public_hostname


@pytest.mark.parametrize("value, expected", [
    ("meet.example.com", "meet.example.com"),
    ("MEET.Example.COM.", "meet.example.com"),
])
def test_public_hostname(value: str, expected: str) -> None:
    assert public_hostname(value) == expected


@pytest.mark.parametrize("value", [
    "192.168.1.2", "localhost", "meet.local", "bad..example.com",
    "-meet.example.com", "meet.example.com\nfoo", "meet.example.com {",
])
def test_public_hostname_rejects_invalid_input(value: str) -> None:
    with pytest.raises(ValueError):
        public_hostname(value)


@pytest.mark.parametrize("public_tls", [False, True])
def test_caddyfile_adapts_for_both_certificate_modes(tmp_path: Path, public_tls: bool) -> None:
    caddy = shutil.which("caddy")
    if not caddy:
        pytest.skip("Caddy is not installed")
    if public_tls:
        text = caddyfile_text("meet.example.com", tmp_path / "storage",
                              tmp_path / "full chain.pem", tmp_path / "private key.pem")
        assert "local_certs" not in text
        assert text.count("  tls ") == 2
    else:
        text = caddyfile_text("192.168.1.2", tmp_path / "storage")
        assert "local_certs" in text
        assert "  tls " not in text
    config = tmp_path / "Caddyfile"
    config.write_text(text)
    result = subprocess.run([caddy, "adapt", "--config", str(config), "--adapter", "caddyfile"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
