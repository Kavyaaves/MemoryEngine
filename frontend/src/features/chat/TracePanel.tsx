// Collapsible "how was this answered" panel under a finished answer: per-step latency,
// the provider/model used, whether a fallback ("degraded") path ran, whether the fine-tuning phase's
// derived model helped (its base and derived model), and how the question was analysed.
import { useState } from "react";
import { AlertTriangle, ChevronRight, Cpu, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import type { AskAnalysis, AskResponse } from "@/types/api";
import { cn } from "@/lib/cn";
import { formatDateTime, formatJsonPreview } from "@/lib/format";

interface TracePanelProps {
  response: AskResponse;
  /** Round-trip time measured in the browser, or null if unknown. */
  clientMs: number | null;
}

export function TracePanel({ response, clientMs }: TracePanelProps) {
  const [open, setOpen] = useState(false);
  const { trace, analysis } = response;
  const totalMs = trace.steps.reduce((sum, step) => sum + (step.latency_ms || 0), 0);
  const slowestMs = Math.max(1, ...trace.steps.map((step) => step.latency_ms || 0));
  const finetune = trace.finetune ?? null;

  return (
    <div className="mt-3 rounded-lg border bg-muted/30 text-xs">
      <button
        type="button"
        onClick={() => setOpen((isOpen) => !isOpen)}
        aria-expanded={open}
        className="flex w-full cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-left"
      >
        <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} aria-hidden />
        <span className="font-medium">Trace</span>
        <span className="text-muted-foreground">
          {trace.steps.length} steps · {Math.round(totalMs)} ms
          {clientMs !== null && ` (round-trip ${Math.round(clientMs)} ms)`}
        </span>
        {(trace.provider || trace.model) && (
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <Cpu className="size-3" aria-hidden /> {[trace.provider, trace.model].filter(Boolean).join(" / ")}
          </span>
        )}
        {(finetune || trace.degraded) && (
          <span className="ml-auto flex items-center gap-1.5">
            {finetune && (
              <Badge variant="info" title={finetune.derived_model}>
                <Sparkles /> derived model
              </Badge>
            )}
            {trace.degraded && (
              <Badge variant="warning">
                <AlertTriangle /> degraded
              </Badge>
            )}
          </span>
        )}
      </button>

      {open && (
        <div className="flex flex-col gap-3 border-t px-3 py-3">
          {finetune && (
            <div className="flex items-start gap-2 rounded bg-primary/10 p-2 text-primary">
              <Sparkles className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <div className="flex min-w-0 flex-col gap-1">
                <span>A model trained in this app&apos;s fine-tuning phase helped with this answer.</span>
                <dl className="grid grid-cols-[7rem_1fr] gap-x-2 gap-y-0.5">
                  <dt className="opacity-80">Fine-tuning base</dt>
                  <dd className="break-all font-mono">{finetune.base_model}</dd>
                  <dt className="opacity-80">Derived model</dt>
                  <dd className="break-all font-mono">{finetune.derived_model}</dd>
                </dl>
              </div>
            </div>
          )}
          {trace.degraded && (
            <p className="flex items-start gap-2 rounded bg-warning/10 p-2 text-warning">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              Degraded mode: a provider was unavailable or quota-limited, so a fallback path (e.g. retrieval-only
              or a secondary model) produced this answer.
            </p>
          )}
          <ul className="flex flex-col gap-1.5">
            {trace.steps.map((step, index) => {
              const detail = formatJsonPreview(step.detail);
              return (
                <li key={`${step.name}-${index}`} className="grid grid-cols-[7rem_1fr_4rem] items-center gap-2">
                  <span className="truncate font-medium capitalize" title={step.name}>
                    {step.name}
                  </span>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted" title={detail || undefined}>
                    <div
                      className="h-full rounded-full bg-primary/70"
                      style={{ width: `${((step.latency_ms || 0) / slowestMs) * 100}%` }}
                    />
                  </div>
                  <span className="text-right font-mono tabular-nums text-muted-foreground">
                    {Math.round(step.latency_ms)} ms
                  </span>
                  {detail && <span className="col-span-3 -mt-1 break-all text-muted-foreground">{detail}</span>}
                </li>
              );
            })}
          </ul>
          <AnalysisDetails analysis={analysis} />
        </div>
      )}
    </div>
  );
}

/** How the agent understood the question (intent, people, time range, …). */
function AnalysisDetails({ analysis }: { analysis: AskAnalysis }) {
  return (
    <dl className="grid grid-cols-[7rem_1fr] gap-x-2 gap-y-1">
      <dt className="text-muted-foreground">Intent</dt>
      <dd>{analysis.intent || "—"}</dd>
      {analysis.people.length > 0 && (
        <>
          <dt className="text-muted-foreground">People</dt>
          <dd>{analysis.people.join(", ")}</dd>
        </>
      )}
      {(analysis.time_start || analysis.time_end) && (
        <>
          <dt className="text-muted-foreground">Time range</dt>
          <dd>
            {formatDateTime(analysis.time_start)} → {formatDateTime(analysis.time_end)}
          </dd>
        </>
      )}
      {analysis.temporal_order && (
        <>
          <dt className="text-muted-foreground">Order</dt>
          <dd>{analysis.temporal_order}</dd>
        </>
      )}
      {analysis.modality.length > 0 && (
        <>
          <dt className="text-muted-foreground">Modality</dt>
          <dd>{analysis.modality.join(", ")}</dd>
        </>
      )}
      {analysis.rewritten_queries.length > 0 && (
        <>
          <dt className="text-muted-foreground">Queries</dt>
          <dd>
            <ul className="list-inside list-disc">
              {analysis.rewritten_queries.map((query) => (
                <li key={query} className="memory-text">
                  {query}
                </li>
              ))}
            </ul>
          </dd>
        </>
      )}
    </dl>
  );
}
