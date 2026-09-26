// Life page side panel for one selected day: every memory from that day, in time order.
// Life page → useTimelineDay → api/timeline.ts → GET /api/timeline/day/{date}
import { CalendarDays, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { EvidenceCard } from "@/features/chat/EvidenceCard";
import { useTimelineDay } from "@/hooks/useTimeline";
import { formatPeriod } from "@/lib/periods";

export function DayPanel({ date, onClose }: { date: string; onClose: () => void }) {
  const day = useTimelineDay(date);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-3 flex items-center gap-2">
        <CalendarDays className="size-4 text-primary" aria-hidden />
        <h2 className="flex-1 font-semibold">{formatPeriod(date)}</h2>
        {day.data && <span className="text-xs text-muted-foreground">{day.data.length} memories</span>}
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose} aria-label="Close day">
          <X />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {day.isPending ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2, 3].map((index) => (
              <Skeleton key={index} className="h-24" />
            ))}
          </div>
        ) : day.isError ? (
          <ErrorState error={day.error} onRetry={() => void day.refetch()} />
        ) : day.data.length === 0 ? (
          <EmptyState title="Nothing recorded" description="No memories on this day." />
        ) : (
          <div className="flex flex-col gap-2">
            {day.data.map((memory) => (
              <EvidenceCard key={memory.memory_id} evidence={memory} compact />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
