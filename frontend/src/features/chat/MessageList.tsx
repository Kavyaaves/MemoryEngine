import { useEffect, useRef } from "react";
import { AssistantMessageCard } from "./AssistantMessageCard";
import type { ChatMessage } from "./chatStore";

interface MessageListProps {
  messages: ChatMessage[];
  /** The answer whose evidence is shown in the evidence column. */
  activeAnswerId: string | undefined;
  onSelectAnswer: (messageId: string) => void;
  onCite: (messageId: string, citation: number) => void;
}

/** The conversation: user questions on the right, assistant answers as cards. */
export function MessageList({ messages, activeAnswerId, onSelectAnswer, onCite }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const answerCount = messages.filter((message) => message.role === "assistant").length;
  const lastMessage = messages.at(-1);
  const lastContentLength = lastMessage?.content.length ?? 0;
  const lastStepCount = lastMessage?.role === "assistant" ? lastMessage.steps.length : 0;

  // Keep the newest content in view while an answer streams in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, lastContentLength, lastStepCount]);

  return (
    <div className="flex flex-col gap-4 pb-2">
      {messages.map((message) =>
        message.role === "user" ? (
          <div key={message.id} className="flex justify-end">
            <div className="memory-text max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-sm text-primary-foreground">
              {message.content}
            </div>
          </div>
        ) : (
          <AssistantMessageCard
            key={message.id}
            message={message}
            // With a single answer there is nothing to choose between, so no outline.
            selected={answerCount > 1 && message.id === activeAnswerId}
            onSelect={onSelectAnswer}
            onCite={onCite}
          />
        ),
      )}
      <div ref={bottomRef} />
    </div>
  );
}
