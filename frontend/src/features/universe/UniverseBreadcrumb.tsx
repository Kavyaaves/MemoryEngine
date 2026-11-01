// Where you are: Memory Universe › 2024 › June › Andhra Trip › 14 Jun.
// The year and month come from where the camera is along the time river; while a "Visit memory"
// trip is flying, the step it is travelling to is shown.
import { ChevronRight, Orbit } from "lucide-react";
import type { UniverseLayout } from "@/types/api";
import { useUniverseStore } from "@/stores/universeStore";
import { MONTH_NAMES, xToDate } from "@/universe/universeMath";

interface UniverseBreadcrumbProps {
  layout: UniverseLayout;
  bookTitle: string | null;
  pageDay: string | null;
}

export function UniverseBreadcrumb({ layout, bookTitle, pageDay }: UniverseBreadcrumbProps) {
  const cameraX = useUniverseStore((state) => state.cameraX);
  const zoom = useUniverseStore((state) => state.zoom);
  const flightLabel = useUniverseStore((state) => state.flightLabel);
  const date = xToDate(cameraX, layout);

  const steps = [String(date.getUTCFullYear())];
  if (zoom !== "universe") steps.push(MONTH_NAMES[date.getUTCMonth()]);
  if (bookTitle) steps.push(bookTitle);
  if (pageDay) steps.push(new Date(`${pageDay}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" }));

  return (
    <div className="pointer-events-none flex min-w-0 flex-wrap items-center gap-1 text-xs text-slate-300">
      <Orbit className="size-3.5 text-indigo-200" />
      <span className="text-slate-400">Memory Universe</span>
      {steps.map((step) => (
        <span key={step} className="inline-flex min-w-0 items-center gap-1">
          <ChevronRight className="size-3 text-slate-600" />
          <span className="max-w-48 truncate">{step}</span>
        </span>
      ))}
      {flightLabel && (
        <span className="ml-2 animate-pulse rounded-full bg-indigo-400/15 px-2 py-0.5 text-indigo-200">→ {flightLabel}</span>
      )}
    </div>
  );
}
