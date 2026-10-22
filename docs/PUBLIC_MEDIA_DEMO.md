# Temporary public media route

The public demo uses LiveKit Cloud for media and signaling. The FastAPI meeting
service, per-person consent logic, Whisper transcription, and filtering continue
to run on this Mac. A self-hosted LiveKit server remains an option for the
longer-term local deployment.

This is a temporary cloud-media mode. LiveKit Cloud carries every participant's
meeting audio and video, including media from people who have notes turned off.
Notes-off controls what the local notetaker subscribes to and transcribes; it
does not stop the meeting server from routing that person's media to other
participants. Separately, the Vercel API proxy and Cloudflare tunnel carry
meeting-control requests and responses. When a notes-on participant polls the
shared live transcript, approved text also passes through Vercel and
Cloudflare. Do not describe this mode as fully local or cloud-private. A
notes-off participant gets no live transcript text, but LiveKit Cloud still
carries their meeting audio and video.

## Configure on the meeting host

1. Create a LiveKit Cloud project and copy its project WebSocket URL, API key,
   and API secret. Keep the credentials only on this Mac.
2. Create `.local-lan/livekit-cloud.env` in this repository with permission 600.
   The entire `.local-lan/` directory is ignored by Git:

   ```sh
   umask 077
   mkdir -p .local-lan
   $EDITOR .local-lan/livekit-cloud.env
   chmod 600 .local-lan/livekit-cloud.env
   ```

   File contents (replace placeholders locally, never in a commit):

   ```sh
   LIVEKIT_URL='wss://YOUR-PROJECT.livekit.cloud'
   LIVEKIT_API_KEY='YOUR-API-KEY'
   LIVEKIT_API_SECRET='YOUR-API-SECRET'
   ```

   The launcher uses this repository's existing
   `models/faster-whisper/tiny.en/model.bin` by default. If using another local
   model, add `OTR_WHISPER_MODEL_DIR='/absolute/path/to/model/directory'` to
   this ignored file.

3. In a terminal on the meeting host, start the existing backend with
   `bash demo/start_cloud_media.sh`. It checks the required settings before
   starting. `LIVEKIT_PUBLIC_URL` is set to the same Cloud URL for browsers;
   the API key and secret stay in the backend process. The launcher defaults
   the page origin to `https://consentmeeting.vercel.app` and listens only on
   `127.0.0.1:18773` for the existing local tunnel. Set `OTR_BACKEND_PORT` in
   the local file only if the tunnel targets another port.
4. Confirm that the existing API tunnel and Vercel rewrite still point to this
   backend. No Vercel rebuild is required to change the LiveKit URL: the browser
   obtains it from `/api/config` and its admission response. Create a new
   meeting after switching servers; pre-existing rooms and tokens belong to the
   previous server and are not transferred.
5. Test with two devices on different networks. Host creates a meeting, guest
   requests admission, host admits, and both see the other participant's video.
   Then test notes consent and local transcription. Stop the old local backend
   before launching this mode; only one service can own the backend port.

The script does not start or reconfigure LiveKit, Cloudflare, or Vercel. The
local app does not request LiveKit recording/egress or write audio and transcript
files; it holds in-progress notes in memory. LiveKit Cloud's own data handling
and usage terms apply to all meeting media in this mode. Keep the local runtime
available during the demo: if the Mac or API tunnel stops, admission and notes
stop too.
