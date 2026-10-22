"""LiveKit credential defaults shared by the source, token minting, preflight and docs.

The secret is 32+ characters because PyJWT warns about shorter HMAC keys. Override with
LIVEKIT_API_KEY / LIVEKIT_API_SECRET; the compose file reads the same variables.
"""
import os

DEFAULT_API_KEY = "devkey"
DEFAULT_API_SECRET = "otr-dev-secret-change-me-0123456789abcdef"
MIN_SECRET_LEN = 32


def api_key() -> str:
    return os.environ.get("LIVEKIT_API_KEY", DEFAULT_API_KEY)


def api_secret() -> str:
    return os.environ.get("LIVEKIT_API_SECRET", DEFAULT_API_SECRET)
