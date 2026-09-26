// Renders an answer, turning citations like "[1]", "[2, 3]" or "[2-4]" into buttons that
// highlight the matching evidence card. Citation numbers are 1-based indexes into the evidence list.
import { Fragment, type ReactNode } from "react";
import { cn } from "@/lib/cn";

const CITATION_PATTERN = /\[(\d+(?:\s*[,–-]\s*\d+)*)\]/g;
/** Guards against expanding a nonsense range like "[1-9999]". */
const MAX_RANGE_LENGTH = 20;

/** "1, 3" → [1, 3];  "2-4" → [2, 3, 4] */
function citationNumbers(group: string): number[] {
  const numbers: number[] = [];
  for (const part of group.split(",")) {
    const [from, to] = part.split(/[–-]/).map((text) => Number(text.trim()));
    if (from === undefined || Number.isNaN(from)) continue;
    if (to !== undefined && !Number.isNaN(to) && to >= from && to - from < MAX_RANGE_LENGTH) {
      for (let n = from; n <= to; n++) numbers.push(n);
    } else {
      numbers.push(from);
    }
  }
  return numbers;
}

/** The only formatting supported is **bold**; everything else is shown as plain text (never as HTML). */
function renderBold(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={`${keyPrefix}-${index}`}>{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={`${keyPrefix}-${index}`}>{part}</Fragment>
    ),
  );
}

interface AnswerTextProps {
  text: string;
  evidenceCount: number;
  onCite: (citation: number) => void;
  /** Shows a blinking caret after the text. */
  streaming: boolean;
}

export function AnswerText({ text, evidenceCount, onCite, streaming }: AnswerTextProps) {
  const nodes: ReactNode[] = [];
  let textStart = 0;
  let citationIndex = 0;

  for (const match of text.matchAll(CITATION_PATTERN)) {
    const matchStart = match.index;
    if (matchStart > textStart) nodes.push(...renderBold(text.slice(textStart, matchStart), `text-${citationIndex}`));
    nodes.push(
      <span key={`citation-${citationIndex}`} className="whitespace-nowrap">
        {citationNumbers(match[1] ?? "").map((citation) => {
          const available = citation >= 1 && citation <= evidenceCount;
          return (
            <button
              key={citation}
              type="button"
              disabled={!available}
              onClick={() => onCite(citation)}
              aria-label={available ? `Show evidence ${citation}` : `Evidence ${citation} not available`}
              title={available ? `Show evidence ${citation}` : `Evidence ${citation} not available`}
              className={cn(
                "mx-0.5 inline-flex h-5 min-w-5 -translate-y-px items-center justify-center rounded px-1 align-middle text-[11px] font-semibold tabular-nums transition-colors",
                available
                  ? "cursor-pointer bg-primary/15 text-primary hover:bg-primary hover:text-primary-foreground"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {citation}
            </button>
          );
        })}
      </span>,
    );
    textStart = matchStart + match[0].length;
    citationIndex++;
  }
  if (textStart < text.length) nodes.push(...renderBold(text.slice(textStart), `text-${citationIndex}`));

  return <div className={cn("memory-text", streaming && "stream-caret")}>{nodes}</div>;
}
