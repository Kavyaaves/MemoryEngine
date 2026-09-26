// Life page side panel for a selected month: a short summary and the list of its days.
// It reads the same cached queries as LifePage (TanStack Query de-duplicates them: one request each).
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { useTimelineDays, useTimelineMonths } from "@/hooks/useTimeline";
import { formatPeriod } from "@/lib/periods";
import { dominantSource, sourceMeta } from "@/lib/sources";

interface MonthPanelProps {
  /** "YYYY-MM" */
  month: string;
  onSelectDay: (day: string) => void;
  onClear: () => void;
}

export function MonthPanel({ month, onSelectDay, onClear }: MonthPanelProps) {
  const months = useTimelineMonths();
  const days = useTimelineDays(month);
  const monthBucket = months.data?.find((bucket) => bucket.period.startsWith(month));

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold">{formatPeriod(month)}</h2>
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear
        </Button>
      </div>

      {monthBucket && (
        <div className="mb-3 text-sm text-muted-foreground">
          {monthBucket.count.toLocaleString()} memories · mostly {sourceMeta(dominantSource(monthBucket.sources)).label}
          {monthBucket.top_people.length > 0 && (
            <div className="memory-text mt-1">with {monthBucket.top_people.slice(0, 5).join(", ")}</div>
          )}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {days.isPending ? (
          <LoadingState label="Loading days…" />
        ) : days.isError ? (
          <ErrorState error={days.error} onRetry={() => void days.refetch()} />
        ) : days.data.length === 0 ? (
          <EmptyState title="No day-level data" />
        ) : (
          <ul className="flex flex-col gap-1">
            {days.data.map((dayBucket) => {
              const day = dayBucket.period.slice(0, 10);
              return (
                <li key={day}>
                  <button
                    type="button"
                    onClick={() => onSelectDay(day)}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
                  >
                    <span
                      className="size-2 rounded-full"
                      style={{ background: sourceMeta(dominantSource(dayBucket.sources)).color }}
                      aria-hidden
                    />
                    <span className="flex-1">{formatPeriod(day)}</span>
                    <span className="tabular-nums text-muted-foreground">{dayBucket.count}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
