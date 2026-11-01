// One retrieved memory with its provenance (source, time, author, conversation, retriever, score).
// Used in the Ask page's evidence column and in the Life page's day view.
import { useState, type Ref } from "react";
import { ChevronDown, ChevronUp, Clock, MessagesSquare, User } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { SourceBadge } from "@/components/SourceBadge";
import { MediaThumb } from "@/features/media/MediaThumb";
import { SentimentBadge } from "@/features/sentiment/SentimentBadge";
import { VisitMemoryButton } from "@/features/universe/VisitMemoryButton";
import type { Evidence } from "@/types/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { RetrievalPaths } from "./RetrievalPaths";

const MAX_MEDIA_THUMBNAILS = 6;

interface EvidenceCardProps {
  evidence: Evidence;
  /** The citation number shown in the corner. */
  citation?: number;
  highlighted?: boolean;
  /** Hides score, retrieval paths and language (for the day view). */
  compact?: boolean;
  ref?: Ref<HTMLDivElement>;
}

export function EvidenceCard({ evidence, citation, highlighted = false, compact = false, ref }: EvidenceCardProps) {
  const [expanded, setExpanded] = useState(false);
  const canExpand = evidence.text !== "" && evidence.snippet !== "" && evidence.text !== evidence.snippet;
  const body = expanded ? evidence.text : evidence.snippet || evidence.text;

  return (
    <div
      ref={ref}
      className={cn(
        "scroll-mt-4 rounded-lg border bg-card p-3 text-sm transition-colors",
        highlighted && "cite-flash border-primary bg-primary/5",
      )}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {citation !== undefined && (
          <span className="flex size-5 shrink-0 items-center justify-center rounded bg-primary/15 text-[11px] font-semibold text-primary tabular-nums">
            {citation}
          </span>
        )}
        <SourceBadge type={evidence.source_type} />
        <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground" title={evidence.source_name}>
          {evidence.source_name}
        </span>
        {evidence.sentiment && <SentimentBadge sentiment={evidence.sentiment} />}
        {evidence.book_id && <VisitMemoryButton memoryId={evidence.memory_id} />}
        {!compact && (
          <span className="font-mono text-[11px] text-muted-foreground" title="Retrieval score">
            {Number.isFinite(evidence.score) ? evidence.score.toFixed(3) : "—"}
          </span>
        )}
      </div>

      <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {evidence.timestamp && (
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3" /> {formatDateTime(evidence.timestamp)}
          </span>
        )}
        {evidence.author && (
          <span className="inline-flex items-center gap-1">
            <User className="size-3" /> {evidence.author}
          </span>
        )}
        {evidence.conversation_title && (
          <span className="inline-flex min-w-0 items-center gap-1">
            <MessagesSquare className="size-3 shrink-0" />{" "}
            <span className="truncate">{evidence.conversation_title}</span>
          </span>
        )}
      </div>

      <p className="memory-text text-foreground/90" lang={evidence.language || undefined}>
        {body}
      </p>
      {canExpand && (
        <button
          type="button"
          aria-expanded={expanded}
          className="mt-1 inline-flex cursor-pointer items-center gap-0.5 text-xs text-primary hover:underline"
          onClick={() => setExpanded((isExpanded) => !isExpanded)}
        >
          {expanded ? "Show less" : "Show full text"}
          {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
        </button>
      )}

      {evidence.media.length > 0 && (
        <div className="mt-2 grid grid-cols-3 gap-2">
          {evidence.media.slice(0, MAX_MEDIA_THUMBNAILS).map((media) => (
            <MediaThumb key={media.id} media={media} className="aspect-square" />
          ))}
        </div>
      )}

      {!compact && (evidence.retrieval_paths.length > 0 || evidence.language || evidence.script) && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <RetrievalPaths paths={evidence.retrieval_paths} />
          {(evidence.language || evidence.script) && (
            <Badge variant="muted" className="font-mono text-[10px]">
              {[evidence.language, evidence.script].filter(Boolean).join(" · ")}
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}
