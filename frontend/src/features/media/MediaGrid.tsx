// Media page results: photos as a square grid, audio/video as cards with players.
import { SourceBadge } from "@/components/SourceBadge";
import type { Evidence, MediaSourceType } from "@/types/api";
import { formatDateTime } from "@/lib/format";
import { MediaThumb } from "./MediaThumb";

export function MediaGrid({ results, kind }: { results: Evidence[]; kind: MediaSourceType }) {
  if (kind === "image") {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {results.map((result) => {
          const firstMedia = result.media[0];
          const caption = result.snippet || result.text || result.source_name;
          return (
            <figure key={result.memory_id} className="group overflow-hidden rounded-lg border bg-card">
              {firstMedia ? (
                <MediaThumb media={firstMedia} alt={caption} className="aspect-square rounded-none" />
              ) : (
                <div className="memory-text flex aspect-square items-center justify-center bg-muted p-3 text-center text-xs text-muted-foreground">
                  {result.snippet || "No preview"}
                </div>
              )}
              <figcaption className="flex flex-col gap-1 p-2 text-xs">
                <span className="memory-text line-clamp-2">{caption}</span>
                <span className="text-muted-foreground">{formatDateTime(result.timestamp)}</span>
              </figcaption>
            </figure>
          );
        })}
      </div>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {results.map((result) => (
        <div key={result.memory_id} className="flex flex-col gap-2 rounded-lg border bg-card p-3 text-sm">
          <div className="flex items-center gap-2">
            <SourceBadge type={result.source_type} />
            <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{result.source_name}</span>
            <span className="text-xs text-muted-foreground">{formatDateTime(result.timestamp)}</span>
          </div>
          {result.media.map((media) => (
            <MediaThumb key={media.id} media={media} controls className={kind === "video" ? "aspect-video" : undefined} />
          ))}
          {(result.snippet || result.text) && (
            <p className="memory-text line-clamp-4 text-muted-foreground" lang={result.language || undefined}>
              {result.snippet || result.text}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
