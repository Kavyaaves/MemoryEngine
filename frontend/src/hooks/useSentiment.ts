// Sentiment hooks → api/sentiment.ts.
//   Life page overview + person detail → useMoodTimeline (mood per month)
//   AI Lab → useSentimentStatus + useStartSentimentAnalysis ("Analyse now", then poll until done)
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getMoodTimeline, getSentimentStatus, startSentimentAnalysis } from "@/api/sentiment";
import { invalidateMemoryData, queryKeys } from "@/api/queryKeys";
import type { MoodTimelineParams, SentimentStatus } from "@/types/api";

const STATUS_POLL_INTERVAL_MS = 3000;

export function useMoodTimeline(params: MoodTimelineParams) {
  return useQuery({
    queryKey: queryKeys.sentiment.timeline(params),
    queryFn: ({ signal }) => getMoodTimeline(params, signal),
  });
}

export function useSentimentStatus() {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: queryKeys.sentiment.status,
    queryFn: async () => {
      const wasRunning = queryClient.getQueryData<SentimentStatus>(queryKeys.sentiment.status)?.running;
      const status = await getSentimentStatus();
      // A run just finished: memories got new sentiments, so moods and evidence cards change.
      if (wasRunning && !status.running) invalidateMemoryData(queryClient);
      return status;
    },
    // Poll only while a run is going on.
    refetchInterval: (query) => (query.state.data?.running ? STATUS_POLL_INTERVAL_MS : false),
  });
}

export function useStartSentimentAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: startSentimentAnalysis,
    // Show "running" right away; that also starts the polling in useSentimentStatus.
    onSuccess: (status) => queryClient.setQueryData(queryKeys.sentiment.status, status),
  });
}
