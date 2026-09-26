# Memory Engine — Frontend

React 19 + TypeScript + Vite, Tailwind v4, shadcn-style UI, Zustand, TanStack Query, React Three Fiber.
Codes against `../docs/api-contract.md`.

## Install

```bash
npm install
```

## Develop

```bash
npm run dev        # http://localhost:5173
```

The dev server proxies `/api` → `http://localhost:8000` (override with `VITE_PROXY_TARGET`).

## Build

```bash
npm run build      # tsc -b && vite build → dist/
npm run preview
```

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | `""` | Backend origin. Empty = same-origin `/api` (dev proxy / nginx). Requests go to `${VITE_API_URL}/api/...` |
| `VITE_PROXY_TARGET` | `http://localhost:8000` | Dev-only proxy target |

No AI provider keys are ever used in the frontend.

## Docker

```bash
docker build -t memory-frontend .
docker run -p 8080:80 --network <compose-net> memory-frontend   # proxies /api to http://backend:8000
```

## Layout

| Folder | What lives there | May import from |
|---|---|---|
| `src/pages/<Page>/` | One route each. Pages only arrange feature components. | everything below |
| `src/features/<area>/` | Components (and the chat store) for one area: `chat`, `timeline`, `graph`, `media`, `people`, `upload`, `lab` | hooks, components, lib, types (only `chatStore.ts` calls `api/ask.ts` directly, because it owns the stream) |
| `src/three/` | The 3D Life explorer (React Three Fiber) and its layout math; lazy-loaded | lib, types |
| `src/hooks/` | `use*` hooks — every server request goes through one of these (TanStack Query) | api, stores, lib, types |
| `src/api/` | One module per contract section (`auth`, `uploads`, `search`, `ask`, `timeline`, `people`, `lab`, `health`, `media`) + the HTTP client, error messages, SSE reader, cache keys | stores, types |
| `src/stores/` | Zustand stores for app-wide client state (`authStore`, `themeStore`) | — |
| `src/components/` | Shared app components (`Layout`, `ErrorState`, …); `components/ui/` holds the design-system primitives (`Button`, `Card`, …) | hooks, stores, lib |
| `src/lib/` | Pure helpers: formatting, period strings, source colours/icons | types |
| `src/types/api.ts` | TypeScript mirror of `docs/api-contract.md` | — |

Naming: components `PascalCase.tsx` (one exported component per file), hooks `useThing.ts`, other modules `camelCase.ts`.

A request, end to end: `UploadForm` → `useUploadFiles()` (hooks/useUploads.ts) → `uploadFiles()` (api/uploads.ts) →
`POST /api/uploads`. Cache keys live in `api/queryKeys.ts`; after data changes, `invalidateMemoryData()` refreshes
everything derived from memories. Error responses become `ApiError`s with a readable `message` (api/errors.ts).
