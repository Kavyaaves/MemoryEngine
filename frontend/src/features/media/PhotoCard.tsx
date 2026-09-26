// One photo in the library: the picture, its metadata (name + dates) and a caption editor.
// Saving stores the caption as a draft; the "Ingest Captions" button (PhotoLibrary) makes it searchable.
import { useState } from "react";
import { Check, Save } from "lucide-react";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { Textarea } from "@/components/ui/Textarea";
import { useSaveCaption } from "@/hooks/usePhotos";
import { formatDateTime } from "@/lib/format";
import type { CaptionStatus, Photo, PhotoDateSource } from "@/types/api";
import { MediaThumb } from "./MediaThumb";

/** How the timeline date was found, in words. */
const DATE_SOURCE_LABELS: Record<PhotoDateSource, string> = {
  exif_taken: "taken (EXIF)",
  filename: "from file name",
  exif_changed: "changed (EXIF)",
  file_modified: "file last modified",
  uploaded: "upload date",
};

const CAPTION_BADGES: Record<CaptionStatus, { label: string; variant: BadgeVariant }> = {
  none: { label: "No caption", variant: "muted" },
  pending: { label: "Not ingested", variant: "warning" },
  ingested: { label: "Ingested", variant: "success" },
};

export function PhotoCard({ photo }: { photo: Photo }) {
  const [draft, setDraft] = useState(photo.caption);
  const save = useSaveCaption();
  const changed = draft.trim() !== photo.caption;
  const badge = CAPTION_BADGES[photo.caption_status];

  const media = { id: photo.memory_id, kind: "image", url: photo.url, mime_type: photo.mime_type ?? "" };
  return (
    <figure className="flex flex-col overflow-hidden rounded-lg border bg-card">
      <MediaThumb media={media} alt={photo.caption || photo.filename} className="aspect-square rounded-none" />
      <figcaption className="flex flex-1 flex-col gap-2 p-2 text-xs">
        <div className="flex items-start justify-between gap-2">
          <span className="min-w-0 truncate font-medium" title={photo.filename}>
            {photo.filename}
          </span>
          <Badge variant={badge.variant} className="shrink-0">
            {badge.label}
          </Badge>
        </div>
        <span className="text-muted-foreground">
          {formatDateTime(photo.timestamp)} · {DATE_SOURCE_LABELS[photo.date_source] ?? photo.date_source}
        </span>
        <details className="text-muted-foreground">
          <summary className="cursor-pointer select-none">Metadata</summary>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
            <dt>Taken</dt>
            <dd>{formatDateTime(photo.taken_at)}</dd>
            <dt>Changed</dt>
            <dd>{formatDateTime(photo.changed_at)}</dd>
            <dt>File modified</dt>
            <dd>{formatDateTime(photo.file_modified_at)}</dd>
            <dt>Uploaded</dt>
            <dd>{formatDateTime(photo.uploaded_at)}</dd>
          </dl>
        </details>

        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Add a caption: who, where, what happened…"
          aria-label={`Caption for ${photo.filename}`}
          maxLength={2000}
          rows={2}
          className="memory-text text-xs"
        />
        <div className="flex items-center justify-end gap-2">
          {save.isError && (
            <span role="alert" className="mr-auto text-destructive">
              {save.error.message}
            </span>
          )}
          <Button
            size="sm"
            variant={changed ? "default" : "outline"}
            disabled={!changed || save.isPending}
            onClick={() => save.mutate({ memoryId: photo.memory_id, caption: draft.trim() })}
          >
            {save.isPending ? <Spinner /> : changed ? <Save /> : <Check />}
            {changed ? "Save caption" : "Saved"}
          </Button>
        </div>
      </figcaption>
    </figure>
  );
}
