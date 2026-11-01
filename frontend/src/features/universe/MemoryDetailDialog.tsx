// "Open the original": one memory exactly as it was imported — text, author, time, source,
// conversation and media — the messages around it, and its connections, each with "Visit".
import { Clock, MessagesSquare, Navigation, User } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { SourceBadge } from "@/components/SourceBadge";
import { MediaThumb } from "@/features/media/MediaThumb";
import { useMemoryDetail } from "@/hooks/useUniverse";
import { useUniverseStore } from "@/stores/universeStore";
import type { ConnectionKind, MemoryConnection } from "@/types/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/cn";

const KIND_ORDER: ConnectionKind[] = ["same_event", "same_person", "previous_mention", "later_reference", "similar",
  "related_photo"];
const KIND_TITLE: Record<ConnectionKind, string> = {
  same_event: "Same event",
  same_person: "Same person",
  previous_mention: "Earlier",
  later_reference: "Later",
  similar: "Similar conversation",
  related_photo: "Photos",
};

export function MemoryDetailDialog() {
  const memoryId = useUniverseStore((state) => state.detailMemoryId);
  const showMemory = useUniverseStore((state) => state.showMemory);
  const visit = useUniverseStore((state) => state.visit);
  const detail = useMemoryDetail(memoryId);
  const data = detail.data;

  const grouped = KIND_ORDER.map((kind) => ({
    kind,
    items: (data?.connections ?? []).filter((connection) => connection.kind === kind),
  })).filter((group) => group.items.length > 0);

  return (
    <Dialog
      open={memoryId !== null}
      onOpenChange={(open) => !open && showMemory(null)}
      title="Original memory"
      description={data?.location ? `In “${data.location.book_title}”` : undefined}
      className="max-h-[88vh] max-w-2xl overflow-y-auto"
    >
      {detail.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
      {detail.isError && <p className="text-sm text-destructive">This memory couldn't be loaded.</p>}
      {data && (
        <div className="flex flex-col gap-5">
          <section className="rounded-lg border bg-card p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <SourceBadge type={data.memory.source_type} />
              <span className="truncate">{data.memory.source_name}</span>
            </div>
            <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {data.memory.timestamp && (
                <span className="inline-flex items-center gap-1"><Clock className="size-3" /> {formatDateTime(data.memory.timestamp)}</span>
              )}
              {data.memory.author && <span className="inline-flex items-center gap-1"><User className="size-3" /> {data.memory.author}</span>}
              {data.memory.conversation_title && (
                <span className="inline-flex items-center gap-1"><MessagesSquare className="size-3" /> {data.memory.conversation_title}</span>
              )}
            </div>
            <p className="memory-text text-sm" lang={data.memory.language || undefined}>{data.memory.text}</p>
            {data.memory.media.length > 0 && (
              <div className="mt-2 grid grid-cols-2 gap-2">
                {data.memory.media.map((media) => <MediaThumb key={media.id} media={media} controls className="aspect-video" />)}
              </div>
            )}
            <p className="mt-2 font-mono text-[10px] text-muted-foreground">
              {data.memory.language} · {data.memory.script} · stored exactly as imported
            </p>
          </section>

          {data.context.length > 1 && (
            <section>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">The conversation around it</h3>
              <ol className="flex flex-col gap-1 border-l pl-3">
                {data.context.map((message) => (
                  <li key={message.memory_id}
                      className={cn("text-sm", message.memory_id === data.memory.memory_id ? "font-medium text-foreground" : "text-muted-foreground")}>
                    <span className="mr-2 text-[11px] tabular-nums">{message.timestamp ? formatDateTime(message.timestamp) : ""}</span>
                    <span className="mr-1 text-primary/80">{message.author}:</span>
                    <span className="memory-text">{message.snippet || message.text}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Connected memories</h3>
            {grouped.length === 0 && <p className="text-sm text-muted-foreground">No connections found for this memory yet.</p>}
            <div className="flex flex-col gap-3">
              {grouped.map((group) => (
                <div key={group.kind}>
                  <h4 className="mb-1 text-xs text-muted-foreground">{KIND_TITLE[group.kind]}</h4>
                  <ul className="flex flex-col gap-1.5">
                    {group.items.map((connection) => (
                      <ConnectionRow key={connection.memory.memory_id} connection={connection}
                                     onVisit={() => visit(connection.memory.memory_id)}
                                     onOpen={() => showMemory(connection.memory.memory_id)} />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </Dialog>
  );
}

function ConnectionRow({ connection, onVisit, onOpen }: { connection: MemoryConnection; onVisit: () => void; onOpen: () => void }) {
  const { memory, location, label, similarity } = connection;
  return (
    <li className="flex items-start gap-2 rounded-md border p-2 text-sm">
      <button type="button" onClick={onOpen} className="min-w-0 flex-1 cursor-pointer text-left">
        <div className="text-[11px] text-muted-foreground">
          {label}
          {similarity !== null && ` · ${Math.round(similarity * 100)}% similar`}
          {memory.timestamp && ` · ${formatDate(memory.timestamp)}`}
          {memory.author && ` · ${memory.author}`}
        </div>
        <p className="memory-text line-clamp-2">{memory.snippet || memory.text}</p>
      </button>
      <button
        type="button"
        onClick={onVisit}
        disabled={!location}
        title={location ? `Visit it in “${location.book_title}”` : "Not placed in the universe yet"}
        className="inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-md bg-primary/10 px-2 py-1 text-xs text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Navigation className="size-3" /> Visit
      </button>
    </li>
  );
}
