// GET /api/search (docs/api-contract.md § Search). Called from hooks/useSearch.ts.
import type { SearchParams, SearchResponse } from "@/types/api";
import { apiFetch } from "./client";

export function searchMemories(params: SearchParams, signal?: AbortSignal) {
  return apiFetch<SearchResponse>("/search", {
    query: {
      q: params.q,
      start: params.start,
      end: params.end,
      person_id: params.person_id,
      source_type: params.source_type,
      k: params.k ?? 20,
      mode: params.mode ?? "hybrid",
    },
    signal,
  });
}
