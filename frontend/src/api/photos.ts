// Photo library endpoints (docs/api-contract.md § Photos). Called from hooks/usePhotos.ts.
// Photos are never analysed — the backend only uses their name and dates. Captions come from the user.
import type { CaptionIngestResponse, Photo, PhotoFilters, PhotosResponse } from "@/types/api";
import { apiFetch } from "./client";

export function getPhotos(filters: PhotoFilters, signal?: AbortSignal) {
  return apiFetch<PhotosResponse>("/photos", {
    query: { start: filters.start, end: filters.end, q: filters.q, caption: filters.caption },
    signal,
  });
}

/** Saves the caption as a draft; it becomes searchable after ingestCaptions(). */
export function saveCaption(memoryId: string, caption: string) {
  return apiFetch<Photo>(`/photos/${encodeURIComponent(memoryId)}/caption`, { method: "PUT", json: { caption } });
}

export function ingestCaptions() {
  return apiFetch<CaptionIngestResponse>("/photos/captions/ingest", { method: "POST" });
}
