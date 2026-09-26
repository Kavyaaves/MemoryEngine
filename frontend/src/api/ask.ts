// POST /api/ask/stream — the agent answers a question, streaming its progress as server-sent events.
// Data flow: AskPage → useChatStore.send (features/chat/chatStore.ts) → askStream() → readServerSentEvents() (api/sse.ts)
// Events (docs/api-contract.md § Ask): step → evidence → token… → done, or error at any point.
import type { AskErrorEvent, AskRequest, AskResponse, AskStepEvent, AskTokenEvent, Evidence } from "@/types/api";
import { authHeaders, buildUrl, errorFromResponse, sendRequest } from "./client";
import { readServerSentEvents } from "./sse";

export interface AskStreamHandlers {
  onStep: (step: AskStepEvent) => void;
  onEvidence: (evidence: Evidence[]) => void;
  onToken: (text: string) => void;
  onDone: (response: AskResponse) => void;
  onError: (message: string) => void;
}

/**
 * Resolves when the answer is complete (done/error event or end of stream).
 * Rejects with an AbortError when `signal` is aborted, or with an ApiError if the request itself fails
 * (for example 503 while the database is down).
 */
export async function askStream(request: AskRequest, handlers: AskStreamHandlers, signal: AbortSignal): Promise<void> {
  const response = await sendRequest(buildUrl("/ask/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...authHeaders() },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) throw errorFromResponse(response.status, await response.text());
  if (!response.body) throw new Error("This browser cannot read streamed responses.");

  for await (const message of readServerSentEvents(response.body)) {
    let payload: unknown;
    try {
      payload = JSON.parse(message.data);
    } catch {
      continue; // ignore a malformed event rather than failing the whole answer
    }

    switch (message.event) {
      case "step":
        handlers.onStep(payload as AskStepEvent);
        break;
      case "evidence":
        handlers.onEvidence(payload as Evidence[]);
        break;
      case "token":
        handlers.onToken((payload as AskTokenEvent).text);
        break;
      case "done":
        handlers.onDone(payload as AskResponse);
        return; // leaving the loop also stops reading the stream
      case "error":
        handlers.onError((payload as AskErrorEvent).message);
        return;
    }
  }
}
