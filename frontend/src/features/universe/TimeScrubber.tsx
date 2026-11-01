// A slim strip of years along the bottom: where you are in time, and a way to jump.
// Each year's width is the same (time is linear, like the river); its brightness shows how full it is.
import type { UniverseLayout, UniversePeriod } from "@/types/api";
import { cn } from "@/lib/cn";
import { dateX } from "@/universe/universeMath";

interface TimeScrubberProps {
  years: UniversePeriod[];
  layout: UniverseLayout;
  cameraX: number;
  onSelectYear: (year: string) => void;
}

export function TimeScrubber({ years, layout, cameraX, onSelectYear }: TimeScrubberProps) {
  if (years.length === 0) return null;
  const busiest = Math.max(...years.map((year) => year.memory_count), 1);
  const start = dateX(`${years[0].period}-01-01`, layout);
  const end = dateX(`${years.at(-1)!.period}-12-31`, layout);
  const here = Math.min(1, Math.max(0, (cameraX - start) / (end - start || 1)));

  return (
    <nav aria-label="Years" className="pointer-events-auto relative flex h-9 w-full max-w-3xl items-stretch overflow-hidden rounded-full border border-white/10 bg-slate-950/55 backdrop-blur-xl">
      {years.map((year) => {
        const x = dateX(`${year.period}-07-01`, layout);
        const active = Math.abs(x - cameraX) < (dateX("2001-01-01", layout) - dateX("2000-01-01", layout)) / 2;
        return (
          <button
            key={year.period}
            type="button"
            onClick={() => onSelectYear(year.period)}
            title={`${year.memory_count.toLocaleString()} memories · ${year.book_count} books`}
            className={cn(
              "relative flex-1 cursor-pointer border-r border-white/5 text-[11px] tracking-widest transition-colors last:border-r-0 hover:bg-white/10",
              active ? "text-white" : "text-slate-400",
            )}
          >
            <span className="absolute inset-x-0 bottom-0 h-0.5 bg-indigo-300"
                  style={{ opacity: 0.15 + 0.85 * (year.memory_count / busiest) }} />
            {year.period}
          </button>
        );
      })}
      <span aria-hidden className="pointer-events-none absolute inset-y-1 w-px bg-amber-200/80 transition-[left] duration-300"
            style={{ left: `${here * 100}%` }} />
    </nav>
  );
}
