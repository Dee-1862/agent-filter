# Vercel demo frontend

Build this static frontend from the main meeting UI:

```sh
python vercel-demo/build.py https://YOUR-PUBLIC-BACKEND
```

Deploy with Vercel's project root set to `vercel-demo`, Framework Preset `Other`, and Output Directory `public`. Deploy only after the build command has generated `public/` and `vercel.json` in the project root. The backend must remain running and publicly reachable over HTTPS. Its LiveKit config must return a publicly reachable WSS URL.

The browser calls `/api/*` on the Vercel origin. Vercel rewrites those paths to the backend, preserving first-party browser cookies without cross-origin browser requests. The backend must allow the exact Vercel page origin in its origin check. Session cookies must have no `Domain` attribute, and the backend must not assume the request's Host equals the page origin. Test that the external rewrite preserves `Set-Cookie`, request cookies, and POST bodies before calling this deployment functional.

The Vercel build polls viewer-scoped `/api/me?summary=1` every five seconds for live note status. That response omits approved transcript lines. Its external rewrite buffered `/stream` SSE events in a live check, so this build does not request that route. The local app still uses SSE. Polling adds about 12 API requests per connected person per minute; keep the demo small and watch Vercel's free usage dashboard.

Vercel receives meeting-control requests and transcript responses through these rewrites. Media follows the LiveKit URL returned by the backend. Speech recognition and filtering stay on the meeting host; this demo does **not** claim that all meeting data stays local. Do not put API keys or meeting data into the frontend build or Vercel environment variables.

For an internet-wide media route, follow [the temporary LiveKit Cloud setup](../docs/PUBLIC_MEDIA_DEMO.md). The backend and local models remain on the meeting host; LiveKit Cloud carries meeting audio and video.
