import type { RetrievalPath } from "@/types/api";
import { cn } from "@/lib/cn";

// Which retriever(s) found a memory: full-text, trigram, vector, graph or temporal — or "derived":
// the model trained in the fine-tuning phase (backend/app/finetuning/).
const PATH_STYLE: Record<string, string> = {
  fts: "bg-sky-500/15 text-sky-600 dark:text-sky-300",
  trgm: "bg-teal-500/15 text-teal-600 dark:text-teal-300",
  vector: "bg-violet-500/15 text-violet-600 dark:text-violet-300",
  graph: "bg-orange-500/15 text-orange-600 dark:text-orange-300",
  temporal: "bg-lime-500/15 text-lime-700 dark:text-lime-300",
  derived: "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300",
  // Graph RAG over Memory Books (backend retrieval/books.py)
  book: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
};

export function RetrievalPaths({ paths }: { paths: RetrievalPath[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {paths.map((path) => (
        <span
          key={path}
          className={cn(
            "rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide",
            PATH_STYLE[path] ?? "bg-muted text-muted-foreground",
          )}
        >
          {path}
        </span>
      ))}
    </div>
  );
}
