// While an import runs: a small "Processing memories…" chip. When it finishes (while you are here),
// a checklist of what it did — detected, new, duplicates skipped, books updated / created, connections.
import { useEffect, useRef, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { isJobRunning, useJobs } from "@/hooks/useUploads";
import type { Job } from "@/types/api";

export function IngestionStatus() {
  const jobs = useJobs();
  const running = (jobs.data ?? []).filter(isJobRunning);
  const [finished, setFinished] = useState<Job[]>([]);
  const wasRunning = useRef(new Set<string>());

  useEffect(() => {
    const list = jobs.data ?? [];
    const done = list.filter((job) => wasRunning.current.has(job.id) && job.status === "completed");
    if (done.length) setFinished((previous) => [...done, ...previous].slice(0, 3));
    wasRunning.current = new Set(list.filter(isJobRunning).map((job) => job.id));
  }, [jobs.data]);

  if (running.length === 0 && finished.length === 0) return null;
  const progress = running.length ? running.reduce((sum, job) => sum + job.progress, 0) / running.length : 1;

  return (
    <div className="pointer-events-auto flex w-72 flex-col gap-2">
      {running.length > 0 && (
        <div className="flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/70 px-3 py-1.5 text-xs text-slate-200 backdrop-blur-xl">
          <Loader2 className="size-3.5 animate-spin text-indigo-200" />
          <span className="min-w-0 flex-1 truncate">
            Processing memories… {running.length > 1 ? `${running.length} files` : running[0].filename}
          </span>
          <span className="tabular-nums text-slate-400">{Math.round(progress * 100)}%</span>
        </div>
      )}
      {finished.map((job) => (
        <FinishedCard key={job.id} job={job} onClose={() => setFinished((list) => list.filter((j) => j.id !== job.id))} />
      ))}
    </div>
  );
}

function FinishedCard({ job, onClose }: { job: Job; onClose: () => void }) {
  const stats = job.stats;
  const universe = stats.universe;
  const lines = [
    stats.total !== undefined && `${stats.total.toLocaleString()} memories detected`,
    stats.new !== undefined && `${stats.new.toLocaleString()} new memories`,
    stats.skipped !== undefined && `${stats.skipped.toLocaleString()} duplicates skipped`,
    universe && `${universe.books_updated} existing ${universe.books_updated === 1 ? "event" : "events"} updated`,
    universe && `${universe.books_created} new ${universe.books_created === 1 ? "event" : "events"} created`,
    universe && `${universe.connections} new ${universe.connections === 1 ? "relationship" : "relationships"} discovered`,
  ].filter(Boolean) as string[];

  return (
    <div className="rounded-xl border border-white/10 bg-slate-950/75 px-3 py-2.5 text-slate-100 shadow-xl backdrop-blur-xl">
      <div className="mb-1 flex items-center gap-2">
        <p className="min-w-0 flex-1 truncate text-sm font-medium" title={job.filename}>{job.filename}</p>
        <button type="button" onClick={onClose} aria-label="Dismiss" className="cursor-pointer text-slate-500 hover:text-white">
          <X className="size-3.5" />
        </button>
      </div>
      <ul className="flex flex-col gap-0.5 text-xs text-slate-300">
        {lines.map((line) => (
          <li key={line} className="flex items-center gap-1.5"><Check className="size-3 text-emerald-300" /> {line}</li>
        ))}
      </ul>
    </div>
  );
}
