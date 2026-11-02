# 0029. Frontend: React + Vite, TanStack Query for server data, Zustand for the rest

- **Status:** Accepted

## Context

The frontend is a single-page app with ordinary pages (Upload, Ask, People, Media, AI Lab, Settings)
plus two 3D scenes (Life and Memories). The 3D code is large, and most users open only one page at a time.

## Decision

| Concern | Choice | Why |
|---|---|---|
| UI | React 19 + TypeScript | typed components, and React Three Fiber builds on React |
| Build | Vite | fast dev server with an `/api` proxy, small production bundles |
| Routing | React Router 7 | each page is one route, lazy-loaded |
| Server data | TanStack Query | caching, refetching and loading/error states for every request |
| Client state | Zustand | small stores for login, theme, the chat stream and the universe |
| Styling | Tailwind CSS v4 | utility classes, no separate CSS files |
| Components | shadcn-style primitives in `components/ui/` | own the code, built with `cva`, `clsx` and `tailwind-merge` |
| Icons | lucide-react | one consistent icon set |
| 3D | three.js + React Three Fiber + drei | 3D as React components, with ready-made controls, lines, stars and HTML labels |

Rules that keep it clean:

- Every server request goes through a `use*` hook, and cache keys live in `api/queryKeys.ts`.
- `src/types/api.ts` mirrors `docs/api-contract.md`.
- Pages only arrange feature components.
- The 3D scenes are lazy-loaded, and WebGL support is checked first (`lib/webgl.ts`).
- No AI keys ever exist in the frontend.

## Consequences

- Pages that don't use 3D never download three.js.
- After an import, `invalidateMemoryData()` refreshes everything derived from memories in one call.

## Where in the code

`frontend/src/App.tsx`, `frontend/README.md` (layout and import rules), `src/api/`, `src/hooks/`,
`src/stores/`, `src/three/`, `src/universe/`.
