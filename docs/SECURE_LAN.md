# Secure LAN meeting preview

This runs the meeting app, LiveKit, and speech processing on one computer. A friend can join from the same Wi-Fi network through HTTPS. The launcher does not use LiveKit Cloud or a public tunnel.

## Start it on the host Mac

Install the two local server binaries once:

```sh
brew install livekit caddy
```

Install the Python dependencies and download the local speech model before going offline. Then run from this repository:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-demo.txt -r requirements-ingest.txt
OTR_WHISPER_MODEL_DIR=/absolute/path/to/downloaded/faster-whisper-model \
  python3 -m demo.lan --python .venv/bin/python
```

If the Mac has several network interfaces, pass `--lan-ip 192.168.x.x` with its Wi-Fi address. For a UI-only check without speech recognition, add `--pipeline fake`.

The launcher prints the meeting URL and the path to a **public root certificate**. Its default ports are HTTPS `18443`, LiveKit WSS `18444`, WebRTC UDP `17882`, and WebRTC TCP fallback `17881`. Allow incoming connections for Caddy and LiveKit if the host firewall asks. Keep the terminal running during the meeting; Ctrl-C stops all three services.

## Trust the local certificate on each device

Before opening the meeting URL, install and trust the printed `root.crt` on the host and each friend's device using that device's certificate trust settings. Transfer **only `root.crt`** to the friend. Never transfer anything from `.local-lan/caddy-storage` with a `.key` extension. After trusting it, open the printed `https://...:18443/` URL, create a meeting, and send the generated meeting link. The friend opens that link on the same Wi-Fi network and asks to join; the host admits them.

The root certificate is local and is not issued by a public certificate authority. Installing it grants this host's local CA trust on that device, so remove it from the friend's trust store after the demo if they do not want to keep that trust. Do not bypass browser certificate warnings: LiveKit's secure WebSocket connection also needs the certificate to be trusted.

## What stays local

The launcher creates a new random LiveKit API key and secret for each run and deletes their config file when stopped. Caddy keeps its local CA in `.local-lan/` so devices can trust the same root for later previews. The app and LiveKit signaling listen on loopback behind Caddy; WebRTC media travels over the LAN using encrypted transport. The only STUN address configured for LiveKit is the host's LAN address. Local model downloads must already be present; the launcher sets Hugging Face offline environment flags. Meeting notes and transcripts are not sent to a cloud service by this launcher.

`.local-lan/` is ignored by git and holds local service logs and certificate keys. Keep this directory private. If you delete it, Caddy creates a new CA and each device must trust the new `root.crt`.

This path is for devices on the same reachable LAN. Some guest or campus Wi-Fi networks isolate devices; if the link does not open from the friend's device, use a network that permits device-to-device traffic. The friend must reach the host on the four ports above.

The previous plain HTTP preview on `127.0.0.1:8772` is only for the host computer. Do not share that URL with another device.

References: [LiveKit ports](https://docs.livekit.io/transport/self-hosting/ports-firewall/), [LiveKit self-hosted TLS](https://docs.livekit.io/transport/self-hosting/deployment/), [Caddy local HTTPS](https://caddyserver.com/docs/automatic-https), [Caddy WebSocket reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
