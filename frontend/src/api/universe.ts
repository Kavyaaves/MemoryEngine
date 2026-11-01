// Memory Universe endpoints (backend app/api/universe.py). Called from hooks/useUniverse.ts.
import type { AskResponse, Book, BookDetail, MemoryDetail, PageDetail, Universe, UniverseChanges } from "@/types/api";
import { apiFetch } from "./client";

/** Everything the 3D scene needs: books with their fixed positions, years, months, change cursor. */
export function getUniverse() {
  return apiFetch<Universe>("/universe");
}

export function getBook(bookId: string) {
  return apiFetch<BookDetail>(`/universe/books/${encodeURIComponent(bookId)}`);
}

export function renameBook(bookId: string, title: string) {
  return apiFetch<Book>(`/universe/books/${encodeURIComponent(bookId)}`, { method: "PATCH", json: { title } });
}

export function getPage(pageId: string) {
  return apiFetch<PageDetail>(`/universe/pages/${encodeURIComponent(pageId)}`);
}

/** One memory: the original text, where it is in the universe, its conversation context and connections. */
export function getMemoryDetail(memoryId: string) {
  return apiFetch<MemoryDetail>(`/universe/memories/${encodeURIComponent(memoryId)}`);
}

/** What changed after change `after` (the Memories page polls this while imports run). */
export function getUniverseChanges(after: number) {
  return apiFetch<UniverseChanges>("/universe/changes", { query: { after } });
}

/** Place memories imported before the universe existed (runs in the background). */
export function buildUniverse() {
  return apiFetch<{ status: "queued" | "inline" }>("/universe/build", { method: "POST" });
}

/** The agent's answer in one response (no streaming) — used by the universe's search pill. */
export function askOnce(question: string) {
  return apiFetch<AskResponse>("/ask", { method: "POST", json: { question } });
}
