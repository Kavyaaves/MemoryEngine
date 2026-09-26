import type { TimelineBucket } from "@/types/api";
import { SOURCE_META, totalsBySource } from "@/lib/sources";

/** Colour key drawn over the 3D scene, listing only the source types that actually occur. */
export function SourceLegend({ months }: { months: TimelineBucket[] }) {
  const totals = totalsBySource(months);
  const presentSources = Object.entries(SOURCE_META).filter(([type]) => totals[type]);

  return (
    <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-x-3 gap-y-1 rounded-md bg-black/50 px-2.5 py-1.5 text-[11px] text-white/85 backdrop-blur">
      {presentSources.map(([type, meta]) => (
        <span key={type} className="flex items-center gap-1.5">
          <span className="size-2 rounded-full" style={{ background: meta.color }} aria-hidden />
          {meta.label}
        </span>
      ))}
    </div>
  );
}
