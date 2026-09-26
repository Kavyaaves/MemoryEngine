// The 2D alternative to the 3D Life explorer (used when WebGL is missing or the user picks "List"):
// years → months with a bar per month → expand a month to see its days → click a day.
import { ChevronDown, ChevronRight } from "lucide-react";
import { Spinner } from "@/components/ui/Spinner";
import type { TimelineBucket } from "@/types/api";
import { cn } from "@/lib/cn";
import { formatPeriod, monthName } from "@/lib/periods";
import { dominantSource, sourceMeta } from "@/lib/sources";

interface TimelineListProps {
  months: TimelineBucket[];
  /** Day buckets of the selected month. */
  days: TimelineBucket[];
  daysLoading: boolean;
  selectedMonth: string | null;
  selectedDay: string | null;
  onSelectMonth: (month: string | null) => void;
  onSelectDay: (day: string) => void;
}

/** Newest year first, and newest month first within each year. */
function groupByYear(months: TimelineBucket[]): [string, TimelineBucket[]][] {
  const byYear = new Map<string, TimelineBucket[]>();
  for (const bucket of [...months].sort((a, b) => b.period.localeCompare(a.period))) {
    const year = bucket.period.slice(0, 4);
    byYear.set(year, [...(byYear.get(year) ?? []), bucket]);
  }
  return [...byYear.entries()];
}

export function TimelineList({
  months,
  days,
  daysLoading,
  selectedMonth,
  selectedDay,
  onSelectMonth,
  onSelectDay,
}: TimelineListProps) {
  const busiestMonth = Math.max(1, ...months.map((month) => month.count));
  const busiestDay = Math.max(1, ...days.map((day) => day.count));

  return (
    <div className="flex flex-col gap-5">
      {groupByYear(months).map(([year, yearMonths]) => (
        <section key={year}>
          <h3 className="mb-2 flex items-baseline gap-2 font-semibold">
            {year}
            <span className="text-xs font-normal text-muted-foreground">
              {yearMonths.reduce((sum, month) => sum + month.count, 0).toLocaleString()} memories
            </span>
          </h3>
          <ul className="flex flex-col gap-1">
            {yearMonths.map((monthBucket) => {
              const month = monthBucket.period.slice(0, 7);
              const open = selectedMonth === month;
              return (
                <li key={month}>
                  <button
                    type="button"
                    onClick={() => onSelectMonth(open ? null : month)}
                    aria-expanded={open}
                    className={cn(
                      "grid w-full cursor-pointer grid-cols-[1rem_3rem_1fr_4rem] items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent",
                      open && "bg-accent",
                    )}
                  >
                    {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    <span>{monthName(Number(month.slice(5, 7)))}</span>
                    <span className="h-2 overflow-hidden rounded-full bg-muted">
                      <span
                        className="block h-full rounded-full"
                        style={{
                          width: `${(monthBucket.count / busiestMonth) * 100}%`,
                          background: sourceMeta(dominantSource(monthBucket.sources)).color,
                        }}
                      />
                    </span>
                    <span className="text-right tabular-nums text-muted-foreground">
                      {monthBucket.count.toLocaleString()}
                    </span>
                  </button>

                  {open && (
                    <div className="ml-6 mt-1 border-l pl-3">
                      {daysLoading ? (
                        <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
                          <Spinner className="size-3" /> Loading days…
                        </div>
                      ) : days.length === 0 ? (
                        <p className="py-2 text-xs text-muted-foreground">No day-level data.</p>
                      ) : (
                        <ul className="flex flex-col gap-0.5 py-1">
                          {days.map((dayBucket) => {
                            const day = dayBucket.period.slice(0, 10);
                            return (
                              <li key={day}>
                                <button
                                  type="button"
                                  onClick={() => onSelectDay(day)}
                                  aria-pressed={selectedDay === day}
                                  className={cn(
                                    "grid w-full cursor-pointer grid-cols-[6rem_1fr_3rem] items-center gap-2 rounded px-2 py-1 text-left text-xs hover:bg-accent",
                                    selectedDay === day && "bg-primary/15 text-primary",
                                  )}
                                >
                                  <span>{formatPeriod(day)}</span>
                                  <span className="h-1.5 overflow-hidden rounded-full bg-muted">
                                    <span
                                      className="block h-full rounded-full bg-primary/70"
                                      style={{ width: `${(dayBucket.count / busiestDay) * 100}%` }}
                                    />
                                  </span>
                                  <span className="text-right tabular-nums">{dayBucket.count}</span>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
