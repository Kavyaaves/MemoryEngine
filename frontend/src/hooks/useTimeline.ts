// Timeline hooks used by the Life page (pages/Life, features/timeline, three/) → api/timeline.ts.
import { skipToken, useQuery } from "@tanstack/react-query";
import { getTimeline, getTimelineDay } from "@/api/timeline";
import { queryKeys } from "@/api/queryKeys";
import { monthRange } from "@/lib/periods";
import type { DayResponse, TimelineBucket, TimelineParams, TimelineResponse } from "@/types/api";

// `select` functions live outside the hooks so TanStack Query can reuse their result between renders.
function bucketsSortedByPeriod(response: TimelineResponse): TimelineBucket[] {
  return [...response.buckets].sort((a, b) => a.period.localeCompare(b.period));
}

function memoriesSortedByTime(response: DayResponse) {
  return [...response.memories].sort((a, b) => (a.timestamp ?? "").localeCompare(b.timestamp ?? ""));
}

/** Memory counts for every month, oldest first. */
export function useTimelineMonths() {
  const params: TimelineParams = { granularity: "month" };
  return useQuery({
    queryKey: queryKeys.timeline.buckets(params),
    queryFn: () => getTimeline(params),
    select: bucketsSortedByPeriod,
  });
}

/** Memory counts for each day of `month` ("YYYY-MM"); does not fetch while no month is selected. */
export function useTimelineDays(month: string | null) {
  const params: TimelineParams | null = month ? { granularity: "day", ...monthRange(month) } : null;
  return useQuery({
    queryKey: queryKeys.timeline.buckets(params ?? { granularity: "day" }),
    // skipToken = "don't run this query yet" (the type-safe alternative to `enabled: false`).
    queryFn: params ? () => getTimeline(params) : skipToken,
    select: bucketsSortedByPeriod,
  });
}

/** All memories of one day ("YYYY-MM-DD"), in chronological order. */
export function useTimelineDay(date: string) {
  return useQuery({
    queryKey: queryKeys.timeline.day(date),
    queryFn: () => getTimelineDay(date),
    select: memoriesSortedByTime,
  });
}
