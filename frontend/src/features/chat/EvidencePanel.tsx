// The Ask page's evidence column: the memories behind the selected answer.
// Clicking a citation in the answer scrolls to and flashes the matching card here.
import { useEffect, useRef } from "react";
import { FileSearch } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";
import type { Evidence } from "@/types/api";
import { EvidenceCard } from "./EvidenceCard";

interface EvidencePanelProps {
  evidence: Evidence[];
  /** 1-based citation to highlight, or null. */
  highlightedCitation: number | null;
  /** Changes on every citation click so the flash replays even for the same citation. */
  flashKey: number;
  loading: boolean;
}

export function EvidencePanel({ evidence, highlightedCitation, flashKey, loading }: EvidencePanelProps) {
  const cardsByCitation = useRef(new Map<number, HTMLDivElement>());

  useEffect(() => {
    if (highlightedCitation === null) return;
    cardsByCitation.current.get(highlightedCitation)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [highlightedCitation, flashKey]);

  if (evidence.length === 0) {
    return (
      <EmptyState
        icon={<FileSearch />}
        title={loading ? "Retrieving evidence…" : "No evidence yet"}
        description={
          loading
            ? "Searching your memories across text, time and people."
            : "Ask a question — the memories used to answer it appear here with their provenance."
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {evidence.map((item, index) => {
        const citation = index + 1;
        const highlighted = highlightedCitation === citation;
        return (
          <EvidenceCard
            // A new key remounts the highlighted card, which restarts its CSS flash animation.
            key={`${item.memory_id}-${index}-${highlighted ? flashKey : 0}`}
            ref={(element) => {
              if (element) cardsByCitation.current.set(citation, element);
              else cardsByCitation.current.delete(citation);
            }}
            evidence={item}
            citation={citation}
            highlighted={highlighted}
          />
        );
      })}
    </div>
  );
}
