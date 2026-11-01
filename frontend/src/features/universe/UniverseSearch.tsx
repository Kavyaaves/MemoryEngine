// Search second: a small "ask your past" pill above the universe. It uses the same agent as the Ask
// page (Graph RAG included) and answers with the memory itself — "Memory found · 18 June 2024 ·
// Visit memory" — so you can fly there and read the original.
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, Navigation, Search, X } from "lucide-react";
import { askOnce } from "@/api/universe";
import { useUniverseStore } from "@/stores/universeStore";
import type { Evidence } from "@/types/api";

const MORE_RESULTS = 4;

function longDate(iso: string | null): string {
  if (!iso) return "Undated";
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

export function UniverseSearch() {
  const [question, setQuestion] = useState("");
  const visit = useUniverseStore((state) => state.visit);
  const ask = useMutation({ mutationFn: askOnce });
  const result = ask.data;
  const top = result?.evidence[0];

  const goTo = (evidence: Evidence) => {
    visit(evidence.memory_id);
    ask.reset();
  };

  return (
    <div className="pointer-events-auto w-full max-w-lg">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (question.trim()) ask.mutate(question.trim());
        }}
        className="flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/60 px-4 py-2 text-sm text-slate-100 shadow-lg backdrop-blur-xl focus-within:border-indigo-300/50"
      >
        {ask.isPending ? <Loader2 className="size-4 animate-spin text-indigo-200" /> : <Search className="size-4 text-slate-400" />}
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask your past… e.g. when did I first say I love you?"
          aria-label="Ask your memories"
          className="min-w-0 flex-1 bg-transparent placeholder:text-slate-500 focus:outline-none"
        />
        {(result || ask.isError) && (
          <button type="button" onClick={() => ask.reset()} aria-label="Clear" className="cursor-pointer text-slate-400 hover:text-white">
            <X className="size-4" />
          </button>
        )}
      </form>

      {ask.isError && (
        <p className="mt-2 rounded-xl bg-rose-950/70 px-4 py-2 text-xs text-rose-200 backdrop-blur">{ask.error.message}</p>
      )}

      {result && (
        <div className="mt-2 max-h-[60vh] overflow-y-auto rounded-2xl border border-white/10 bg-slate-950/80 p-4 text-slate-100 shadow-2xl backdrop-blur-xl">
          {top ? (
            <>
              <p className="text-[11px] uppercase tracking-[0.25em] text-amber-200/90">Memory found</p>
              <p className="mt-1 text-xl font-light">{longDate(top.timestamp)}</p>
              <p className="memory-text mt-2 line-clamp-3 text-sm text-slate-300">“{top.snippet || top.text}”</p>
              <p className="mt-1 text-xs text-slate-500">{top.author} · {top.source_name}</p>
              <VisitButton evidence={top} onVisit={goTo} primary />
              {result.answer && <p className="mt-4 border-t border-white/10 pt-3 text-sm leading-relaxed text-slate-300">{result.answer}</p>}
              {result.evidence.length > 1 && (
                <ul className="mt-3 flex flex-col gap-1.5">
                  {result.evidence.slice(1, 1 + MORE_RESULTS).map((evidence) => (
                    <li key={evidence.memory_id} className="flex items-center gap-2 text-xs">
                      <span className="w-24 shrink-0 text-slate-500">{longDate(evidence.timestamp)}</span>
                      <span className="min-w-0 flex-1 truncate text-slate-300">{evidence.snippet || evidence.text}</span>
                      <VisitButton evidence={evidence} onVisit={goTo} />
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="text-sm text-slate-300">{result.answer || "No memory matched that question."}</p>
          )}
        </div>
      )}
    </div>
  );
}

function VisitButton({ evidence, onVisit, primary = false }: { evidence: Evidence; onVisit: (e: Evidence) => void; primary?: boolean }) {
  const placed = Boolean(evidence.book_id);
  return (
    <button
      type="button"
      onClick={() => onVisit(evidence)}
      title={placed ? `In “${evidence.book_title}”` : "Opens the original (not placed in the universe yet)"}
      className={
        primary
          ? "mt-3 inline-flex cursor-pointer items-center gap-2 rounded-full bg-amber-200/90 px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-950 hover:bg-amber-100"
          : "inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/80 hover:bg-white/20"
      }
    >
      <Navigation className={primary ? "size-3.5" : "size-3"} /> {primary ? "Visit memory" : "Visit"}
    </button>
  );
}
