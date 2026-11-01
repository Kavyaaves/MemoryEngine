// Pure math for the Memory Universe (no React, no three.js objects).
// Book positions come from the server (backend app/universe/layout.py) and are never recomputed here.
// This file only places things the server doesn't store — year gates, month ticks, camera stops —
// using the same constants the server sends in `universe.layout`, so everything lines up.
import type { Book, MemoryLocation, UniverseLayout } from "@/types/api";
import type { Vec3, Waypoint, ZoomLevel } from "@/stores/universeStore";

const DAY_MS = 86_400_000;

/** x on the time river for a calendar date "YYYY-MM-DD" (same formula as the server's time_x). */
export function dateX(isoDate: string, layout: UniverseLayout): number {
  const [year, month, day] = isoDate.slice(0, 10).split("-").map(Number);
  const [originYear, originMonth, originDay] = layout.origin.split("-").map(Number);
  const days = Math.round((Date.UTC(year, month - 1, day) - Date.UTC(originYear, originMonth - 1, originDay)) / DAY_MS);
  return days * layout.units_per_day;
}

/** The calendar date at x (inverse of dateX) — used to name the year/month the camera is over. */
export function xToDate(x: number, layout: UniverseLayout): Date {
  const [originYear, originMonth, originDay] = layout.origin.split("-").map(Number);
  return new Date(Date.UTC(originYear, originMonth - 1, originDay) + Math.round(x / layout.units_per_day) * DAY_MS);
}

// Camera distance → how much detail the scene shows (progressive disclosure: years → months → books → labels).
const ZOOM_THRESHOLDS: [number, ZoomLevel][] = [
  [170, "universe"],
  [75, "year"],
  [26, "month"],
];

export function zoomFor(distance: number): ZoomLevel {
  for (const [minDistance, level] of ZOOM_THRESHOLDS) if (distance >= minDistance) return level;
  return "book";
}

/** Calm colours per event type (three.js needs hex, it can't read CSS variables). */
export const EVENT_COLORS: Record<string, string> = {
  trip: "#5eead4",
  celebration: "#fbbf24",
  work: "#93c5fd",
  study: "#a5b4fc",
  relationship: "#f9a8d4",
  family: "#fdba74",
  move: "#86efac",
  health: "#fca5a5",
  photos: "#d8b4fe",
  everyday: "#c7d2fe",
  other: "#cbd5e1",
};

export function eventColor(eventType: string): string {
  return EVENT_COLORS[eventType] ?? EVENT_COLORS.other;
}

/** Bigger books hold more memories — gently (log scale), so one huge chat doesn't dwarf everything. */
export function bookScale(memoryCount: number): number {
  return Math.min(1.9, 0.75 + 0.3 * Math.log10(memoryCount + 1));
}

function normalize([x, y, z]: Vec3): Vec3 {
  const length = Math.hypot(x, y, z) || 1;
  return [x / length, y / length, z / length];
}

/** Looking at the river from the side and a little above — the "overview" angle. */
export const OVERVIEW_DIRECTION: Vec3 = normalize([0.18, 0.42, 0.89]);

/** A camera direction for looking at a book: from outside the river, slightly ahead in time and above. */
export function bookViewDirection([, y, z]: Vec3): Vec3 {
  const radius = Math.hypot(y, z) || 1;
  return normalize([0.35, y / radius + 0.35, z / radius]);
}

/** How far the camera stays from an open book (the page arc must fit on screen). */
export const BOOK_VIEW_DISTANCE = 12;
/** The camera looks this far to the right of an open book, so the book sits left of the reader panel. */
export const BOOK_VIEW_SHIFT = 2.2;

/** The screen's "right" for a camera looking along -direction with world-up (0, 1, 0). */
export function screenRight([dx, , dz]: Vec3): Vec3 {
  return normalize([dz, 0, -dx]);
}

function add(a: Vec3, b: Vec3, scale = 1): Vec3 {
  return [a[0] + b[0] * scale, a[1] + b[1] * scale, a[2] + b[2] * scale];
}

/** Where the reader panel is: beside the scene (wide screens) or a bottom sheet (phones). */
export type ReaderPlacement = "right" | "bottom";

export function readerPlacement(): ReaderPlacement {
  return window.matchMedia("(min-width: 768px)").matches ? "right" : "bottom";
}

/** The point to look at so that a book at `position` stays clear of the reader panel:
 *  left of centre when the panel is on the right, above centre when it is a bottom sheet. */
export function bookViewTarget(position: Vec3, placement: ReaderPlacement = "right"): Vec3 {
  if (placement === "bottom") return add(position, [0, -1, 0], BOOK_VIEW_SHIFT);
  return add(position, screenRight(bookViewDirection(position)), BOOK_VIEW_SHIFT);
}

/** Where the camera ends up when a book is open (OpenBook turns the book and pages to face it). */
export function bookCameraPosition(position: Vec3): Vec3 {
  return add(bookViewTarget(position), bookViewDirection(position), BOOK_VIEW_DISTANCE);
}

export const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
  "October", "November", "December"];

/** Waypoints for "Visit memory": Universe → year → month → book (then the page view opens the exact message). */
/** Seeing a whole year: close enough that its books are visible (zoom level "year"). */
export const YEAR_VIEW_DISTANCE = 150;

export function visitWaypoints(location: MemoryLocation, layout: UniverseLayout,
                               placement: ReaderPlacement = "right"): Waypoint[] {
  const month = Number(location.month.slice(5, 7));
  return [
    { target: [dateX(`${location.year}-07-01`, layout), 0, 0], distance: 210, direction: OVERVIEW_DIRECTION,
      durationMs: 1400, label: location.year },
    { target: [dateX(`${location.month}-15`, layout), 0, 0], distance: 62, direction: OVERVIEW_DIRECTION,
      durationMs: 1300, label: MONTH_NAMES[month - 1] },
    { target: bookViewTarget(location.position, placement), distance: BOOK_VIEW_DISTANCE,
      direction: bookViewDirection(location.position), durationMs: 1500, label: location.book_title },
  ];
}

/** One glide to a book. */
export function bookWaypoint(book: Book, placement: ReaderPlacement = "right"): Waypoint {
  return { target: bookViewTarget(book.position, placement), distance: BOOK_VIEW_DISTANCE,
    direction: bookViewDirection(book.position), durationMs: 1400, label: book.title };
}

/** Pull back to see a whole year. */
export function yearWaypoint(year: string, layout: UniverseLayout): Waypoint {
  return { target: [dateX(`${year}-07-01`, layout), 0, 0], distance: YEAR_VIEW_DISTANCE, direction: OVERVIEW_DIRECTION,
    durationMs: 1600, label: year };
}

/** Smooth start and stop (smootherstep): calm, no sudden jerks. */
export function ease(t: number): number {
  const clamped = Math.min(1, Math.max(0, t));
  return clamped * clamped * clamped * (clamped * (clamped * 6 - 15) + 10);
}
