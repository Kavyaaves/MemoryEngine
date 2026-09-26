// Mood over time (plain SVG): one bar per period, above the line when mostly positive, below when mostly negative.
// Bar height = mood, from −1 (every analysed memory negative) to +1 (every one positive).
// Data: useMoodTimeline (hooks/useSentiment.ts) → GET /api/sentiment/timeline
import { useState } from "react";
import { useMoodTimeline } from "@/hooks/useSentiment";
import { formatPeriod } from "@/lib/periods";
import type { MoodBucket } from "@/types/api";

const WIDTH = 600;
const HEIGHT = 120;
const MIDDLE = HEIGHT / 2;

export function MoodChart({ personId }: { personId?: string }) {
  const moods = useMoodTimeline({ granularity: "month", person_id: personId });
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (moods.isPending) return <div className="h-32 animate-pulse rounded-md bg-muted" />;
  if (moods.isError) return <p className="text-xs text-destructive">Could not load the mood: {moods.error.message}</p>;
  const buckets = moods.data.buckets;
  const first = buckets[0];
  const last = buckets.at(-1);
  if (!first || !last) {
    return (
      <p className="py-4 text-center text-xs text-muted-foreground">
        No sentiment yet. It is added after each upload, or run it from the AI Lab.
      </p>
    );
  }

  const barSlot = WIDTH / buckets.length;
  const barGap = Math.min(2, barSlot * 0.2);
  const hovered = hoveredIndex !== null ? buckets[hoveredIndex] : undefined;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-32 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Mood from ${formatPeriod(first.period)} to ${formatPeriod(last.period)}`}
      >
        {buckets.map((bucket, index) => {
          const barHeight = Math.max(1, Math.abs(bucket.mood) * (MIDDLE - 4));
          const isHappy = bucket.mood >= 0;
          return (
            <rect
              key={bucket.period}
              x={index * barSlot + barGap / 2}
              y={isHappy ? MIDDLE - barHeight : MIDDLE}
              width={Math.max(0.5, barSlot - barGap)}
              height={barHeight}
              className={
                isHappy
                  ? hoveredIndex === index ? "fill-success" : "fill-success/60"
                  : hoveredIndex === index ? "fill-destructive" : "fill-destructive/60"
              }
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <title>{describe(bucket)}</title>
            </rect>
          );
        })}
        <line x1={0} x2={WIDTH} y1={MIDDLE} y2={MIDDLE} className="stroke-border" strokeWidth={1} />
      </svg>
      <div className="flex justify-between gap-2 text-[11px] text-muted-foreground">
        <span>{formatPeriod(first.period)}</span>
        {hovered && <span className="text-center font-medium text-foreground">{describe(hovered)}</span>}
        <span>{formatPeriod(last.period)}</span>
      </div>
    </div>
  );
}

function describe(bucket: MoodBucket): string {
  return `${formatPeriod(bucket.period)} · ${bucket.positive} positive, ${bucket.negative} negative, ${bucket.neutral} neutral`;
}
