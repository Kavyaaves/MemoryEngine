// Sentiment endpoints (docs/api-contract.md § Sentiment). Called from hooks/useSentiment.ts.
import type { MoodTimelineParams, MoodTimelineResponse, SentimentStatus } from "@/types/api";
import { apiFetch } from "./client";

export function getMoodTimeline(params: MoodTimelineParams, signal?: AbortSignal) {
  return apiFetch<MoodTimelineResponse>("/sentiment/timeline", {
    query: { granularity: params.granularity, start: params.start, end: params.end, person_id: params.person_id },
    signal,
  });
}

export function getSentimentStatus() {
  return apiFetch<SentimentStatus>("/sentiment/status");
}

/** Starts analysing the remaining memories in the background (responds right away). */
export function startSentimentAnalysis() {
  return apiFetch<SentimentStatus>("/sentiment/analyze", { method: "POST" });
}
