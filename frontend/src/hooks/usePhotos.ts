// Photo library hooks (Media page → Photos tab) → api/photos.ts.
// Lifecycle of a caption: type it → useSaveCaption stores it as a draft ("pending")
// → "Ingest Captions" (useIngestCaptions) makes every pending caption searchable.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getPhotos, ingestCaptions, saveCaption } from "@/api/photos";
import { invalidateMemoryData, queryKeys } from "@/api/queryKeys";
import type { PhotoFilters } from "@/types/api";

export function usePhotos(filters: PhotoFilters) {
  return useQuery({
    queryKey: queryKeys.photos.list(filters),
    queryFn: ({ signal }) => getPhotos(filters, signal),
    // Keep showing the current photos while a new filter loads, instead of flashing a skeleton.
    placeholderData: keepPreviousData,
  });
}

export function useSaveCaption() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memoryId, caption }: { memoryId: string; caption: string }) => saveCaption(memoryId, caption),
    // Refetch so the caption badge and the "pending" count update.
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.photos.all }),
  });
}

export function useIngestCaptions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ingestCaptions,
    // Photo memories got new text: timeline, search and the photo list all change.
    onSuccess: () => invalidateMemoryData(queryClient),
  });
}
