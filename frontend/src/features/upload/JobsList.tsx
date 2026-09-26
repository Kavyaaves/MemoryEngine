// "Ingestion jobs" card: one row per uploaded file being processed by the backend.
// Data flow: JobsList → useJobs (polls GET /api/uploads/jobs every 2 s while any job is running)
//            Retry button → useRetryJob → POST /api/uploads/jobs/{id}/retry
import { ListChecks, RotateCw } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { isJobRunning, useJobs, useRetryJob } from "@/hooks/useUploads";
import { JobRow } from "./JobRow";

export function JobsList() {
  const jobs = useJobs();
  const retry = useRetryJob();
  const runningCount = jobs.data?.filter(isJobRunning).length ?? 0;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          Ingestion jobs
          {runningCount > 0 && (
            <Badge variant="info">
              <Spinner className="size-3" /> {runningCount} active
            </Badge>
          )}
        </CardTitle>
        <Button variant="ghost" size="sm" onClick={() => void jobs.refetch()} disabled={jobs.isFetching}>
          <RotateCw className={jobs.isFetching ? "animate-spin" : ""} /> Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {jobs.isPending ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2].map((index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </div>
        ) : jobs.isError ? (
          <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} />
        ) : jobs.data.length === 0 ? (
          <EmptyState icon={<ListChecks />} title="No uploads yet" description="Jobs appear here as files are processed." />
        ) : (
          <ul className="flex flex-col divide-y">
            {jobs.data.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                retrying={retry.isPending && retry.variables === job.id}
                onRetry={() => retry.mutate(job.id)}
              />
            ))}
          </ul>
        )}
        {retry.isError && <p className="mt-2 text-sm text-destructive">Retry failed: {retry.error.message}</p>}
      </CardContent>
    </Card>
  );
}
