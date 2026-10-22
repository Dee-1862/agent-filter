# Vercel demo frontend

Build this static frontend from the main meeting UI:

```sh
python vercel-demo/build.py https://YOUR-PUBLIC-BACKEND
```

Deploy with Vercel's project root set to `vercel-demo`, Framework Preset `Other`, and Output Directory `public`. Deploy only after the build command has generated `public/` and `vercel.json` in the project root. The backend must remain running and publicly reachable over HTTPS. Its LiveKit config must return a publicly reachable WSS URL.

The browser calls `/api/*` on the Vercel origin. Vercel rewrites those paths to the backend, preserving first-party browser cookies without cross-origin browser requests. The backend must allow the exact Vercel page origin in its origin check. Session cookies must have no `Domain` attribute, and the backend must not assume the request's Host equals the page origin. Test that the external rewrite preserves `Set-Cookie`, request cookies, and POST bodies before calling this deployment functional.

The hosted build polls full viewer-scoped `/api/me` every three seconds for the shared live transcript. Authenticated participants with notes ON can see post-hold approved lines from every consenting speaker; notes-off participants get no live text. The external rewrite buffered `/stream` SSE events in a live check, so the hosted build polls instead. The local app still uses SSE. Polling adds about 20 API requests per connected person per minute; keep the demo small and watch Vercel's free usage dashboard.

Vercel and Cloudflare carry approved live transcript text whenever a notes-on participant polls the shared view, as well as meeting-control requests and final transcript responses. Media follows the LiveKit URL returned by the backend. Speech recognition and filtering stay on the meeting host; this demo does **not** claim that all meeting data stays local or that filtering catches every sensitive line. Do not put API keys or meeting data into the frontend build or Vercel environment variables.

For an internet-wide media route, follow [the temporary LiveKit Cloud setup](../docs/PUBLIC_MEDIA_DEMO.md). The backend and local models remain on the meeting host; LiveKit Cloud carries meeting audio and video.
