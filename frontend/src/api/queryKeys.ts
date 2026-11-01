// The one place that defines TanStack Query cache keys. Every hook in hooks/ takes its key from here.
// Keys are arrays and invalidation matches by prefix: invalidating ["people"] refreshes the people list,
// every person detail and the alias suggestions in one go. That is why related keys share a first element.
import type { QueryClient } from "@tanstack/react-query";
import type { MoodTimelineParams, PhotoFilters, SearchParams, TimelineParams } from "@/types/api";

export const queryKeys = {
  me: ["me"],
  health: ["health"],
  jobs: ["jobs"],
  sources: ["sources"],
  timeline: {
    all: ["timeline"],
    buckets: (params: TimelineParams) => ["timeline", "buckets", params],
    day: (date: string) => ["timeline", "day", date],
  },
  people: {
    all: ["people"],
    list: ["people", "list"],
    detail: (personId: string) => ["people", "detail", personId],
    aliasSuggestions: ["people", "alias-suggestions"],
  },
  search: {
    all: ["search"],
    results: (params: SearchParams) => ["search", "results", params],
    // The AI Lab caches results together with the measured client-side latency — a different
    // data shape, so it must not share cache entries with plain results.
    timedResults: (params: SearchParams) => ["search", "timed", params],
  },
  lab: {
    usage: ["lab", "usage"],
    config: ["lab", "config"],
  },
  photos: {
    all: ["photos"],
    list: (filters: PhotoFilters) => ["photos", "list", filters],
  },
  sentiment: {
    all: ["sentiment"],
    timeline: (params: MoodTimelineParams) => ["sentiment", "timeline", params],
    status: ["sentiment", "status"],
  },
  universe: {
    all: ["universe"],
    snapshot: ["universe", "snapshot"],
    book: (bookId: string) => ["universe", "book", bookId],
    page: (pageId: string) => ["universe", "page", pageId],
    memory: (memoryId: string) => ["universe", "memory", memoryId],
    changes: (after: number) => ["universe", "changes", after],
  },
};

/**
 * Mark everything derived from memories as stale so it is refetched.
 * Call after the memories themselves change: an ingestion job finished, a source was deleted,
 * or an alias was merged into a person.
 */
export function invalidateMemoryData(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.sources });
  void queryClient.invalidateQueries({ queryKey: queryKeys.timeline.all });
  void queryClient.invalidateQueries({ queryKey: queryKeys.people.all });
  void queryClient.invalidateQueries({ queryKey: queryKeys.search.all });
  void queryClient.invalidateQueries({ queryKey: queryKeys.photos.all });
  void queryClient.invalidateQueries({ queryKey: queryKeys.sentiment.all });
  // Refetching the universe never moves the camera: book positions come from the server and are fixed.
  void queryClient.invalidateQueries({ queryKey: queryKeys.universe.all });
}
