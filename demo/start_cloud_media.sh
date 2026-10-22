#!/usr/bin/env bash
# Temporary public demo: LiveKit Cloud carries media; the app and ASR run here.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${1:-$repo_root/.local-lan/livekit-cloud.env}"
if [[ ! -f "$env_file" ]]; then
  echo "Missing local config: $env_file (see docs/PUBLIC_MEDIA_DEMO.md)" >&2
  exit 2
fi

# Only source a file created by the local operator. Never commit or print it.
set -a
source "$env_file"
set +a
for name in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing $name in local config" >&2
    exit 2
  fi
done
export OTR_WHISPER_MODEL_DIR="${OTR_WHISPER_MODEL_DIR:-$repo_root/models/faster-whisper/tiny.en}"
if [[ "$LIVEKIT_URL" != wss://* ]]; then
  echo "LIVEKIT_URL must be the LiveKit Cloud wss:// project URL" >&2
  exit 2
fi
if [[ ! -f "$OTR_WHISPER_MODEL_DIR/model.bin" ]]; then
  echo "OTR_WHISPER_MODEL_DIR must contain local model.bin" >&2
  exit 2
fi
if [[ ! -x "$repo_root/.venv/bin/python" ]]; then
  echo "Missing local Python environment: $repo_root/.venv/bin/python" >&2
  exit 2
fi

export LIVEKIT_PUBLIC_URL="$LIVEKIT_URL"
export MEETING_PUBLIC_ORIGIN="${MEETING_PUBLIC_ORIGIN:-https://consentmeeting.vercel.app}"
export OTR_PUBLIC_ORIGIN="${OTR_PUBLIC_ORIGIN:-$MEETING_PUBLIC_ORIGIN}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OTR_MAX_ACTIVE_MEETINGS="${OTR_MAX_ACTIVE_MEETINGS:-4}"
export OTR_MAX_PENDING_JOIN_REQUESTS="${OTR_MAX_PENDING_JOIN_REQUESTS:-20}"

cd "$repo_root"
exec "$repo_root/.venv/bin/python" -m demo.server --source livekit --pipeline real \
  --host 127.0.0.1 --port "${OTR_BACKEND_PORT:-18773}"
