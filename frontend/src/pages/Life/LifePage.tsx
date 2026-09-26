// Life page: your memories through time (PLAN §28). Year → month → day.
// Left: the 3D spiral (three/TimelineScene, lazy-loaded) or the 2D list; right: overview, month or day details.
// Data: useTimelineMonths / useTimelineDays (hooks/useTimeline.ts) → GET /api/timeline
import { lazy, Suspense, useState } from "react";
import { Link } from "react-router";
import { Box, List, Orbit, Upload } from "lucide-react";
import { buttonVariants } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { EmptyState } from "@/components/EmptyState";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { DayPanel } from "@/features/timeline/DayPanel";
import { MonthPanel } from "@/features/timeline/MonthPanel";
import { SourceLegend } from "@/features/timeline/SourceLegend";
import { TimelineList } from "@/features/timeline/TimelineList";
import { TimelineOverview } from "@/features/timeline/TimelineOverview";
import { useTimelineDays, useTimelineMonths } from "@/hooks/useTimeline";
import { isWebGLAvailable } from "@/lib/webgl";

// lazy(): three.js is large, so its code is only downloaded when the 3D view is first shown.
const TimelineScene = lazy(() => import("@/three/TimelineScene"));

type View = "3d" | "list";

export default function LifePage() {
  const webglAvailable = isWebGLAvailable();
  const [view, setView] = useState<View>(webglAvailable ? "3d" : "list");
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const months = useTimelineMonths();
  const days = useTimelineDays(selectedMonth);
  const monthBuckets = months.data ?? [];
  const dayBuckets = days.data ?? [];

  const selectMonth = (month: string | null) => {
    setSelectedMonth(month);
    setSelectedDay(null);
  };

  const listView = (
    <TimelineList
      months={monthBuckets}
      days={dayBuckets}
      daysLoading={days.isFetching}
      selectedMonth={selectedMonth}
      selectedDay={selectedDay}
      onSelectMonth={selectMonth}
      onSelectDay={setSelectedDay}
    />
  );

  return (
    <div className="flex flex-col p-4 md:p-6 lg:h-screen">
      <PageHeader
        title="Life"
        description="Your memories through time — year, month, day. Drag to orbit, scroll to zoom, click to dive in."
        actions={
          <Tabs value={view} onValueChange={(value) => setView(value as View)}>
            <TabsList aria-label="View">
              <TabsTrigger value="3d" disabled={!webglAvailable} title={webglAvailable ? undefined : "WebGL unavailable"}>
                <Box /> 3D
              </TabsTrigger>
              <TabsTrigger value="list">
                <List /> List
              </TabsTrigger>
            </TabsList>
          </Tabs>
        }
      />

      {months.isPending ? (
        <LoadingState label="Loading your timeline…" />
      ) : months.isError ? (
        <ErrorState error={months.error} onRetry={() => void months.refetch()} />
      ) : monthBuckets.length === 0 ? (
        <EmptyState
          icon={<Orbit />}
          title="Your timeline is empty"
          description="Upload a chat export, journal or photos and your life will appear here."
          action={
            <Link to="/upload" className={buttonVariants({ size: "sm" })}>
              <Upload /> Upload memories
            </Link>
          }
        />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row">
          <Card className="relative h-[60vh] min-h-0 overflow-hidden lg:h-auto lg:flex-1">
            {view === "3d" && webglAvailable ? (
              // If the 3D scene crashes (e.g. the GPU driver fails), fall back to the list.
              <ErrorBoundary
                fallback={(error) => (
                  <div className="h-full overflow-y-auto p-4">
                    <p className="mb-4 rounded-md bg-warning/10 p-2 text-xs text-warning">
                      3D view failed ({error.message}); showing the list instead.
                    </p>
                    {listView}
                  </div>
                )}
              >
                <Suspense fallback={<LoadingState label="Starting 3D engine…" className="h-full" />}>
                  <TimelineScene
                    months={monthBuckets}
                    days={dayBuckets}
                    selectedMonth={selectedMonth}
                    selectedDay={selectedDay}
                    onSelectMonth={selectMonth}
                    onSelectDay={setSelectedDay}
                  />
                </Suspense>
                <SourceLegend months={monthBuckets} />
                {selectedMonth && days.isFetching && (
                  <div className="absolute right-3 top-3 rounded bg-black/50 px-2 py-1 text-xs text-white/80">
                    Loading days…
                  </div>
                )}
              </ErrorBoundary>
            ) : (
              <div className="h-full overflow-y-auto p-4">
                {!webglAvailable && (
                  <p className="mb-4 rounded-md bg-muted p-2 text-xs text-muted-foreground">
                    WebGL isn't available in this browser, so the 3D explorer is replaced by a list.
                  </p>
                )}
                {listView}
              </div>
            )}
          </Card>

          <Card className="flex max-h-[70vh] min-h-0 flex-col p-4 lg:max-h-none lg:w-96 lg:shrink-0">
            {selectedDay ? (
              <DayPanel date={selectedDay} onClose={() => setSelectedDay(null)} />
            ) : selectedMonth ? (
              <MonthPanel month={selectedMonth} onSelectDay={setSelectedDay} onClear={() => selectMonth(null)} />
            ) : (
              <TimelineOverview months={monthBuckets} />
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
