import { Sparkles } from "lucide-react";

const EXAMPLE_QUESTIONS = [
  "When did I first talk to Rahul?",
  "What did we plan for the Goa trip?",
  "அம்மா birthday ku enna gift pannom?",
  "Summarise my journal entries from last June",
];

/** Shown before the first question: a short intro plus example questions to click. */
export function ChatWelcome({ onAsk }: { onAsk: (question: string) => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/15 text-primary">
        <Sparkles className="size-6" />
      </div>
      <div>
        <p className="text-lg font-medium">What would you like to remember?</p>
        <p className="text-sm text-muted-foreground">Answers cite the exact messages, notes and photos they come from.</p>
      </div>
      <div className="grid w-full max-w-xl gap-2 sm:grid-cols-2">
        {EXAMPLE_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onAsk(question)}
            className="memory-text cursor-pointer rounded-lg border bg-card px-3 py-2 text-left text-sm transition-colors hover:border-primary/50 hover:bg-accent"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
