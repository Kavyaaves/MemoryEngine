// "Is X the same person as Y?" — asks the user to confirm identity merges the backend is unsure about
// (active learning). People page → useAliasSuggestions / useAliasFeedback → api/people.ts
import { useState } from "react";
import { Check, HelpCircle, Sparkles, X } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { useAliasFeedback, useAliasSuggestions } from "@/hooks/usePeople";
import type { AliasAnswer, AliasSuggestion } from "@/types/api";

const suggestionKey = (suggestion: AliasSuggestion) => `${suggestion.alias_id}:${suggestion.person_id}`;

export function AliasSuggestionCard() {
  const suggestions = useAliasSuggestions();
  const feedback = useAliasFeedback();
  // Hide answered questions immediately, without waiting for the suggestions to refetch.
  const [answeredKeys, setAnsweredKeys] = useState<Set<string>>(new Set());

  // This card is optional help, so it stays hidden while loading or when the request fails.
  if (suggestions.isPending || suggestions.isError) return null;

  const remaining = suggestions.data.filter((suggestion) => !answeredKeys.has(suggestionKey(suggestion)));
  const current = remaining[0];

  if (!current) {
    if (answeredKeys.size === 0) return null;
    return (
      <Card className="border-success/30 bg-success/5">
        <CardContent className="flex items-center gap-2 p-4 text-sm">
          <Check className="size-4 text-success" aria-hidden /> Thanks — all identity questions answered.
          <Button variant="link" size="sm" className="ml-auto" onClick={() => void suggestions.refetch()}>
            Check for more
          </Button>
        </CardContent>
      </Card>
    );
  }

  const answer = (reply: AliasAnswer) =>
    feedback.mutate(
      { alias_id: current.alias_id, person_id: current.person_id, answer: reply },
      { onSuccess: () => setAnsweredKeys((keys) => new Set(keys).add(suggestionKey(current))) },
    );

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <Sparkles className="hidden size-5 shrink-0 text-primary sm:block" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="memory-text text-sm">
            Is <span className="font-semibold">“{current.alias}”</span> the same person as{" "}
            <span className="font-semibold">{current.person_name}</span>?
          </p>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="muted">{Math.round(current.similarity * 100)}% similar</Badge>
            {remaining.length > 1 && <span>{remaining.length - 1} more to review</span>}
          </div>
          {feedback.isError && <p className="mt-1 text-xs text-destructive">{feedback.error.message}</p>}
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => answer("yes")} disabled={feedback.isPending}>
            <Check /> Yes
          </Button>
          <Button size="sm" variant="outline" onClick={() => answer("no")} disabled={feedback.isPending}>
            <X /> No
          </Button>
          <Button size="sm" variant="ghost" onClick={() => answer("unsure")} disabled={feedback.isPending}>
            <HelpCircle /> Not sure
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
