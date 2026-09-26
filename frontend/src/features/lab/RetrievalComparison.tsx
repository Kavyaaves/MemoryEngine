// AI Lab: run one query through every retriever (full-text, trigram, vector, hybrid) side by side
// to compare what each finds and how fast.
// Data flow: form submit → useRetrieverComparison (hooks/useSearch.ts) → 4 × GET /api/search?mode=…
import { useState, type FormEvent } from "react";
import { GitCompareArrows } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { RETRIEVAL_MODES, useRetrieverComparison } from "@/hooks/useSearch";
import { RetrieverColumn } from "./RetrieverColumn";

const TOP_K_OPTIONS = [5, 10, 20, 50];

export function RetrievalComparison() {
  const [input, setInput] = useState("");
  const [topK, setTopK] = useState(10);
  const [submitted, setSubmitted] = useState<{ q: string; k: number } | null>(null);
  const results = useRetrieverComparison(submitted);
  const anyFetching = results.some((result) => result.isFetching);

  // How many retrievers returned each memory — shows how much the retrievers overlap.
  const retrieverHits = new Map<string, number>();
  for (const result of results) {
    for (const evidence of result.data?.results ?? []) {
      retrieverHits.set(evidence.memory_id, (retrieverHits.get(evidence.memory_id) ?? 0) + 1);
    }
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const query = input.trim();
    if (!query) return;
    if (submitted && submitted.q === query && submitted.k === topK) {
      // Same query again: the cache key doesn't change, so ask for fresh results explicitly.
      results.forEach((result) => void result.refetch());
    } else {
      setSubmitted({ q: query, k: topK });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GitCompareArrows className="size-4" aria-hidden /> Retrieval comparison
        </CardTitle>
        <CardDescription>Run one query through each retriever side by side and compare hits and latency.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="e.g. naan unna miss panren / Goa trip plans"
            className="memory-text flex-1"
            aria-label="Comparison query"
          />
          <Select
            value={topK}
            onChange={(event) => setTopK(Number(event.target.value))}
            className="sm:w-24"
            aria-label="Top K"
          >
            {TOP_K_OPTIONS.map((option) => (
              <option key={option} value={option}>
                k={option}
              </option>
            ))}
          </Select>
          <Button type="submit" disabled={!input.trim() || anyFetching}>
            {anyFetching && <Spinner />} Compare
          </Button>
        </form>

        {submitted && (
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
            {RETRIEVAL_MODES.map((mode, index) => (
              <RetrieverColumn key={mode} mode={mode} result={results[index]} retrieverHits={retrieverHits} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
