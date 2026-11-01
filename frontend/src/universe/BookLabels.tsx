// Book titles, shown only when they help: when you are close (zoom "month" or "book") and only for
// the books nearest the point you are looking at. Thousands of labels would bury the scene.
// The hovered book always gets a fuller tooltip: title, dates, how many memories, who is in it.
import { useRef, useState, type RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { Sparkles } from "lucide-react";
import type { Book } from "@/types/api";
import { useUniverseStore, type ZoomLevel } from "@/stores/universeStore";
import { formatDate } from "@/lib/format";
import type { OrbitControlsHandle } from "./controls";

const MAX_LABELS = { universe: 0, year: 0, month: 10, book: 18 } satisfies Record<ZoomLevel, number>;
const LABEL_RANGE = 70; // world units from the camera target
const REFRESH_MS = 300;

interface BookLabelsProps {
  books: Book[];
  zoom: ZoomLevel;
  openBookId: string | null;
  controlsRef: RefObject<OrbitControlsHandle | null>;
}

export function BookLabels({ books, zoom, openBookId, controlsRef }: BookLabelsProps) {
  const [nearIds, setNearIds] = useState<string[]>([]);
  const lastRefresh = useRef(0);
  const hoveredBookId = useUniverseStore((state) => state.hoveredBookId);
  const freshBooks = useUniverseStore((state) => state.freshBooks);

  useFrame(() => {
    const now = performance.now();
    const controls = controlsRef.current;
    if (!controls || now - lastRefresh.current < REFRESH_MS) return;
    lastRefresh.current = now;
    const limit = MAX_LABELS[zoom];
    const target = controls.target;
    const nearest = limit === 0 ? [] : books
      .map((book) => ({ id: book.id, d: Math.hypot(book.position[0] - target.x, book.position[1] - target.y,
        book.position[2] - target.z) }))
      .filter((entry) => entry.d < LABEL_RANGE && entry.id !== openBookId)
      .sort((a, b) => a.d - b.d)
      .slice(0, limit)
      .map((entry) => entry.id);
    if (nearest.join() !== nearIds.join()) setNearIds(nearest);
  });

  const byId = new Map(books.map((book) => [book.id, book]));
  const hovered = hoveredBookId ? byId.get(hoveredBookId) : undefined;

  return (
    <group>
      {nearIds.filter((id) => id !== hoveredBookId).map((id) => {
        const book = byId.get(id);
        if (!book) return null;
        return (
          <Html key={id} position={[book.position[0], book.position[1] + 1.35, book.position[2]]} center
                zIndexRange={[30, 20]}>
            <div className="pointer-events-none max-w-44 select-none truncate text-center text-[11px] text-white/75 drop-shadow">
              {freshBooks[id] && <Sparkles className="mr-1 inline size-3 text-amber-200" />}
              {book.title}
            </div>
          </Html>
        );
      })}
      {hovered && hovered.id !== openBookId && (
        <Html position={[hovered.position[0], hovered.position[1] + 1.6, hovered.position[2]]} center
              zIndexRange={[60, 50]}>
          <div className="pointer-events-none w-60 select-none rounded-lg border border-white/10 bg-slate-950/80 px-3 py-2 text-xs text-white shadow-xl backdrop-blur">
            <div className="flex items-center gap-1 font-medium">
              {freshBooks[hovered.id] && <Sparkles className="size-3 shrink-0 text-amber-200" />}
              <span className="truncate">{hovered.title}</span>
            </div>
            <div className="mt-0.5 text-white/60">
              {formatDate(hovered.start_at)}
              {hovered.end_at.slice(0, 10) !== hovered.start_at.slice(0, 10) && ` – ${formatDate(hovered.end_at)}`}
            </div>
            <div className="mt-1 text-white/70">
              {hovered.memory_count.toLocaleString()} memories · {hovered.page_count} pages
              {hovered.photo_count > 0 && ` · ${hovered.photo_count} photos`}
            </div>
            {hovered.people.length > 0 && (
              <div className="mt-1 truncate text-white/60">with {hovered.people.map((p) => p.name).join(", ")}</div>
            )}
            <div className="mt-1.5 text-[10px] uppercase tracking-wider text-indigo-200/70">Click to open</div>
          </div>
        </Html>
      )}
    </group>
  );
}
