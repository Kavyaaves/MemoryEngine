import type { UseQueryResult } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ErrorState";
import { SourceBadge } from "@/components/SourceBadge";
import { RetrievalPaths } from "@/features/chat/RetrievalPaths";
import { RETRIEVAL_MODES, type TimedSearchResponse } from "@/hooks/useSearch";
import type { SearchMode } from "@/types/api";
import { formatDateTime } from "@/lib/format";

const MODE_LABEL: Record<SearchMode, string> = {
  fts: "Full-text (FTS)",
  trgm: "Trigram (fuzzy)",
  vector: "Vector (semantic)",
  hybrid: "Hybrid (RRF)",
};

interface RetrieverColumnProps {
  mode: SearchMode;
  result: UseQueryResult<TimedSearchResponse> | undefined;
  /** memory_id → how many retrievers returned it. */
  retrieverHits: Map<string, number>;
}

/** One retriever's ranked results in the comparison, with its latency. */
export function RetrieverColumn({ mode, result, retrieverHits }: RetrieverColumnProps) {
  const response = result?.data;

  return (
    <div className="flex min-w-0 flex-col rounded-lg border">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <span className="text-sm font-semibold">{MODE_LABEL[mode]}</span>
        {response && (
          <Badge variant="muted" className="ml-auto font-mono" title="Round-trip time measured in the browser">
            {Math.round(response.clientMs)} ms
          </Badge>
        )}
      </div>
      {response && Object.keys(response.timings_ms).length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 border-b px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
          {Object.entries(response.timings_ms).map(([stage, milliseconds]) => (
            <span key={stage}>
              {stage}: {milliseconds.toFixed(1)}ms
            </span>
          ))}
        </div>
      )}

      <div className="max-h-[32rem] overflow-y-auto p-2">
        {result?.isError ? (
          <ErrorState error={result.error} title={`${mode} failed`} className="py-4" />
        ) : !response ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2].map((index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </div>
        ) : response.results.length === 0 ? (
          <p className="py-6 text-center text-xs text-muted-foreground">No results</p>
        ) : (
          <ol className="flex flex-col gap-2">
            {response.results.map((evidence, rank) => {
              const hits = retrieverHits.get(evidence.memory_id) ?? 1;
              return (
                <li key={evidence.memory_id} className="rounded-md bg-muted/40 p-2 text-xs">
                  <div className="mb-1 flex items-center gap-1.5">
                    <span className="font-mono text-muted-foreground">#{rank + 1}</span>
                    <SourceBadge type={evidence.source_type} />
                    <span className="ml-auto font-mono">{evidence.score.toFixed(3)}</span>
                  </div>
                  <p className="memory-text line-clamp-3">{evidence.snippet || evidence.text}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
                    <span>{formatDateTime(evidence.timestamp)}</span>
                    {evidence.author && <span>· {evidence.author}</span>}
                    <Badge
                      variant={hits === RETRIEVAL_MODES.length ? "success" : hits > 1 ? "info" : "muted"}
                      className="ml-auto text-[10px]"
                      title="Number of retrievers that returned this memory"
                    >
                      {hits}/{RETRIEVAL_MODES.length}
                    </Badge>
                  </div>
                  {evidence.retrieval_paths.length > 0 && (
                    <div className="mt-1">
                      <RetrievalPaths paths={evidence.retrieval_paths} />
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
