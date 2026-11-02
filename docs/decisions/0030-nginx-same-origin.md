# 0030. nginx serves the frontend and proxies /api on the same origin

- **Status:** Accepted

## Context

The browser needs the built frontend files and the API. Serving them from different origins means
CORS setup and a backend URL baked into the build. The Ask page also streams its answer with
Server-Sent Events (SSE), which breaks if a proxy buffers the response.

## Decision

- The frontend image is two stages: Node builds the app, then **nginx** serves `dist/`.
- nginx proxies `/api/` to `http://backend:8000`, so the browser only ever talks to one origin.
  `VITE_API_URL` is empty by default, meaning same-origin.
- For the SSE endpoint, buffering is off and timeouts are 300 seconds, so tokens reach the browser
  immediately.
- `client_max_body_size 1g` allows large WhatsApp zips and videos.
- Hashed files in `/assets/` are cached for a year. `index.html` is never cached, so a new deploy
  shows up at once. Unknown paths fall back to `index.html` (single-page app routing).
- The backend runs uvicorn with `--proxy-headers`, so it sees the real client IP and scheme.

## Consequences

- No CORS in production, and one image works on any domain.
- In development, Vite's dev server does the same proxying (`VITE_PROXY_TARGET`).

## Where in the code

`frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/vite.config.ts`, `frontend/src/api/sse.ts`.
