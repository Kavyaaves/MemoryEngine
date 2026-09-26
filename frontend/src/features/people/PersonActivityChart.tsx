// Bar chart (plain SVG) of how many memories involve a person in each period.
import { useState } from "react";
import type { PersonActivity } from "@/types/api";
import { formatPeriod } from "@/lib/periods";

const WIDTH = 600;
const HEIGHT = 120;
const AXIS_SPACE = 18;

export function PersonActivityChart({ activity }: { activity: PersonActivity[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const sorted = [...activity].sort((a, b) => a.period.localeCompare(b.period));
  const first = sorted[0];
  const last = sorted.at(-1);

  if (!first || !last) {
    return <p className="py-6 text-center text-sm text-muted-foreground">No activity recorded.</p>;
  }

  const maxCount = Math.max(1, ...sorted.map((point) => point.count));
  const barSlot = WIDTH / sorted.length;
  const barGap = Math.min(2, barSlot * 0.2);
  const hovered = hoveredIndex !== null ? sorted[hoveredIndex] : undefined;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-32 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Activity from ${formatPeriod(first.period)} to ${formatPeriod(last.period)}`}
      >
        {sorted.map((point, index) => {
          const barHeight = Math.max(1.5, (point.count / maxCount) * (HEIGHT - AXIS_SPACE - 4));
          return (
            <rect
              key={point.period}
              x={index * barSlot + barGap / 2}
              y={HEIGHT - AXIS_SPACE - barHeight}
              width={Math.max(0.5, barSlot - barGap)}
              height={barHeight}
              rx={Math.min(2, barSlot / 4)}
              className={hoveredIndex === index ? "fill-primary" : "fill-primary/55"}
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <title>
                {formatPeriod(point.period)}: {point.count}
              </title>
            </rect>
          );
        })}
        <line x1={0} x2={WIDTH} y1={HEIGHT - AXIS_SPACE} y2={HEIGHT - AXIS_SPACE} className="stroke-border" strokeWidth={1} />
      </svg>
      <div className="flex justify-between text-[11px] text-muted-foreground">
        <span>{formatPeriod(first.period)}</span>
        {hovered && (
          <span className="font-medium text-foreground">
            {formatPeriod(hovered.period)} · {hovered.count}
          </span>
        )}
        <span>{formatPeriod(last.period)}</span>
      </div>
    </div>
  );
}
