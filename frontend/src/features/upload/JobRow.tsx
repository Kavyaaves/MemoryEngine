import { RotateCw } from "lucide-react";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Progress } from "@/components/ui/Progress";
import { Spinner } from "@/components/ui/Spinner";
import { SourceBadge } from "@/components/SourceBadge";
import { isJobRunning } from "@/hooks/useUploads";
import type { Job, JobStatus } from "@/types/api";
import { formatNumber, formatRelative } from "@/lib/format";

const BADGE_VARIANT_BY_STATUS: Record<JobStatus, BadgeVariant> = {
  queued: "muted",
  processing: "info",
  completed: "success",
  failed: "destructive",
  duplicate: "warning",
};

interface JobRowProps {
  job: Job;
  retrying: boolean;
  onRetry: () => void;
}

/** One ingestion job: file name, status, progress, counts and any error. */
export function JobRow({ job, retrying, onRetry }: JobRowProps) {
  const running = isJobRunning(job);
  const showProgress = (running || job.progress > 0) && job.status !== "completed";

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-medium" title={job.filename}>
          {job.filename}
        </span>
        <SourceBadge type={job.source_type} />
        <Badge variant={BADGE_VARIANT_BY_STATUS[job.status]}>
          {job.status === "processing" && <Spinner className="size-3" />}
          {job.status}
        </Badge>
        {job.status === "failed" && (
          <Button variant="outline" size="sm" onClick={onRetry} disabled={retrying}>
            <RotateCw /> Retry
          </Button>
        )}
      </div>
      {showProgress && (
        <Progress
          value={job.progress}
          aria-label={`Processing ${job.filename}`}
          indicatorClassName={job.status === "failed" ? "bg-destructive" : undefined}
        />
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {job.stats.total !== undefined && <span>total {formatNumber(job.stats.total)}</span>}
        {job.stats.new !== undefined && <span>new {formatNumber(job.stats.new)}</span>}
        {job.stats.skipped !== undefined && <span>skipped {formatNumber(job.stats.skipped)}</span>}
        {job.stats.embedded !== undefined && <span>embedded {formatNumber(job.stats.embedded)}</span>}
        {job.stats.universe && (
          <span title="Memory Universe: books updated · new books · new connections">
            {job.stats.universe.books_updated} books updated · {job.stats.universe.books_created} new ·{" "}
            {job.stats.universe.connections} connections
          </span>
        )}
        {running && <span>{Math.round(job.progress * 100)}%</span>}
        <span className="ml-auto">updated {formatRelative(job.updated_at)}</span>
      </div>
      {job.error && <p className="rounded bg-destructive/10 px-2 py-1 text-xs text-destructive">{job.error}</p>}
    </li>
  );
}
