// A small "positive / negative / neutral" tag for one memory (shown on evidence cards).
import { Frown, Meh, Smile, type LucideIcon } from "lucide-react";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import type { Sentiment, SentimentLabel } from "@/types/api";

export const SENTIMENT_STYLES: Record<SentimentLabel, { label: string; icon: LucideIcon; variant: BadgeVariant }> = {
  positive: { label: "Positive", icon: Smile, variant: "success" },
  negative: { label: "Negative", icon: Frown, variant: "destructive" },
  neutral: { label: "Neutral", icon: Meh, variant: "muted" },
};

export function SentimentBadge({ sentiment }: { sentiment: Sentiment }) {
  const style = SENTIMENT_STYLES[sentiment.label];
  const Icon = style.icon;
  return (
    <Badge variant={style.variant} title={`Sentiment: ${style.label} (model confidence ${Math.round(sentiment.score * 100)}%)`}>
      <Icon /> {style.label}
    </Badge>
  );
}
