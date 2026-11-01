// One Memory Page: a conversation (or your photos) on one day, shown as it was — original text,
// author, time and media. Click a memory to see the original with its context and connections.
// At the end of a "Visit memory" trip, the visited message is scrolled to and gently flashed.
import { useEffect, useRef } from "react";
import { Image as ImageIcon, MessagesSquare } from "lucide-react";
import { usePage } from "@/hooks/useUniverse";
import { useUniverseStore } from "@/stores/universeStore";
import { MediaThumb } from "@/features/media/MediaThumb";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/cn";

function timeOf(iso: string | null): string {
  return iso ? new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "";
}

export function PageView({ pageId }: { pageId: string }) {
  const page = usePage(pageId);
  const highlightMemoryId = useUniverseStore((state) => state.highlightMemoryId);
  const showMemory = useUniverseStore((state) => state.showMemory);
  const highlighted = useRef<HTMLLIElement>(null);

  useEffect(() => {
    highlighted.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [page.data, highlightMemoryId]);

  if (page.isPending) return <p className="text-sm text-slate-400">Turning to the page…</p>;
  if (page.isError) return <p className="text-sm text-rose-300">This page couldn't be loaded.</p>;
  const { page: info, memories, total } = page.data;

  return (
    <div>
      <header className="mb-3">
        <h3 className="text-base font-semibold text-white">{formatDate(info.day)}</h3>
        <p className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-400">
          {info.thread_name === "Photos & media" ? <ImageIcon className="size-3.5" /> : <MessagesSquare className="size-3.5" />}
          {info.thread_name} · {total} memories
        </p>
        {info.people.length > 0 && (
          <p className="mt-1 text-xs text-slate-500">with {info.people.map((person) => person.name).join(", ")}</p>
        )}
      </header>

      <ol className="flex flex-col gap-2">
        {memories.map((memory) => {
          const isTarget = memory.memory_id === highlightMemoryId;
          return (
            <li
              key={memory.memory_id}
              ref={isTarget ? highlighted : undefined}
              className={cn(
                "rounded-xl border border-transparent bg-white/[0.04] transition-colors hover:border-white/10 hover:bg-white/[0.07]",
                isTarget && "cite-flash border-amber-200/60 bg-amber-200/10",
              )}
            >
              <button
                type="button"
                onClick={() => showMemory(memory.memory_id)}
                title="See the original, its conversation and connections"
                className="w-full cursor-pointer px-3 py-2 text-left"
              >
                <div className="mb-0.5 flex items-center gap-2 text-[11px] text-slate-500">
                  <span className="font-medium text-indigo-200/90">{memory.author ?? memory.source_name}</span>
                  <span className="ml-auto">{timeOf(memory.timestamp)}</span>
                </div>
                <p className="memory-text text-sm text-slate-100" lang={memory.language || undefined}>{memory.text}</p>
              </button>
              {memory.media.length > 0 && (
                <div className="grid grid-cols-3 gap-1.5 px-3 pb-2">
                  {memory.media.slice(0, 6).map((media) => (
                    <MediaThumb key={media.id} media={media} className="aspect-square" />
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {total > memories.length && (
        <p className="mt-3 text-center text-xs text-slate-500">Showing the first {memories.length} of {total} memories.</p>
      )}
    </div>
  );
}
