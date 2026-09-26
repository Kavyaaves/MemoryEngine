import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import type { Confidence } from "@/types/api";

const VARIANT_BY_CONFIDENCE: Record<Confidence, BadgeVariant> = {
  high: "success",
  medium: "warning",
  low: "destructive",
  none: "muted",
};

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  return (
    <Badge variant={VARIANT_BY_CONFIDENCE[confidence]} title="Answer confidence">
      confidence: {confidence}
    </Badge>
  );
}
