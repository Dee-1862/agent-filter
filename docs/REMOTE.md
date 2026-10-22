# Sharing a meeting over the internet

The meeting server, speech to text and the AI model run on the host's laptop. A tunnel gives guests a web
address that reaches the laptop.

## Start

```
python -m otr.service
```

Settings come from `.otr-service.json` in the repository folder (ignored by git):

```
{"tunnel": "ngrok", "ngrok_domain": "your-name.ngrok-free.dev", "port": 8765, "idle_minutes": 10, "serve_page": true, "llm": "auto"}
```

- `ngrok_domain`: the free domain shown in your ngrok dashboard. Running `ngrok http 8000` once also prints it.
- `serve_page: true`: the page and the live updates come from the laptop through the tunnel, so captions update instantly. This is the recommended mode.
- `idle_minutes`: the model unloads after this many minutes with no active meeting.

Check the setup without starting: `python -m otr.service --check`.

## What happens

1. The service checks that Docker, the call server, Whisper, Presidio and Ollama are ready.
2. It starts the meeting server on `127.0.0.1` only, then the ngrok tunnel, and prints the public address.
3. The AI model is not loaded. Creating or joining a meeting loads it (about 5 to 10 seconds). Until then the keyword rules do the checking.
4. After `idle_minutes` with no meeting, the model is unloaded again.

## Choosing the model

On the host's own laptop, open `/meet`, then the notes panel. A "Local model" list shows the installed Ollama models.
Changing it takes effect for the next sentences. Guests coming through the tunnel see which model is active but cannot change it.

## What crosses the tunnel

- Crosses: the web page, names, consent on or off, approved note lines, counts of kept out items, model name.
- Does not cross: audio files (none are made), held or kept out text, the model itself, Ollama's port.
- The tunnel provider (ngrok) decrypts traffic at its edge, so it can see what crosses. Do not call this end to end private.
- Call audio and video are a separate path. Guests on the same Wi-Fi work. Guests elsewhere need the cloud media route in [PUBLIC_MEDIA_DEMO.md](PUBLIC_MEDIA_DEMO.md).

## Other tunnels

| Tunnel | Cost | Notes |
|---|---|---|
| ngrok (used now) | free | one stable address, a warning page on the first visit, bandwidth limit |
| Cloudflare quick tunnel | free | no account, the address changes every restart |
| Cloudflare named tunnel | tunnel free, needs a domain you own | stable address on your own domain |

Set `"tunnel": "cloudflared"` and the matching fields to switch.
