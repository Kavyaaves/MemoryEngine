// Upload / ingestion hooks used by the Upload page (features/upload/*) → api/uploads.ts.
// Lifecycle: upload files → the backend creates "queued" jobs → useJobs polls until every job is finished
// → the memories changed, so everything derived from them is refreshed (invalidateMemoryData).
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteSource, getJobs, getSources, retryJob, uploadFiles, type UploadInput } from "@/api/uploads";
import { invalidateMemoryData, queryKeys } from "@/api/queryKeys";
import type { Job, Source } from "@/types/api";

const JOB_POLL_INTERVAL_MS = 2000;

export function isJobRunning(job: Job): boolean {
  return job.status === "queued" || job.status === "processing";
}

/**
 * The job list. Polls every 2 s while a job runs. `idlePollMs` also checks now and then while nothing
 * runs — the Memories page uses it to notice imports started in another tab or on another device.
 */
export function useJobs(idlePollMs: number | false = false) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: queryKeys.jobs,
    queryFn: async () => {
      const previousJobs = queryClient.getQueryData<Job[]>(queryKeys.jobs) ?? [];
      const jobs = await getJobs();

      // A job that was running last time and isn't any more has written new memories.
      const previouslyRunning = new Set(previousJobs.filter(isJobRunning).map((job) => job.id));
      if (jobs.some((job) => previouslyRunning.has(job.id) && !isJobRunning(job))) {
        invalidateMemoryData(queryClient);
      }
      return jobs;
    },
    // Poll quickly while something is queued/processing; otherwise only if the caller asked for an idle poll.
    refetchInterval: (query) => (query.state.data?.some(isJobRunning) ? JOB_POLL_INTERVAL_MS : idlePollMs),
  });
}

export function useRetryJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: retryJob,
    onSuccess: (updatedJob) => {
      // Show the job as queued right away; that also restarts polling in useJobs.
      queryClient.setQueryData<Job[]>(queryKeys.jobs, (jobs) =>
        jobs?.map((job) => (job.id === updatedJob.id ? updatedJob : job)),
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
    },
  });
}

/** Upload mutation plus the 0..1 progress of the file transfer. */
export function useUploadFiles() {
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState(0);
  const mutation = useMutation({
    mutationFn: (input: UploadInput) => {
      setProgress(0);
      return uploadFiles(input, setProgress);
    },
    onSuccess: (response) => {
      // Show the new jobs immediately (this starts polling), then refetch the real list.
      queryClient.setQueryData<Job[]>(queryKeys.jobs, (jobs = []) => [...response.jobs, ...jobs]);
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources });
    },
  });
  return { ...mutation, progress };
}

export function useSources() {
  return useQuery({ queryKey: queryKeys.sources, queryFn: getSources });
}

export function useDeleteSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteSource,
    onSuccess: (_response, deletedId) => {
      queryClient.setQueryData<Source[]>(queryKeys.sources, (sources) =>
        sources?.filter((source) => source.id !== deletedId),
      );
      // The source's memories are gone too: timeline, people and search results all change.
      invalidateMemoryData(queryClient);
    },
  });
}
