// One assistant answer in the chat: live agent steps, the answer text with citation buttons,
// error/stopped notices, confidence, evidence count and the trace panel.
import { memo } from "react";
import { Card } from "@/components/ui/Card";
import { badgeVariants } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import { MemoryFoundCard } from "@/features/universe/MemoryFoundCard";
import { AnswerText } from "./AnswerText";
import type { AssistantMessage } from "./chatStore";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { LiveSteps } from "./LiveSteps";
import { TracePanel } from "./TracePanel";

interface AssistantMessageCardProps {
  message: AssistantMessage;
  /** Outlined when its evidence is the one shown in the evidence column. */
  selected: boolean;
  onSelect: (messageId: string) => void;
  onCite: (messageId: string, citation: number) => void;
}

// memo: while an answer streams, only that message object changes on each token,
// so the earlier answers can skip re-rendering (AskPage passes stable callbacks for this).
export const AssistantMessageCard = memo(function AssistantMessageCard({
  message,
  selected,
  onSelect,
  onCite,
}: AssistantMessageCardProps) {
  const streaming = message.status === "streaming";
  const evidenceCount = message.evidence.length;

  return (
    <Card
      onClick={() => onSelect(message.id)}
      aria-busy={streaming}
      className={cn("max-w-full p-4 text-sm transition-colors", selected && "border-primary/40")}
    >
      <LiveSteps steps={message.steps} active={streaming && !message.content} />
      {message.content && (
        <AnswerText
          text={message.content}
          evidenceCount={evidenceCount}
          streaming={streaming}
          onCite={(citation) => onCite(message.id, citation)}
        />
      )}
      {message.status === "error" && (
        <p role="alert" className="mt-2 rounded-md bg-destructive/10 px-3 py-2 text-destructive">
          {message.error ?? "Something went wrong."}
        </p>
      )}
      {message.status === "aborted" && <p className="mt-2 text-xs text-muted-foreground">Stopped.</p>}
      {message.response && message.response.confidence !== "none" && message.evidence[0] && (
        <MemoryFoundCard evidence={message.evidence[0]} />
      )}

      {(message.response || evidenceCount > 0) && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {message.response && <ConfidenceBadge confidence={message.response.confidence} />}
          {evidenceCount > 0 && (
            // A real button so keyboard users can also pick which answer's evidence is shown.
            <button
              type="button"
              onClick={() => onSelect(message.id)}
              className={cn(badgeVariants({ variant: "muted" }), "cursor-pointer hover:text-foreground")}
            >
              {evidenceCount} evidence item{evidenceCount === 1 ? "" : "s"}
            </button>
          )}
        </div>
      )}
      {message.response && (
        <TracePanel
          response={message.response}
          clientMs={message.finishedAt !== null ? message.finishedAt - message.startedAt : null}
        />
      )}
    </Card>
  );
});
