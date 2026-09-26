// Timeline endpoints (docs/api-contract.md § Timeline). Called from hooks/useTimeline.ts.
import type { DayResponse, TimelineParams, TimelineResponse } from "@/types/api";
import { apiFetch } from "./client";

/** Memory counts per year/month/day. `start` and `end` are inclusive YYYY-MM-DD dates. */
export function getTimeline(params: TimelineParams) {
  return apiFetch<TimelineResponse>("/timeline", {
    query: { granularity: params.granularity, start: params.start, end: params.end },
  });
}

/** Every memory on one day (`date` is YYYY-MM-DD). */
export function getTimelineDay(date: string) {
  return apiFetch<DayResponse>(`/timeline/day/${encodeURIComponent(date)}`);
}
