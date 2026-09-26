import { useState, type FormEvent, type KeyboardEvent } from "react";
import { SendHorizontal, Square } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";

interface ChatComposerProps {
  isStreaming: boolean;
  onAsk: (question: string) => void;
  onStop: () => void;
}

/** The question box. Enter sends, Shift+Enter adds a new line; while streaming, Send becomes Stop. */
export function ChatComposer({ isStreaming, onAsk, onStop }: ChatComposerProps) {
  const [question, setQuestion] = useState("");

  const submit = () => {
    const trimmed = question.trim();
    if (!trimmed || isStreaming) return;
    setQuestion("");
    onAsk(trimmed);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // isComposing: Enter also confirms a word in an input-method editor (e.g. typing Tamil) — don't send then.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form onSubmit={onSubmit} className="mt-3 flex items-end gap-2">
      <Textarea
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask anything — English, Tamil, Tanglish, Malayalam…"
        rows={2}
        className="memory-text max-h-40 min-h-[44px] resize-none"
        aria-label="Question"
      />
      {isStreaming ? (
        <Button variant="secondary" size="icon" onClick={onStop} aria-label="Stop">
          <Square />
        </Button>
      ) : (
        <Button type="submit" size="icon" disabled={!question.trim()} aria-label="Send">
          <SendHorizontal />
        </Button>
      )}
    </form>
  );
}
