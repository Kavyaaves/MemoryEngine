// Media page → Photos tab: every uploaded photo, filtered by its metadata, with a caption editor each.
// Photos are never analysed — only their name and dates are used. Captions typed here become searchable
// (in search, Ask and the timeline) when the user clicks "Ingest Captions".
// Data flow: filters → usePhotos (hooks/usePhotos.ts) → GET /api/photos
//            "Ingest Captions" → useIngestCaptions → POST /api/photos/captions/ingest
import { useState, type FormEvent } from "react";
import { Image as ImageIcon, Search, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { useIngestCaptions, usePhotos } from "@/hooks/usePhotos";
import type { CaptionFilter, PhotoFilters } from "@/types/api";
import { PhotoCard } from "./PhotoCard";

const CAPTION_FILTERS: { value: CaptionFilter; label: string }[] = [
  { value: "all", label: "All photos" },
  { value: "none", label: "No caption" },
  { value: "pending", label: "Caption not ingested" },
  { value: "ingested", label: "Caption ingested" },
];

export function PhotoLibrary() {
  const [filters, setFilters] = useState<PhotoFilters>({ caption: "all" });
  const [textInput, setTextInput] = useState("");
  const photos = usePhotos(filters);
  const ingest = useIngestCaptions();
  const pending = photos.data?.pending_captions ?? 0;

  const updateFilter = (change: Partial<PhotoFilters>) => setFilters((current) => ({ ...current, ...change }));
  const onSubmitText = (event: FormEvent) => {
    event.preventDefault();
    updateFilter({ q: textInput.trim() || undefined });
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Photos are never analysed — only their file name and dates (EXIF, file modified) are used, which places them
        in the timeline. Write a caption to make a photo searchable, then click <strong>Ingest Captions</strong>.
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_auto] lg:items-end">
        <form onSubmit={onSubmitText} className="flex flex-col gap-1.5">
          <Label htmlFor="photo_q">File name or caption</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="photo_q"
              value={textInput}
              onChange={(event) => setTextInput(event.target.value)}
              onBlur={() => updateFilter({ q: textInput.trim() || undefined })}
              placeholder="IMG_2024, goa, birthday…"
              className="memory-text pl-8"
            />
          </div>
        </form>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="photo_start">From</Label>
          <Input
            id="photo_start"
            type="date"
            value={filters.start ?? ""}
            onChange={(event) => updateFilter({ start: event.target.value || undefined })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="photo_end">To</Label>
          <Input
            id="photo_end"
            type="date"
            value={filters.end ?? ""}
            onChange={(event) => updateFilter({ end: event.target.value || undefined })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="photo_caption">Caption</Label>
          <Select
            id="photo_caption"
            value={filters.caption ?? "all"}
            onChange={(event) => updateFilter({ caption: event.target.value as CaptionFilter })}
          >
            {CAPTION_FILTERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
        <Button onClick={() => ingest.mutate()} disabled={pending === 0 || ingest.isPending}>
          {ingest.isPending ? <Spinner /> : <Sparkles />}
          Ingest Captions{pending > 0 && ` (${pending})`}
        </Button>
      </div>

      {ingest.isError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {ingest.error.message}
        </p>
      )}
      {ingest.isSuccess && (
        <p role="status" className="text-sm text-success">
          Ingested {ingest.data.ingested} caption{ingest.data.ingested === 1 ? "" : "s"}
          {ingest.data.embedded > 0 && ` · ${ingest.data.embedded} embedded for semantic search`}.
        </p>
      )}

      {photos.isPending ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {Array.from({ length: 10 }, (_, index) => (
            <Skeleton key={index} className="aspect-[3/4]" />
          ))}
        </div>
      ) : photos.isError ? (
        <ErrorState error={photos.error} onRetry={() => void photos.refetch()} />
      ) : photos.data.photos.length === 0 ? (
        <EmptyState
          icon={<ImageIcon />}
          title="No photos"
          description="No photos match these filters. Upload photos on the Upload page — they are dated from their metadata and appear here and in the timeline."
        />
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {photos.data.photos.length} photo{photos.data.photos.length === 1 ? "" : "s"}
            {photos.isFetching && " · updating…"}
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {photos.data.photos.map((photo) => (
              <PhotoCard key={photo.memory_id} photo={photo} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
