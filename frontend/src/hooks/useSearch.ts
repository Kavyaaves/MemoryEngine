// Search hooks → api/search.ts → GET /api/search.
//   Media page → useSearch
//   AI Lab (features/lab/RetrievalComparison) → useRetrieverComparison
import { keepPreviousData, queryOptions, skipToken, useQueries, useQuery } from "@tanstack/react-query";
import { searchMemories } from "@/api/search";
import { queryKeys } from "@/api/queryKeys";
import type { SearchMode, SearchParams, SearchResponse } from "@/types/api";

/** Search results for `params`; does nothing while `params` is null (no query typed yet). */
export function useSearch(params: SearchParams | null) {
  return useQuery({
    queryKey: queryKeys.search.results(params ?? { q: "" }),
    queryFn: params ? ({ signal }) => searchMemories(params, signal) : skipToken,
    // Keep showing the previous results while the next ones load, instead of flashing a skeleton.
    placeholderData: keepPreviousData,
  });
}

export const RETRIEVAL_MODES: SearchMode[] = ["fts", "trgm", "vector", "hybrid"];

export interface TimedSearchResponse extends SearchResponse {
  /** Round-trip time measured in the browser. */
  clientMs: number;
}

/** Run the same query once per retrieval mode, in parallel. Results are in RETRIEVAL_MODES order. */
export function useRetrieverComparison(query: { q: string; k: number } | null) {
  return useQueries({
    queries: RETRIEVAL_MODES.map((mode) => {
      const params: SearchParams | null = query ? { q: query.q, k: query.k, mode } : null;
      // queryOptions() only adds type information, so TypeScript can check each query in the list.
      return queryOptions({
        queryKey: queryKeys.search.timedResults(params ?? { q: "", mode }),
        queryFn: params
          ? async ({ signal }): Promise<TimedSearchResponse> => {
              const startedAt = performance.now();
              const response = await searchMemories(params, signal);
              return { ...response, clientMs: performance.now() - startedAt };
            }
          : skipToken,
        staleTime: 0, // a comparison should always measure a fresh request
      });
    }),
  });
}
