// UI state of the Memories page (the Memory Universe): what is open, where the camera should fly,
// and the quiet notifications. Server data (books, pages, memories) lives in TanStack Query, not here.
//
// Who writes what:
//   the 3D scene (universe/*)        hover, click a book → openBook; reports zoom level and camera x
//   the reader panel (features/…)    openPage, showMemory, visit a connected memory
//   CameraDirector                   reads `flight` and flies the camera along its waypoints
import { create } from "zustand";

export type Vec3 = [number, number, number];

/** How far the camera is from what it looks at — decides what the scene reveals (progressive disclosure). */
export type ZoomLevel = "universe" | "year" | "month" | "book";

export interface Waypoint {
  /** The point the camera looks at. */
  target: Vec3;
  /** Distance from the camera to `target`. */
  distance: number;
  /** Unit vector from target to camera; omitted = keep the current viewing direction. */
  direction?: Vec3;
  durationMs: number;
  /** Shown in the breadcrumb while flying, e.g. "2024", "June", "Andhra Trip". */
  label?: string;
  /** Called when the camera reaches this waypoint (e.g. open the book at the end of a visit). */
  onArrive?: () => void;
}

/** A book that appeared ("new") or gained memories ("grown") while the page was open. */
export interface FreshMark {
  at: number;
  kind: "new" | "grown";
}

export interface Toast {
  id: string;
  title: string;
  body?: string;
  /** Optional action, e.g. open the new book. */
  bookId?: string;
}

interface UniverseState {
  openBookId: string | null;
  openPageId: string | null;
  /** The memory flashed in the page view (the end of a "Visit memory" trip). */
  highlightMemoryId: string | null;
  /** The memory whose original + connections dialog is open. */
  detailMemoryId: string | null;
  /** A pending "Visit memory" request; MemoriesPage looks up its location and plans the flight. */
  visitMemoryId: string | null;
  flight: { id: number; waypoints: Waypoint[] } | null;
  flightLabel: string | null;
  zoom: ZoomLevel;
  cameraX: number;
  hoveredBookId: string | null;
  toasts: Toast[];
  /** Books that appeared or grew while the page was open (drives the subtle animations and "New" badges). */
  freshBooks: Record<string, FreshMark>;
  /** Pages that appeared in an open book while the page was open → when (ms). */
  freshPages: Record<string, number>;

  openBook: (bookId: string) => void;
  closeBook: () => void;
  openPage: (pageId: string | null, highlightMemoryId?: string | null) => void;
  showMemory: (memoryId: string | null) => void;
  visit: (memoryId: string) => void;
  finishVisit: () => void;
  fly: (waypoints: Waypoint[]) => void;
  setFlightLabel: (label: string | null) => void;
  setZoom: (zoom: ZoomLevel) => void;
  setCameraX: (x: number) => void;
  setHoveredBook: (bookId: string | null) => void;
  pushToast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: string) => void;
  markFresh: (bookIds: string[], kind: FreshMark["kind"]) => void;
  markFreshPages: (pageIds: string[]) => void;
}

const MAX_TOASTS = 3;
let nextFlightId = 1;
let nextToastId = 1;

export const useUniverseStore = create<UniverseState>()((set) => ({
  openBookId: null,
  openPageId: null,
  highlightMemoryId: null,
  detailMemoryId: null,
  visitMemoryId: null,
  flight: null,
  flightLabel: null,
  zoom: "universe",
  cameraX: 0,
  hoveredBookId: null,
  toasts: [],
  freshBooks: {},
  freshPages: {},

  openBook: (bookId) => set({ openBookId: bookId, openPageId: null, highlightMemoryId: null }),
  closeBook: () => set({ openBookId: null, openPageId: null, highlightMemoryId: null }),
  openPage: (pageId, highlightMemoryId = null) => set({ openPageId: pageId, highlightMemoryId }),
  showMemory: (memoryId) => set({ detailMemoryId: memoryId }),
  visit: (memoryId) => set({ visitMemoryId: memoryId, detailMemoryId: null }),
  finishVisit: () => set({ visitMemoryId: null }),
  fly: (waypoints) => set({ flight: { id: nextFlightId++, waypoints } }),
  setFlightLabel: (label) => set({ flightLabel: label }),
  setZoom: (zoom) => set((state) => (state.zoom === zoom ? state : { zoom })),
  setCameraX: (cameraX) => set({ cameraX }),
  setHoveredBook: (hoveredBookId) => set((state) => (state.hoveredBookId === hoveredBookId ? state : { hoveredBookId })),
  pushToast: (toast) =>
    set((state) => ({ toasts: [...state.toasts, { ...toast, id: String(nextToastId++) }].slice(-MAX_TOASTS) })),
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
  markFresh: (bookIds, kind) =>
    set((state) => {
      const at = Date.now();
      const fresh = { ...state.freshBooks };
      for (const id of bookIds) fresh[id] = { at, kind };
      return { freshBooks: fresh };
    }),
  markFreshPages: (pageIds) =>
    set((state) => {
      const fresh = { ...state.freshPages };
      for (const id of pageIds) fresh[id] = Date.now();
      return { freshPages: fresh };
    }),
}));
