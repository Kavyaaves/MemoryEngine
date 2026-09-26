// Ask page: chat with your memories. Left: the conversation; right: the evidence behind the selected answer.
// All chat state lives in features/chat/chatStore.ts; this page only tracks which answer/citation is selected.
import { useCallback, useState } from "react";
import { Eraser, MessageSquareText } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { ChatWelcome } from "@/features/chat/ChatWelcome";
import { EvidencePanel } from "@/features/chat/EvidencePanel";
import { MessageList } from "@/features/chat/MessageList";
import { useChatStore, type AssistantMessage, type ChatMessage } from "@/features/chat/chatStore";

interface Selection {
  /** null = follow the newest answer. */
  answerId: string | null;
  citation: number | null;
  /** Bumped on every citation click so the evidence card flashes again. */
  flashKey: number;
}
const FOLLOW_NEWEST: Selection = { answerId: null, citation: null, flashKey: 0 };

function isAssistantMessage(message: ChatMessage): message is AssistantMessage {
  return message.role === "assistant";
}

export default function AskPage() {
  // One selector per value: the page re-renders only when these particular values change.
  const messages = useChatStore((state) => state.messages);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const send = useChatStore((state) => state.send);
  const stop = useChatStore((state) => state.stop);
  const reset = useChatStore((state) => state.reset);
  const [selection, setSelection] = useState<Selection>(FOLLOW_NEWEST);

  const answers = messages.filter(isAssistantMessage);
  const activeAnswer = answers.find((answer) => answer.id === selection.answerId) ?? answers.at(-1);

  const ask = (question: string) => {
    setSelection(FOLLOW_NEWEST);
    void send(question);
  };

  const startNewChat = () => {
    reset();
    setSelection(FOLLOW_NEWEST);
  };

  // useCallback keeps these functions the same between renders, so the memoized answer cards
  // don't re-render on every streamed token.
  const selectAnswer = useCallback((answerId: string) => {
    setSelection((current) =>
      current.answerId === answerId ? current : { answerId, citation: null, flashKey: current.flashKey },
    );
  }, []);
  const showCitation = useCallback((answerId: string, citation: number) => {
    setSelection((current) => ({ answerId, citation, flashKey: current.flashKey + 1 }));
  }, []);

  return (
    <div className="flex h-[calc(100dvh-5.5rem)] flex-col gap-4 p-4 md:h-screen md:p-6 lg:flex-row">
      <section className="flex min-h-0 flex-1 flex-col lg:min-w-0">
        <div className="mb-3 flex items-center justify-between">
          <h1 className="text-xl font-semibold tracking-tight">Ask your memories</h1>
          {messages.length > 0 && (
            <Button variant="ghost" size="sm" onClick={startNewChat}>
              <Eraser /> New chat
            </Button>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          {messages.length === 0 ? (
            <ChatWelcome onAsk={ask} />
          ) : (
            <MessageList
              messages={messages}
              activeAnswerId={activeAnswer?.id}
              onSelectAnswer={selectAnswer}
              onCite={showCitation}
            />
          )}
        </div>

        <ChatComposer isStreaming={isStreaming} onAsk={ask} onStop={stop} />
      </section>

      <aside className="flex max-h-[45vh] min-h-0 flex-col lg:max-h-none lg:w-[26rem] lg:shrink-0">
        <div className="mb-3 flex items-center gap-2">
          <MessageSquareText className="size-4 text-muted-foreground" aria-hidden />
          <h2 className="font-semibold">Evidence</h2>
          {activeAnswer && activeAnswer.evidence.length > 0 && (
            <Badge variant="muted">{activeAnswer.evidence.length}</Badge>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          <EvidencePanel
            evidence={activeAnswer?.evidence ?? []}
            highlightedCitation={selection.citation}
            flashKey={selection.flashKey}
            loading={activeAnswer?.status === "streaming"}
          />
        </div>
      </aside>
    </div>
  );
}
