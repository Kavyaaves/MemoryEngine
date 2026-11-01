// Under an answer on the Ask page: the memory itself, not just text about it.
//   MEMORY FOUND · 18 June 2024 · in "Relationship" · [Visit memory]
// Shown for the first evidence item — for "first"/"last" questions that is the earliest/latest one.
import { Sparkles } from "lucide-react";
import type { Evidence } from "@/types/api";
import { VisitMemoryButton } from "./VisitMemoryButton";

export function MemoryFoundCard({ evidence }: { evidence: Evidence }) {
  const when = evidence.timestamp
    ? new Date(evidence.timestamp).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })
    : "Undated";
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
      <Sparkles className="size-4 shrink-0 text-amber-500" />
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-600 dark:text-amber-300">Memory found</p>
        <p className="text-sm font-medium">{when}</p>
        {evidence.book_title && <p className="truncate text-xs text-muted-foreground">in “{evidence.book_title}”</p>}
      </div>
      <VisitMemoryButton memoryId={evidence.memory_id} label="Visit memory" className="px-3 py-1" />
    </div>
  );
}
