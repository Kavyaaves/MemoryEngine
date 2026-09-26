// Chat state for the Ask page: the conversation and the answer currently streaming in.
// It lives in a Zustand store rather than component state so the conversation survives
// navigating to other pages and back.
// Data flow: AskPage → useChatStore.send() → askStream() (api/ask.ts) → POST /api/ask/stream
//            → each server event patches the assistant message → components re-render.
import { create } from "zustand";
import { askStream } from "@/api/ask";
import { useAuthStore } from "@/stores/authStore";
import type { AskResponse, AskStepEvent, ChatTurn, Evidence } from "@/types/api";

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  /** The answer text: grows token by token while streaming. */
  content: string;
  status: "streaming" | "done" | "error" | "aborted";
  steps: AskStepEvent[];
  evidence: Evidence[];
  /** The final response (with trace and confidence), once the `done` event arrives. */
  response: AskResponse | null;
  error: string | null;
  /** performance.now() timestamps, for the round-trip time shown in the trace. */
  startedAt: number;
  finishedAt: number | null;
}

export type ChatMessage = UserMessage | AssistantMessage;

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  send: (question: string) => Promise<void>;
  stop: () => void;
  reset: () => void;
}

/** How many previous turns are sent along so follow-up questions have context. */
const HISTORY_TURNS = 10;

// The request currently streaming, so stop()/reset() can abort it. Kept outside the store state
// because it is not something the UI renders.
let activeRequest: AbortController | null = null;

let lastMessageId = 0;
const nextMessageId = () => String(++lastMessageId);

function conversationHistory(messages: ChatMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  for (const message of messages) {
    if (message.role === "user") turns.push({ role: "user", content: message.content });
    else if (message.status === "done" && message.content) turns.push({ role: "assistant", content: message.content });
  }
  return turns.slice(-HISTORY_TURNS);
}

export const useChatStore = create<ChatState>()((set, get) => {
  /** Update one assistant message; a no-op if it no longer exists (e.g. after "New chat"). */
  const updateAssistant = (id: string, update: (message: AssistantMessage) => Partial<AssistantMessage>) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id && message.role === "assistant" ? { ...message, ...update(message) } : message,
      ),
    }));

  return {
    messages: [],
    isStreaming: false,

    stop: () => activeRequest?.abort(),

    reset: () => {
      activeRequest?.abort();
      activeRequest = null;
      set({ messages: [], isStreaming: false });
    },

    send: async (question) => {
      if (get().isStreaming) return;
      const history = conversationHistory(get().messages);
      const request = new AbortController();
      activeRequest = request;

      const assistantId = nextMessageId();
      const assistantMessage: AssistantMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        status: "streaming",
        steps: [],
        evidence: [],
        response: null,
        error: null,
        startedAt: performance.now(),
        finishedAt: null,
      };
      set((state) => ({
        isStreaming: true,
        messages: [...state.messages, { id: nextMessageId(), role: "user", content: question }, assistantMessage],
      }));

      try {
        await askStream(
          { question, conversation: history.length > 0 ? history : undefined },
          {
            onStep: (step) => updateAssistant(assistantId, (message) => ({ steps: [...message.steps, step] })),
            onEvidence: (evidence) => updateAssistant(assistantId, () => ({ evidence })),
            onToken: (text) => updateAssistant(assistantId, (message) => ({ content: message.content + text })),
            onDone: (response) =>
              updateAssistant(assistantId, (message) => ({
                response,
                // The final answer is authoritative; the streamed text is only a fallback.
                content: response.answer || message.content,
                evidence: response.evidence.length > 0 ? response.evidence : message.evidence,
                status: "done",
                finishedAt: performance.now(),
              })),
            onError: (errorMessage) =>
              updateAssistant(assistantId, () => ({
                status: "error",
                error: errorMessage,
                finishedAt: performance.now(),
              })),
          },
          request.signal,
        );
        // The stream ended without a done/error event.
        updateAssistant(assistantId, (message) => {
          if (message.status !== "streaming") return {};
          return message.content
            ? { status: "done", finishedAt: performance.now() }
            : { status: "error", error: "The answer stream ended without an answer.", finishedAt: performance.now() };
        });
      } catch (error) {
        const aborted = error instanceof DOMException && error.name === "AbortError";
        updateAssistant(assistantId, () => ({
          status: aborted ? "aborted" : "error",
          error: aborted ? null : error instanceof Error ? error.message : String(error),
          finishedAt: performance.now(),
        }));
      } finally {
        // reset() may already have started a fresh conversation (with a new request) while this one was
        // being aborted — only clear the streaming state if it still belongs to this request.
        if (activeRequest === request) {
          activeRequest = null;
          set({ isStreaming: false });
        }
      }
    },
  };
});

// One user's conversation must never be visible to whoever signs in next.
useAuthStore.subscribe((state, previousState) => {
  const sessionEndedOrChanged = previousState.token !== null && state.token !== previousState.token;
  if (sessionEndedOrChanged) useChatStore.getState().reset();
});
