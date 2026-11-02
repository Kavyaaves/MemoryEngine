# Frontend packages, in detail

Every package in `frontend/package.json`, using the same layout as the [backend guide](backend.md):
what it is, why you need it, what it does here, what breaks without it, the alternatives, and gotchas.

"Range" is the range in `package.json` (`^` = any newer minor or patch, `~` = patch only).
"Installed" is the version in `frontend/node_modules` on 2026-11-02 (`npm ls --depth=0`).

The overall choices are explained in [0029](../decisions/0029-frontend-stack.md).

Contents:
[UI core](#1-ui-core) ·
[Data and state](#2-data-and-state) ·
[3D](#3-3d) ·
[Styling and components](#4-styling-and-components) ·
[Build tools](#5-build-tools) ·
[Types](#6-type-definitions)

---

## 1. UI core

### `react` and `react-dom`

Range `^19.1.0` · Installed 19.3.0 · Docs: <https://react.dev>

**What it is.** React is a library for building user interfaces from **components**: functions that
return what the screen should look like for the current data. When the data changes, React works out
what changed and updates only that part of the page. `react-dom` is the renderer that puts React
components into a browser page. (React Three Fiber is another renderer, for 3D.)

**Why you need it.**
- The app has many interactive pages (chat, uploads with progress, the people graph, the AI Lab),
  each with lots of state.
- React Three Fiber, the 3D layer, is built on React, so the 3D scenes and the normal pages share one
  model of components, props and hooks.

**What it does here.**
- `src/main.tsx`: `createRoot(...).render(<StrictMode><QueryClientProvider>…<App/>)`.
- `src/App.tsx`: routes, with every page loaded by `React.lazy(() => import(...))`.
- `components/Layout.tsx`: wraps the current page in `Suspense` (a loading state while its code
  downloads) and an `ErrorBoundary` (a crash in one page doesn't blank the whole app).
- `pages/Life/LifePage.tsx` and `pages/Memories/MemoriesPage.tsx` lazy-load their 3D scene inside
  their own `ErrorBoundary`. If the 3D view fails, you get the list view instead.
- 98 `.tsx` component files in `src/`.

**Without it.** You'd update the page by hand with the DOM, which gets unmanageable at this size.

**Alternatives.** *Vue*, *Svelte*, *SolidJS*. All are good, but React has React Three Fiber, the most
mature way to write three.js declaratively, and the largest ecosystem.

**Good to know.**
- `StrictMode` runs effects twice in development, on purpose, to expose missing cleanups. If
  something runs twice in dev, that's why. It doesn't happen in production.
- React 19 is new. Some older tutorials use APIs that changed (for example `ReactDOM.render`).

---

### `react-router`

Range `^7.6.0` · Installed 7.18.4 · Docs: <https://reactrouter.com>

**What it is.** Client-side routing: maps URLs (`/ask`, `/people/123`) to components and switches
between them without a full page reload. Version 7 merged the old `react-router-dom` into this one package.

**Why you need it.** The app has eight pages, plus login, and the URL should reflect where you are,
so refresh, the back button and bookmarks work.

**What it does here.**
- `App.tsx`: `BrowserRouter`, `Routes`, `Route`, and `Navigate` (redirects).
- `components/RequireAuth.tsx`: a layout route that sends signed-out users to `/login` and
  remembers where they were going (`useLocation`).
- `components/Layout.tsx`: the sidebar, with `NavLink` (highlights the active page) and `Outlet`
  (where the current page renders).

**Without it.** One URL for the whole app, or a hand-written router.

**Alternatives.** *TanStack Router* (fully type-safe routes), *wouter* (tiny).

**Good to know.**
- Import from `"react-router"`. In v7 the old `"react-router-dom"` is only a re-export.
- In production, nginx sends unknown paths to `index.html` (`try_files … /index.html`), so a deep
  link like `/people/123` loads the app, and the router takes over
  ([0030](../decisions/0030-nginx-same-origin.md)).

---

## 2. Data and state

There are two kinds of state, and this app uses one tool for each:

| Kind | Example | Tool |
|---|---|---|
| **Server state**: data that lives in the backend | memories, people, the timeline, AI usage | TanStack Query |
| **Client state**: data only the browser has | the login token, the theme, the chat stream in progress, the universe camera | Zustand |

### `@tanstack/react-query`

Range `^5.75.0` · Installed 5.103.2 · Docs: <https://tanstack.com/query/latest>

**What it is.** A library for **server state**: fetching, caching, refetching and updating data from
an API. You give it a key and a function, and it handles loading and error states, shares the cache
between components, de-duplicates identical requests and refetches when the data may be stale.

**Why you need it.**
- Many components show the same server data (people appear on the People page, in Ask and in the
  graph). Without a shared cache, each would fetch it separately.
- After an import finishes, every view derived from memories must refresh. With query keys, that is
  one call.

**What it does here.**
- `api/queryClient.ts`: the app's single `QueryClient`:
  - `staleTime: 30_000`: data counts as fresh for 30 seconds
  - `refetchOnWindowFocus: false`
  - retries network errors and 5xx twice, never 4xx ("a 4xx won't fix itself by asking again")
  - **clears the whole cache when the signed-in user changes**, so one user never sees another's data
- `api/queryKeys.ts`: every cache key in one place. `invalidateMemoryData()` refreshes everything
  derived from memories.
- `hooks/use*.ts`: every request goes through a hook (`useQuery` / `useMutation`). For example,
  `useHealth()` uses `retry: false`, because a health check should report the current state immediately.

**Without it.** `useEffect` + `fetch` + `useState` in every component, with your own loading flags,
caching, de-duplication and invalidation.

**Alternatives.** *SWR* (similar, smaller), *RTK Query* (if you use Redux), *Apollo* (GraphQL only).

**Good to know.**
- Query keys are arrays, and invalidation matches by prefix: invalidating `["people"]` also
  invalidates `["people", id]`.
- The streaming chat isn't a query: `chatStore.ts` calls `api/ask.ts` directly, because it owns the
  SSE stream.

---

### `zustand`

Range `^5.0.4` · Installed 5.0.15 · Docs: <https://zustand.docs.pmnd.rs>

**What it is.** A tiny state-management library. `create()` makes a store: an object with state and
functions that change it. Components read just the part they need, and only re-render when that part changes.

**Why you need it.** Some state is shared by many components but isn't server data: who is signed in,
light or dark theme, the chat conversation being streamed, and where you are in the Memory Universe.
Passing it down through props would touch every component in between.

**What it does here.**
- `stores/authStore.ts`: the token and email. The `persist` middleware saves them in `localStorage`
  (`pmme-auth`), and a `storage` event listener keeps open tabs in sync, so signing out in one tab
  signs out the others. `api/client.ts` reads the token for every request and calls `logout()` on a 401.
- `stores/themeStore.ts`: light / dark.
- `stores/universeStore.ts`: the Memory Universe's selection and camera target.
- `features/chat/chatStore.ts`: the conversation and the streaming answer.
- Stores can be **subscribed to** outside React: `queryClient.ts` clears the cache, and `chatStore`
  clears the conversation, whenever the token changes.

**Without it.** React Context (which re-renders every consumer on any change) or prop drilling.

**Alternatives.** *Redux Toolkit* (more structure and boilerplate), *Jotai* (atoms, from the same
authors), *React Context*.

**Good to know.**
- Select narrowly: `useAuthStore((s) => s.token)`, not `useAuthStore()`, or the component re-renders
  on every change.
- `getState()` reads a store outside React, which is how `api/client.ts` gets the token.

---

## 3. 3D

The Life page (a spiral timeline) and the Memories page (the Memory Universe) are 3D scenes. These
three packages work together:

```
three                 the 3D engine (WebGL): scenes, meshes, materials, cameras, maths
  └─ @react-three/fiber   write three.js as React components: <mesh>, <sphereGeometry>, useFrame()
       └─ @react-three/drei    ready-made pieces: camera controls, lines, stars, HTML labels
```

### `three`

Range `^0.176.0` · Installed 0.176.0 · Docs: <https://threejs.org/docs/>

**What it is.** three.js, the most widely used JavaScript 3D library. It wraps WebGL (the browser's
low-level GPU API) in scenes, objects, materials, lights, cameras and vector maths.

**Why you need it.** Drawing thousands of day spheres, books and arcs in 3D, and moving through them
smoothly, needs the GPU, and raw WebGL is far too low-level to write by hand.

**What it does here.** Used through React Three Fiber in `src/three/` (the Life timeline:
`TimelineScene`, `DaySphere`, `MonthColumn`, `spiralLayout.ts`) and `src/universe/` (`UniverseScene`,
`BookField`, `TimeRiver`, `ConnectionArcs`, `CameraDirector`). Vector maths such as `THREE.Vector3`
is used directly in the layout and camera code.

**Without it.** No 3D pages, only the list views.

**Alternatives.** *Babylon.js* (a full game engine), *PlayCanvas*, raw WebGL.

**Good to know.**
- three.js is large, which is why the 3D pages are lazy-loaded and the build's chunk warning is
  raised to 1,200 KB (`vite.config.ts`). Pages without 3D never download it.
- `lib/webgl.ts` checks for WebGL first. If it's missing, the Life page falls back to a list view.
- three.js versions are `0.x`, and minor versions can break APIs. Keep `three` and `@types/three` on
  the same version.

---

### `@react-three/fiber`

Range `^9.1.2` · Installed 9.8.0 · Docs: <https://r3f.docs.pmnd.rs>

**What it is.** React Three Fiber (R3F) is a **React renderer for three.js**. Instead of
`scene.add(new THREE.Mesh(...))`, you write `<mesh><boxGeometry/><meshStandardMaterial/></mesh>`, and
R3F creates, updates and disposes the three.js objects for you.

**Why you need it.** The 3D scenes depend on app data (memories, books, people) that changes. With
R3F, a scene re-renders from data like any React component, instead of hand-written code that adds,
updates and removes objects.

**What it does here.**
- `<Canvas>` hosts each scene. Components inside use `useFrame` (run every frame, for animation and
  camera moves) and `useThree` (access the camera and renderer).
- `universe/CameraDirector.tsx` and `three/CameraRig.tsx` move the camera smoothly to a selected book or day.

**Without it.** Imperative three.js code kept in sync with React state by hand.

**Alternatives.** *Threlte* (Svelte), plain three.js.

**Good to know.**
- Version 9 is for React 19 (v8 was for React 18). They must match.
- `useFrame` runs about 60 times a second, so a `setState` inside it re-renders 60 times a second.
  Change refs or three.js objects directly, or throttle it: `BookLabels.tsx` recomputes which labels
  to show only every 300 ms.
- three.js can't read CSS variables, so 3D colours are hex values (`lib/sources.ts`,
  `universe/universeMath.ts`).

---

### `@react-three/drei`

Range `^10.0.6` · Installed 10.7.8 · Docs: <https://drei.docs.pmnd.rs>

**What it is.** A collection of ready-made helpers for React Three Fiber.

**Why you need it.** Camera controls, labels and curved lines are standard, fiddly pieces you don't
want to write yourself.

**What it does here.**

| Helper | Used for | Where |
|---|---|---|
| `OrbitControls` | drag to rotate, scroll to zoom | `UniverseScene.tsx`, `TimelineScene.tsx`, `universe/controls.ts` |
| `Stars` | the starfield background | `UniverseScene.tsx`, `TimelineScene.tsx` |
| `Line` | the time river and timeline lines | `TimeRiver.tsx`, `TimelineScene.tsx` |
| `QuadraticBezierLine` | curved arcs between connected books | `ConnectionArcs.tsx` |
| `Html` | real HTML labels placed in 3D (book titles, year gates, the open book) | `BookLabels.tsx`, `YearGates.tsx`, `OpenBook.tsx`, `ConnectionArcs.tsx`, `TimelineScene.tsx` |

**Without it.** Each of these written by hand (OrbitControls alone is hundreds of lines).

**Good to know.** `Html` elements are real DOM elements layered over the canvas. They're crisp and
accessible, but expensive in large numbers. `BookLabels.tsx` shows titles only when you've zoomed
in (at most 10 at month zoom, 18 at book zoom), and only for books within 70 units of where you're looking.

---

## 4. Styling and components

The UI follows the **shadcn/ui** approach: instead of installing a component library, the
components' source lives in the repo (`src/components/ui/`) and is styled with Tailwind. You own
and can change every component. Four small packages make that work.

### `tailwindcss` and `@tailwindcss/vite`

Range `^4.1.7` · Installed 4.3.3 · Docs: <https://tailwindcss.com/docs>

**What it is.** A **utility-first** CSS framework. Instead of writing CSS classes like `.card {…}`,
you put small utility classes in the markup: `rounded-md border p-4 text-sm`. Tailwind scans your
files and generates only the CSS for the classes you used. Version 4 is configured in CSS (no
`tailwind.config.js`) and has its own Vite plugin.

**Why you need it.** Consistent spacing, colours and dark mode across about 100 components, without
maintaining separate stylesheets or inventing class names.

**What it does here.**
- `src/index.css`: `@import "tailwindcss"`, the theme tokens (`--primary`, `--background`, … in
  `oklch` colours), and a `dark` variant that applies under a `.dark` class (set by `themeStore`).
- `vite.config.ts`: the `tailwindcss()` plugin generates the CSS during dev and build.
- Every component uses utility classes, and `bg-primary` / `text-muted-foreground` refer to the tokens.

**Without it.** Hand-written CSS files, or CSS modules.

**Alternatives.** *CSS Modules*, *vanilla-extract*, *styled-components* (CSS-in-JS, with a runtime cost), *UnoCSS*.

**Good to know.** Class names must appear **whole** in the source. Tailwind can't see a class built
at runtime like `` `bg-${color}-500` ``, so it never generates its CSS. Write full class names, or
use an inline `style` for truly dynamic values.

---

### `class-variance-authority` (cva)

Range `^0.7.1` · Installed 0.7.1 · Docs: <https://cva.style>

**What it is.** Defines a component's **variants** as class lists: give it base classes and a table
of variant → classes, and it returns a function that picks the right classes for the props.

**Why you need it.** A `Button` has six looks (`default`, `destructive`, `outline`, `secondary`,
`ghost`, `link`) and four sizes. Without cva, that's a tangle of `if` statements in each component.

**What it does here.** `components/ui/Button.tsx` (`buttonVariants`) and `components/ui/Badge.tsx`.
`buttonVariants` is exported, so a router `<Link>` can look like a button:
`<Link className={buttonVariants({ size: "sm" })}>`.

**Without it.** Hand-written `switch` statements returning class strings.

**Alternatives.** *tailwind-variants* (similar, with slots).

---

### `clsx` and `tailwind-merge`

`clsx` range `^2.1.1` (installed 2.1.1) · `tailwind-merge` range `^3.3.0` (installed 3.7.0)
Docs: <https://github.com/lukeed/clsx> · <https://github.com/dcastil/tailwind-merge>

**What they are.**
- **`clsx`** joins class names, skipping falsy values: `clsx("p-2", isActive && "bg-accent")`.
- **`tailwind-merge`** resolves **conflicting** Tailwind classes, so the last one wins:
  `twMerge("p-2 p-4")` → `"p-4"`.

**Why you need them.** Components accept a `className` prop so a page can adjust them. Without
merging, `<Button className="h-12">` would end up with both `h-9` and `h-12`, and which one applies
would depend on the order in the CSS file, not your intent.

**What they do here.** Combined into one helper, `cn()`, in `lib/cn.ts`:
`cn(...inputs) = twMerge(clsx(inputs))`. Every component uses `cn()`, for example
`className={cn(buttonVariants({ variant, size }), className)}`.

**Alternatives.** *classnames* (the same idea as clsx, slightly larger). Nothing standard replaces tailwind-merge.

---

### `lucide-react`

Range `^0.511.0` · Installed 0.511.0 · Docs: <https://lucide.dev>

**What it is.** About 1,500 consistent, open-source icons as React components (`<Inbox />`,
`<Sparkles />`). Each import is tree-shaken, so only the icons you use end up in the bundle.

**Why you need it.** Navigation, source types (WhatsApp, Instagram, journal, photo, audio, video),
buttons and empty states all need icons that look like one set.

**What it does here.** `components/Layout.tsx` (sidebar), `lib/sources.ts` (an icon per source type),
`EmptyState.tsx`, `ErrorState.tsx`, `ui/Dialog.tsx` (close button), `universe/` (sparkle on AI titles).

**Alternatives.** *Heroicons*, *Phosphor*, *react-icons* (many sets in one, inconsistent styles).

**Good to know.** Icons inherit `currentColor` and are sized with CSS. Button gives every SVG inside it `size-4`.

---

## 5. Build tools

### `vite`

Range `^6.3.5` · Installed 6.4.3 · Docs: <https://vite.dev>

**What it is.** A frontend build tool:
- **in development**, a dev server that serves your source files almost instantly (native ES
  modules) and hot-swaps edited components without losing state;
- **for production**, a bundler (Rollup) that produces small, hashed, minified files in `dist/`.

**Why you need it.** Browsers can't run TypeScript or JSX, and shouldn't download hundreds of small
files. Something has to compile and bundle, and development should feel instant.

**What it does here.** `vite.config.ts`:
- plugins: `react()` and `tailwindcss()`
- the `@` alias → `src/` (so imports look like `@/components/ui/Button`)
- the dev server on `5173`, proxying `/api` to `VITE_PROXY_TARGET` (default `http://localhost:8000`),
  so development uses the same origin as production
- `chunkSizeWarningLimit: 1200`, because three.js lives in the lazy Life chunk

Scripts: `npm run dev`, `npm run build` (`tsc -b && vite build`), `npm run preview`.

**Without it.** Webpack configuration, or no build at all.

**Alternatives.** *webpack* (slower, more configuration), *Parcel*, *Rsbuild*, *Next.js* (a full
framework with server rendering, which this app doesn't need).

**Good to know.** Only variables starting with `VITE_` reach the browser code
(`import.meta.env.VITE_API_URL`). That's a safety feature: secrets never get bundled by accident.

---

### `@vitejs/plugin-react`

Range `^4.4.1` · Installed 4.7.0 · Docs: <https://github.com/vitejs/vite-plugin-react>

**What it is.** Vite's React plugin: compiles JSX and enables **Fast Refresh** (editing a component
updates it in the browser without a reload and without losing its state).

**Why you need it.** Vite doesn't know React by itself.

---

### `typescript`

Range `~5.8.3` · Installed 5.8.3 · Docs: <https://www.typescriptlang.org/docs/>

**What it is.** JavaScript with types. The compiler (`tsc`) checks the types, and Vite strips them
when building.

**Why you need it.**
- `src/types/api.ts` mirrors `docs/api-contract.md`, so if the backend's response shape changes and
  the frontend isn't updated, the build fails instead of the page breaking for a user.
- It makes refactoring across about 140 source files safe.

**What it does here.** `tsconfig.json` (with project references), `tsconfig.app.json` (the app),
`tsconfig.node.json` (`vite.config.ts`). `npm run typecheck` runs `tsc -b`, and `npm run build`
type-checks before bundling.

**Good to know.** The range is `~5.8.3` (patch updates only), because TypeScript minor versions can
add stricter checks that suddenly break the build.

---

## 6. Type definitions

| Package | Range · Installed | What it is for |
|---|---|---|
| `@types/react`, `@types/react-dom` | `^19.1.x` · 19.3.0 | Types for React (React itself is written in JavaScript). Must match React's major version |
| `@types/three` | `^0.176.0` · 0.176.0 | Types for three.js. Keep the same version as `three` |
| `@types/node` | `^22.15.0` · 22.20.4 | Types for Node.js APIs (`process.env`, `node:url`), used only by `vite.config.ts`. Not available in browser code |

`@types/*` packages contain no code, only type information for the compiler. They're in
`devDependencies` because nothing from them ships to the browser.
