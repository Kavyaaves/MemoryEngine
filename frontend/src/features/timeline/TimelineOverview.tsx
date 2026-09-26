// Life page side panel when nothing is selected: totals and mood for the whole timeline.
import { MoodChart } from "@/features/sentiment/MoodChart";
import type { TimelineBucket } from "@/types/api";
import { formatPeriod } from "@/lib/periods";
import { sourceMeta, totalsBySource } from "@/lib/sources";

/** `months` must be sorted oldest first (useTimelineMonths does this). */
export function TimelineOverview({ months }: { months: TimelineBucket[] }) {
  const totalMemories = months.reduce((sum, month) => sum + month.count, 0);
  const sourcesByCount = Object.entries(totalsBySource(months)).sort((a, b) => b[1] - a[1]);
  const firstMonth = months[0]?.period;
  const lastMonth = months.at(-1)?.period;

  return (
    <div className="flex flex-col gap-4 text-sm">
      <h2 className="font-semibold">Overview</h2>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Memories" value={totalMemories.toLocaleString()} />
        <Stat label="Months" value={String(months.length)} />
        <Stat label="From" value={firstMonth ? formatPeriod(firstMonth) : "—"} />
        <Stat label="To" value={lastMonth ? formatPeriod(lastMonth) : "—"} />
      </div>
      <div className="flex flex-col gap-1.5">
        {sourcesByCount.map(([type, count]) => (
          <div key={type} className="flex items-center gap-2">
            <span className="size-2 rounded-full" style={{ background: sourceMeta(type).color }} aria-hidden />
            <span className="flex-1">{sourceMeta(type).label}</span>
            <span className="tabular-nums text-muted-foreground">{count.toLocaleString()}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-1.5">
        <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Mood by month</h3>
        <MoodChart />
      </div>
      <p className="text-xs text-muted-foreground">Select a month to see its days; select a day to read what happened.</p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/50 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-semibold">{value}</div>
    </div>
  );
}
