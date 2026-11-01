// Memory Universe hooks used by the Memories page (pages/Memories, features/universe, universe/) → api/universe.ts.
import { useEffect, useRef } from "react";
import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  buildUniverse,
  getBook,
  getMemoryDetail,
  getPage,
  getUniverse,
  getUniverseChanges,
  renameBook,
} from "@/api/universe";
import { queryKeys } from "@/api/queryKeys";
import type { UniverseChange } from "@/types/api";

/** While an import or build runs, check for universe changes this often. */
const CHANGE_POLL_INTERVAL_MS = 3000;

export function useUniverse() {
  return useQuery({ queryKey: queryKeys.universe.snapshot, queryFn: getUniverse });
}

export function useBook(bookId: string | null) {
  return useQuery({
    queryKey: queryKeys.universe.book(bookId ?? ""),
    queryFn: bookId ? () => getBook(bookId) : skipToken,
  });
}

export function usePage(pageId: string | null) {
  return useQuery({
    queryKey: queryKeys.universe.page(pageId ?? ""),
    queryFn: pageId ? () => getPage(pageId) : skipToken,
  });
}

export function useMemoryDetail(memoryId: string | null) {
  return useQuery({
    queryKey: queryKeys.universe.memory(memoryId ?? ""),
    queryFn: memoryId ? () => getMemoryDetail(memoryId) : skipToken,
  });
}

/**
 * Calls `onChanges` with every new universe change, polling only while `active` (an import or a build
 * is running) — plus one last check right after it stops, to catch the final changes.
 * Starts from `startCursor` (the snapshot's cursor), so changes from before the page opened are skipped.
 */
export function useUniverseChangeFeed(
  startCursor: number | undefined,
  active: boolean,
  onChanges: (changes: UniverseChange[]) => void,
) {
  const cursor = useRef<number | null>(null);
  const onChangesRef = useRef(onChanges);
  onChangesRef.current = onChanges;
  const wasActive = useRef(false);

  if (cursor.current === null && startCursor !== undefined) cursor.current = startCursor;

  useEffect(() => {
    const justStopped = wasActive.current && !active;
    wasActive.current = active;
    if (!active && !justStopped) return;

    let cancelled = false;
    const check = async () => {
      if (cursor.current === null) return;
      try {
        const result = await getUniverseChanges(cursor.current);
        if (cancelled || result.changes.length === 0) return;
        cursor.current = result.cursor;
        onChangesRef.current(result.changes);
      } catch {
        // A failed poll is retried on the next tick; the universe itself stays usable.
      }
    };
    void check();
    if (!active) return; // the one last check after an import finished
    const timer = window.setInterval(() => void check(), CHANGE_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [active]);
}

export function useBuildUniverse() {
  return useMutation({ mutationFn: buildUniverse });
}

export function useRenameBook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ bookId, title }: { bookId: string; title: string }) => renameBook(bookId, title),
    onSuccess: (_book, { bookId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.universe.book(bookId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.universe.snapshot });
    },
  });
}
