import { sourceMeta } from "@/lib/sources";

interface SceneTooltipProps {
  title: string;
  count: number;
  sources: Record<string, number>;
  people: string[];
}

/** HTML tooltip drawn over a hovered month column or day sphere (placed in 3D by drei's <Html>). */
export function SceneTooltip({ title, count, sources, people }: SceneTooltipProps) {
  const topSources = Object.entries(sources)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);

  return (
    <div className="pointer-events-none w-max max-w-56 -translate-y-full rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs text-popover-foreground shadow-lg backdrop-blur">
      <div className="font-semibold">{title}</div>
      <div className="text-muted-foreground">{count.toLocaleString()} memories</div>
      {topSources.length > 0 && (
        <div className="mt-1 flex flex-col gap-0.5">
          {topSources.map(([type, sourceCount]) => (
            <span key={type} className="flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: sourceMeta(type).color }} />
              {sourceMeta(type).label} · {sourceCount}
            </span>
          ))}
        </div>
      )}
      {people.length > 0 && <div className="memory-text mt-1 text-muted-foreground">{people.slice(0, 4).join(", ")}</div>}
    </div>
  );
}
