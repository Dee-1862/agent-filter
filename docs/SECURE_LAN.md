# Secure LAN meeting preview

This runs the meeting app, LiveKit, and speech processing on one computer. A friend can join from the same Wi-Fi network through HTTPS. The launcher does not use LiveKit Cloud or a public tunnel.

## A link guests can open without installing a certificate

Use a domain you control and a browser-trusted TLS certificate for it. The domain must resolve to the host computer's Wi-Fi IP on every guest device. A DNS `A` record with that private IP can work, but some networks block private IP answers from public DNS. A local DNS record on the Wi-Fi router is another option if every guest uses that router for DNS. Check the name from a second device before the meeting.

Obtain the certificate with a DNS-01 challenge before the meeting. That checks domain control through DNS and does not require opening the meeting server to the internet. Keep the private key on the host. The launcher does not issue certificates, change DNS, or send meeting data to the certificate provider. DNS lookups and ordinary browser certificate checks may still use the internet.

With the certificate chain and key already on the host, run:

```sh
chmod 600 /private/path/to/key.pem
OTR_WHISPER_MODEL_DIR=/absolute/path/to/downloaded/faster-whisper-model \
  python3 -m demo.lan --python .venv/bin/python \
  --public-host meet.example.com \
  --tls-cert /private/path/to/fullchain.pem \
  --tls-key /private/path/to/key.pem
```

The launcher checks that the hostname resolves to the host's Wi-Fi IP, that the certificate and key load together, and that the meeting page passes the computer's normal HTTPS trust check. It then prints `https://meet.example.com:18443/`. Guests can open the meeting link without installing a certificate. The certificate must remain valid and match the hostname. Share the link only with people on the same reachable Wi-Fi; the server and WebRTC media still run locally.

This mode needs a domain and certificate prepared in advance. It cannot turn an arbitrary `https://192.168.x.x` address into a browser-trusted link by itself.

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

Without `--public-host`, the launcher prints the meeting URL and the path to a **public root certificate**. Its ports are HTTPS `18443`, LiveKit WSS `18444`, WebRTC UDP `17882`, WebRTC TCP fallback `17881`, and local STUN UDP `17883`. It checks that the STUN port responds before printing the link. Allow incoming connections for Caddy and LiveKit if the host firewall asks. Keep the terminal running during the meeting; Ctrl-C stops all three services.

## Trust the local certificate on each device

This step applies only to the default local-certificate mode. Before opening its meeting URL, install and trust the printed `root.crt` on the host and each friend's device using that device's certificate trust settings. Transfer **only `root.crt`** to the friend through a channel you trust, such as AirDrop. Never transfer anything from `.local-lan/caddy-storage` with a `.key` extension. On iPhone/iPad, installing the profile is only the first step; enable full trust for the installed root in Settings > General > About > Certificate Trust Settings. After trusting it, open the printed `https://...:18443/` URL, create a meeting, and send the generated meeting link. The friend opens that link on the same Wi-Fi network and asks to join; the host admits them.

The root certificate is local and is not issued by a public certificate authority. Installing it grants this host's local CA trust on that device, so remove it from the friend's trust store after the demo if they do not want to keep that trust. Do not bypass browser certificate warnings: LiveKit's secure WebSocket connection also needs the certificate to be trusted.

## What stays local

The launcher creates a new random LiveKit API key and secret for each run and deletes their config file when stopped. Caddy keeps its local CA in `.local-lan/` so devices can trust the same root for later previews. The app and LiveKit signaling listen on loopback behind Caddy; WebRTC media travels over the LAN using encrypted transport. The only STUN address configured for LiveKit is the host's LAN address. Local model downloads must already be present; the launcher sets Hugging Face offline environment flags. Meeting notes and transcripts are not sent to a cloud service by this launcher.

`.local-lan/` is ignored by git and holds local service logs and certificate keys. Keep this directory private. If you delete it, Caddy creates a new CA and each device must trust the new `root.crt`.

This path is for devices on the same reachable LAN. Some guest or campus Wi-Fi networks isolate devices; if the link does not open from the friend's device, use a network that permits device-to-device traffic. The friend must reach the host on the five ports above. A successful check from the host itself does not prove that a second device can reach it.

If a friend cannot join, check in this order:

1. Open the printed `https://...:18443/` link on their device. If the page does not load, check the host's Wi-Fi IP, router client isolation, and inbound firewall rules for Caddy on TCP `18443`. If the browser warns about the certificate, trust `root.crt` before continuing. Do not bypass the warning: camera and microphone require a trusted secure page.
2. If the page loads but the meeting says disconnected, check the same certificate trust for WSS `18444` and allow Caddy on TCP `18444`.
3. If the room connects but audio or video does not flow, allow LiveKit on UDP `17882` and `17883` and TCP `17881`. The UDP media and STUN ports must reach the host directly; Caddy does not proxy them.

The default mode uses a local certificate authority, so each device needs that one-time trust step. The public-certificate mode above removes that step once a domain and certificate are ready.

The previous plain HTTP preview on `127.0.0.1:8772` is only for the host computer. Do not share that URL with another device.

References: [LiveKit ports](https://docs.livekit.io/transport/self-hosting/ports-firewall/), [LiveKit self-hosted TLS](https://docs.livekit.io/transport/self-hosting/deployment/), [Caddy certificate files](https://caddyserver.com/docs/caddyfile/directives/tls), [Let's Encrypt DNS-01](https://letsencrypt.org/docs/challenge-types/), [Caddy local HTTPS](https://caddyserver.com/docs/automatic-https), [Caddy WebSocket reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
