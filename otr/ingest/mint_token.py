"""Mint a LiveKit join token for a human participant.

    python -m otr.ingest.mint_token --room demo --identity alice

Reads LIVEKIT_API_KEY / LIVEKIT_API_SECRET (defaults: devkey / secret, which
match docker-compose.livekit.yml dev mode). Requires `livekit-api`.
"""
from __future__ import annotations

import argparse
import os


def mint(room: str, identity: str, api_key: str, api_secret: str, ttl_s: int = 3600, can_subscribe: bool = True) -> str:
    try:
        from datetime import timedelta
        from livekit import api
    except ImportError as e:
        raise RuntimeError("livekit-api not installed: pip install -r requirements-ingest.txt") from e
    return (api.AccessToken(api_key, api_secret)
            .with_identity(identity).with_name(identity)
            .with_ttl(timedelta(seconds=ttl_s))
            .with_grants(api.VideoGrants(room_join=True, room=room, can_subscribe=can_subscribe))
            .to_jwt())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", default="demo")
    ap.add_argument("--identity", required=True)
    a = ap.parse_args()
    print(mint(a.room, a.identity, os.environ.get("LIVEKIT_API_KEY", "devkey"),
               os.environ.get("LIVEKIT_API_SECRET", "secret")))


if __name__ == "__main__":
    main()
