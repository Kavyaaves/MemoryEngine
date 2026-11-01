// Memories page: the Memory Universe — "I can enter my own past and explore it."
//
//   3D scene (universe/UniverseScene, lazy-loaded)      the time river, years, books, the open book
//   overlays (features/universe/*)                      breadcrumb, search pill, reader, toasts, time strip
//
// Data: useUniverse (the snapshot) → books with fixed positions. While an import or a build runs,
// the change feed is polled; each change refreshes the snapshot and shows a quiet notification.
// Books that appear or grow are marked "fresh" so the scene can animate just them.
// Deep link: /memories?memory=<id> flies to that memory ("Visit memory" on the Ask page).
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, Orbit, Sparkles, Upload } from "lucide-react";
import { buttonVariants, Button } from "@/components/ui/Button";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { queryKeys } from "@/api/queryKeys";
import { BookReader } from "@/features/universe/BookReader";
import { DiscoveryToasts } from "@/features/universe/DiscoveryToasts";
import { IngestionStatus } from "@/features/universe/IngestionStatus";
import { MemoryDetailDialog } from "@/features/universe/MemoryDetailDialog";
import { TimeScrubber } from "@/features/universe/TimeScrubber";
import { UniverseBreadcrumb } from "@/features/universe/UniverseBreadcrumb";
import { UniverseSearch } from "@/features/universe/UniverseSearch";
import { isJobRunning, useJobs } from "@/hooks/useUploads";
import { useBook, useBuildUniverse, useMemoryDetail, usePage, useUniverse, useUniverseChangeFeed } from "@/hooks/useUniverse";
import { useUniverseStore } from "@/stores/universeStore";
import type { Book, Universe, UniverseChange } from "@/types/api";
import { isWebGLAvailable } from "@/lib/webgl";
import { formatDate } from "@/lib/format";
import { bookWaypoint, readerPlacement, visitWaypoints, yearWaypoint } from "@/universe/universeMath";

// lazy(): three.js is large, so its code is only downloaded when this page is opened.
const UniverseScene = lazy(() => import("@/universe/UniverseScene"));

const BUILD_WATCH_MS = 15 * 60 * 1000; // keep watching a background build for at most this long
const JOB_IDLE_POLL_MS = 15_000; // notice imports started elsewhere (another tab, the worker) within 15 s

/** A short sentence from an "update" change's totals. */
function describeUpdate(detail: UniverseChange["detail"]): string {
  const parts: string[] = [];
  const placed = Number(detail.memories_placed ?? 0);
  const created = Number(detail.books_created ?? 0);
  const updated = Number(detail.books_updated ?? 0);
  if (placed) parts.push(`${placed.toLocaleString()} memories`);
  if (created) parts.push(`${created} new ${created === 1 ? "book" : "books"}`);
  if (updated) parts.push(`${updated} ${updated === 1 ? "book" : "books"} grew`);
  return parts.join(" · ");
}

export default function MemoriesPage() {
  const webgl = isWebGLAvailable();
  const queryClient = useQueryClient();
  const universe = useUniverse();
  const jobs = useJobs(JOB_IDLE_POLL_MS);
  const build = useBuildUniverse();
  const [buildStartedAt, setBuildStartedAt] = useState<number | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

  const openBookId = useUniverseStore((state) => state.openBookId);
  const openPageId = useUniverseStore((state) => state.openPageId);
  const visitMemoryId = useUniverseStore((state) => state.visitMemoryId);
  const cameraX = useUniverseStore((state) => state.cameraX);
  const store = useUniverseStore.getState;

  const bookDetail = useBook(openBookId);
  const pageDetail = usePage(openPageId);
  const visitTarget = useMemoryDetail(visitMemoryId);
  const data = universe.data;

  // ---- navigation -----------------------------------------------------------------------
  const selectBook = useCallback((book: Book) => {
    store().openBook(book.id);
    store().fly([bookWaypoint(book, readerPlacement())]);
  }, [store]);

  const openBookById = useCallback((bookId: string) => {
    const book = universe.data?.books.find((candidate) => candidate.id === bookId);
    if (book) selectBook(book);
  }, [universe.data, selectBook]);

  const selectYear = useCallback((year: string) => {
    if (data) store().fly([yearWaypoint(year, data.layout)]);
  }, [data, store]);

  // Deep link (?memory=…) → start a visit, then tidy the URL.
  useEffect(() => {
    const memoryId = searchParams.get("memory");
    if (!memoryId) return;
    store().visit(memoryId);
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams, store]);

  // A visit: once we know where the memory lives, fly Universe → year → month → book, then open the page.
  useEffect(() => {
    if (!visitMemoryId || !data || !visitTarget.data) return;
    const { location, memory } = visitTarget.data;
    store().finishVisit();
    if (!location) {
      // Not placed yet (undated, or the universe hasn't caught up): show the original instead.
      store().pushToast({ title: "Not in the universe yet", body: "Showing the original memory." });
      store().showMemory(memory.memory_id);
      return;
    }
    const waypoints = visitWaypoints(location, data.layout, readerPlacement());
    waypoints[waypoints.length - 1].onArrive = () => {
      store().openBook(location.book_id);
      store().openPage(location.page_id, location.memory_id);
    };
    store().closeBook();
    store().fly(waypoints);
  }, [visitMemoryId, visitTarget.data, data, store]);

  useEffect(() => {
    if (visitMemoryId && visitTarget.isError) {
      store().finishVisit();
      store().pushToast({ title: "That memory couldn't be found" });
    }
  }, [visitMemoryId, visitTarget.isError, store]);

  // ---- live updates -----------------------------------------------------------------------
  // Mark books that appeared or grew since the last snapshot, so only they animate.
  const previousCounts = useRef<Map<string, number> | null>(null);
  useEffect(() => {
    if (!data) return;
    const counts = new Map(data.books.map((book) => [book.id, book.memory_count]));
    const previous = previousCounts.current;
    if (previous) {
      const created = data.books.filter((book) => !previous.has(book.id)).map((book) => book.id);
      const grown = data.books.filter((book) => (previous.get(book.id) ?? Infinity) < book.memory_count).map((book) => book.id);
      if (created.length) store().markFresh(created, "new");
      if (grown.length) store().markFresh(grown, "grown");
    }
    previousCounts.current = counts;
  }, [data, store]);

  const building = buildStartedAt !== null && Date.now() - buildStartedAt < BUILD_WATCH_MS
    && (data?.unplaced_memories ?? 0) > 0;
  useEffect(() => {
    if (buildStartedAt !== null && data && data.unplaced_memories === 0) setBuildStartedAt(null);
  }, [buildStartedAt, data]);

  const importing = (jobs.data ?? []).some(isJobRunning);
  const onChanges = useCallback((changes: UniverseChange[]) => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.universe.snapshot });
    const openId = store().openBookId;
    if (openId && changes.some((change) => change.entity_id === openId || change.kind === "update")) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.universe.book(openId) });
    }
    for (const change of changes) {
      if (change.kind === "update") {
        const firstNew = changes.find((c) => c.kind === "book_created" && c.job_id === change.job_id);
        store().pushToast({ title: "New memories discovered", body: describeUpdate(change.detail),
          bookId: firstNew?.entity_id ?? undefined });
      } else if (change.kind === "connection") {
        const others = (change.detail.other_books as { title: string }[] | undefined) ?? [];
        const who = change.detail.reason === "same_person" ? `${String(change.detail.person)} links` : "Similar memories:";
        store().pushToast({
          title: "New connection discovered",
          body: `${who} “${String(change.detail.book_title)}” ↔ “${others[0]?.title ?? "another book"}”`,
          bookId: String(change.detail.book_id),
        });
      }
    }
  }, [queryClient, store]);
  useUniverseChangeFeed(data?.cursor, importing || building, onChanges);

  // ---- render -------------------------------------------------------------------------------
  const openBook = useMemo(() => data?.books.find((book) => book.id === openBookId) ?? null, [data, openBookId]);

  if (universe.isPending) return <LoadingState label="Entering your universe…" className="h-full" />;
  if (universe.isError) {
    return <div className="p-6"><ErrorState error={universe.error} onRetry={() => void universe.refetch()} /></div>;
  }
  if (!data) return null;

  if (data.books.length === 0) {
    return (
      <EmptyUniverse
        universe={data}
        building={building || build.isPending}
        onBuild={() => build.mutate(undefined, { onSuccess: () => setBuildStartedAt(Date.now()) })}
      />
    );
  }

  return (
    <div className="relative h-[calc(100dvh-6.5rem)] overflow-hidden bg-[#04050d] md:h-screen">
      {webgl ? (
        <ErrorBoundary fallback={(error) => <BookList universe={data} onSelect={selectBook} note={`3D view failed (${error.message}).`} />}>
          <Suspense fallback={<LoadingState label="Lighting the stars…" className="h-full text-slate-300" />}>
            <UniverseScene
              universe={data}
              openBookDetail={bookDetail.data}
              onSelectBook={selectBook}
              onOpenPage={(pageId) => store().openPage(pageId)}
              onSelectYear={selectYear}
            />
          </Suspense>
        </ErrorBoundary>
      ) : (
        <BookList universe={data} onSelect={selectBook} note="WebGL isn't available here, so the universe is shown as a list." />
      )}

      {/* Overlays: pointer-events only on the controls themselves, so the scene stays draggable. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-col items-center gap-3 p-4">
        <div className="self-start">
          <UniverseBreadcrumb layout={data.layout} bookTitle={openBook?.title ?? null}
                              pageDay={openPageId ? pageDetail.data?.page.day ?? null : null} />
        </div>
        <UniverseSearch />
        {data.unplaced_memories > 0 && (
          <div className="pointer-events-auto flex items-center gap-2 rounded-full bg-slate-950/60 px-3 py-1 text-xs text-slate-300 backdrop-blur">
            <Sparkles className="size-3 text-amber-200" />
            {building ? "Placing memories in your universe…" : `${data.unplaced_memories.toLocaleString()} memories aren't placed yet.`}
            {!building && (
              <button type="button" className="cursor-pointer text-indigo-300 hover:underline"
                      onClick={() => build.mutate(undefined, { onSuccess: () => setBuildStartedAt(Date.now()) })}>
                Place them
              </button>
            )}
          </div>
        )}
      </div>

      {openBookId && (
        // Phones: a bottom sheet over the lower half, so the open book stays visible above it.
        // Wider screens: a panel on the right (the camera frames the book to its left).
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex h-[55%] p-2 md:inset-y-0 md:left-auto md:right-0 md:h-auto md:w-full md:max-w-sm md:p-3">
          <BookReader bookId={openBookId} onVisitBook={selectBook} />
        </div>
      )}

      <div className="pointer-events-none absolute bottom-16 left-4 flex flex-col gap-2 md:bottom-20">
        <IngestionStatus />
        <DiscoveryToasts onOpenBook={openBookById} />
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center p-4">
        <TimeScrubber years={data.years} layout={data.layout} cameraX={cameraX} onSelectYear={selectYear} />
      </div>

      <MemoryDetailDialog />
    </div>
  );
}

function EmptyUniverse({ universe, building, onBuild }: { universe: Universe; building: boolean; onBuild: () => void }) {
  const waiting = universe.unplaced_memories > 0;
  return (
    <div className="flex h-[calc(100dvh-6.5rem)] flex-col items-center justify-center gap-4 bg-[#04050d] p-6 text-center text-slate-200 md:h-screen">
      <Orbit className="size-10 text-indigo-300" />
      <h1 className="text-2xl font-light tracking-wide">Your Memory Universe</h1>
      {waiting ? (
        <>
          <p className="max-w-md text-sm text-slate-400">
            You have {universe.unplaced_memories.toLocaleString()} memories that haven't been placed in the universe yet.
            They'll be grouped into books — trips, periods, conversations — without changing the memories themselves.
          </p>
          <Button onClick={onBuild} disabled={building}>
            <Sparkles /> {building ? "Building your universe…" : "Build my universe"}
          </Button>
          {building && <p className="text-xs text-slate-500">This page updates by itself as books appear.</p>}
        </>
      ) : (
        <>
          <p className="max-w-md text-sm text-slate-400">Upload a chat export, journal or photos and they'll appear here as books you can visit.</p>
          <Link to="/upload" className={buttonVariants({ size: "sm" })}><Upload /> Upload memories</Link>
        </>
      )}
      {universe.undated_memories > 0 && (
        <p className="text-xs text-slate-500">{universe.undated_memories.toLocaleString()} memories have no date, so they can't be placed in time (they're still searchable).</p>
      )}
    </div>
  );
}

/** Without WebGL (or if the 3D view crashes): the same books as a list, still openable in the reader. */
function BookList({ universe, onSelect, note }: { universe: Universe; onSelect: (book: Book) => void; note: string }) {
  const byYear = new Map<string, Book[]>();
  for (const book of universe.books) {
    const year = book.start_at.slice(0, 4);
    byYear.set(year, [...(byYear.get(year) ?? []), book]);
  }
  return (
    <div className="h-full overflow-y-auto p-6 pt-28 text-slate-200">
      <p className="mb-4 rounded-md bg-white/5 p-2 text-xs text-slate-400">{note}</p>
      {[...byYear.entries()].reverse().map(([year, books]) => (
        <section key={year} className="mb-6">
          <h2 className="mb-2 text-lg font-light tracking-widest">{year}</h2>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {books.map((book) => (
              <li key={book.id}>
                <button type="button" onClick={() => onSelect(book)}
                        className="flex w-full cursor-pointer items-start gap-2 rounded-lg border border-white/10 p-3 text-left hover:bg-white/5">
                  <BookOpen className="mt-0.5 size-4 shrink-0 text-indigo-300" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm">{book.title}</span>
                    <span className="text-xs text-slate-500">{formatDate(book.start_at)} · {book.memory_count} memories</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
