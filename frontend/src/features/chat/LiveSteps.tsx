import { Check, Loader2 } from "lucide-react";
import type { AskStepEvent } from "@/types/api";
import { cn } from "@/lib/cn";
import { formatJsonPreview } from "@/lib/format";

/** The agent's progress (analyze → retrieve → verify → answer) while an answer is being prepared. */
export function LiveSteps({ steps, active }: { steps: AskStepEvent[]; active: boolean }) {
  if (steps.length === 0 && !active) return null;
  return (
    <ol className="mb-3 flex flex-col gap-1 text-xs">
      {steps.map((step, index) => {
        const running = active && index === steps.length - 1;
        const detail = formatJsonPreview(step.detail);
        return (
          <li key={`${step.name}-${index}`} className="flex items-start gap-2 text-muted-foreground">
            {running ? (
              <Loader2 className="mt-0.5 size-3 shrink-0 animate-spin text-primary" aria-hidden />
            ) : (
              <Check className="mt-0.5 size-3 shrink-0 text-success" aria-hidden />
            )}
            <span className={cn("font-medium capitalize", running && "text-foreground")}>{step.name}</span>
            {detail && (
              <span className="min-w-0 truncate" title={detail}>
                {detail}
              </span>
            )}
          </li>
        );
      })}
      {active && steps.length === 0 && (
        <li className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-3 animate-spin text-primary" aria-hidden /> Thinking…
        </li>
      )}
    </ol>
  );
}
