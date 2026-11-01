// The reader: a calm panel beside the 3D scene for the open Memory Book.
//   header    title (rename it if you like), dates, type, people, places
//   summary   the AI summary — labelled as AI-written and linked to the exact memories it was written from
//   related   books connected through a person or similar memories ("visit")
//   pages     one entry per conversation-day; opening one shows its memories (PageView)
import { useEffect, useRef, useState } from "react";
import { BookOpen, ChevronLeft, Link2, MapPin, Pencil, Sparkles, Users, X } from "lucide-react";
import type { Book, BookDetail } from "@/types/api";
import { useBook, useRenameBook } from "@/hooks/useUniverse";
import { useUniverseStore } from "@/stores/universeStore";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/cn";
import { eventColor } from "@/universe/universeMath";
import { PageView } from "./PageView";

interface BookReaderProps {
  bookId: string;
  onVisitBook: (book: Book) => void;
}

function dateRange(book: Book): string {
  const start = formatDate(book.start_at);
  const end = formatDate(book.end_at);
  return start === end ? start : `${start} – ${end}`;
}

export function BookReader({ bookId, onVisitBook }: BookReaderProps) {
  const book = useBook(bookId);
  const openPageId = useUniverseStore((state) => state.openPageId);
  const openPage = useUniverseStore((state) => state.openPage);
  const closeBook = useUniverseStore((state) => state.closeBook);
  const freshBooks = useUniverseStore((state) => state.freshBooks);
  const freshPages = useUniverseStore((state) => state.freshPages);
  const markFreshPages = useUniverseStore((state) => state.markFreshPages);

  // Pages that appear while this book is open (new memories arrived) get a ✨ mark.
  const knownPages = useRef<{ bookId: string; ids: Set<string> } | null>(null);
  useEffect(() => {
    const pages = book.data?.pages;
    if (!pages) return;
    const ids = new Set(pages.map((page) => page.id));
    const known = knownPages.current;
    if (known?.bookId === bookId) {
      const added = pages.filter((page) => !known.ids.has(page.id)).map((page) => page.id);
      if (added.length) markFreshPages(added);
    }
    knownPages.current = { bookId, ids };
  }, [book.data, bookId, markFreshPages]);

  return (
    <aside className="pointer-events-auto flex h-full w-full flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-950/75 text-slate-100 shadow-2xl backdrop-blur-xl">
      <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5">
        {openPageId ? (
          <button type="button" onClick={() => openPage(null)}
                  className="-ml-1 inline-flex cursor-pointer items-center gap-1 rounded px-1 text-xs text-indigo-200 hover:text-white">
            <ChevronLeft className="size-4" /> All pages
          </button>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs uppercase tracking-wider text-indigo-200/80">
            <BookOpen className="size-3.5" /> Memory book
          </span>
        )}
        <button type="button" onClick={closeBook} aria-label="Close book"
                className="ml-auto cursor-pointer rounded p-1 text-slate-400 hover:bg-white/10 hover:text-white">
          <X className="size-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {book.isPending && <p className="text-sm text-slate-400">Opening the book…</p>}
        {book.isError && <p className="text-sm text-rose-300">This book couldn't be opened. It may have been removed.</p>}
        {book.data && (openPageId ? (
          <PageView pageId={openPageId} />
        ) : (
          <BookOverview detail={book.data} fresh={Boolean(freshBooks[bookId])} freshPages={freshPages}
                        onOpenPage={(id) => openPage(id)} onVisitBook={onVisitBook} />
        ))}
      </div>
    </aside>
  );
}

interface BookOverviewProps {
  detail: BookDetail;
  fresh: boolean;
  freshPages: Record<string, number>;
  onOpenPage: (pageId: string) => void;
  onVisitBook: (book: Book) => void;
}

function BookOverview({ detail, fresh, freshPages, onOpenPage, onVisitBook }: BookOverviewProps) {
  const { book, summary, summary_memory_ids, places, pages, related } = detail;
  const showMemory = useUniverseStore((state) => state.showMemory);
  const [showSources, setShowSources] = useState(false);
  const freshPageCount = pages.filter((page) => freshPages[page.id]).length;

  return (
    <div className="flex flex-col gap-4">
      <header>
        <div className="mb-1.5 flex items-center gap-2 text-[11px] uppercase tracking-wider">
          <span className="size-2 rounded-full" style={{ backgroundColor: eventColor(book.event_type) }} />
          <span className="text-slate-400">{book.event_type}</span>
          {fresh && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-300/15 px-2 py-0.5 text-amber-200">
              <Sparkles className="size-3" /> new memories
            </span>
          )}
        </div>
        <BookTitle book={book} />
        <p className="mt-1 text-sm text-slate-400">{dateRange(book)}</p>
        <p className="mt-1 text-xs text-slate-500">
          {book.memory_count.toLocaleString()} memories · {book.page_count} pages
          {book.photo_count > 0 && ` · ${book.photo_count} photos`}
        </p>
        {book.people.length > 0 && (
          <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-slate-300">
            <Users className="size-3.5 text-slate-500" />
            {book.people.map((person) => (
              <span key={person.id} className="rounded-full bg-white/5 px-2 py-0.5">{person.name}</span>
            ))}
          </p>
        )}
        {places.length > 0 && (
          <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-300">
            <MapPin className="size-3.5 text-slate-500" />
            {places.join(" · ")}
          </p>
        )}
      </header>

      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
        {summary ? (
          <>
            <p className="text-sm leading-relaxed text-slate-200">{summary}</p>
            <button type="button" onClick={() => setShowSources((shown) => !shown)}
                    className="mt-2 cursor-pointer text-[11px] text-indigo-300 hover:underline">
              AI summary · written from {summary_memory_ids.length} of this book's memories
              {showSources ? " (hide)" : " (show them)"}
            </button>
            {showSources && (
              <div className="mt-2 flex flex-wrap gap-1">
                {summary_memory_ids.map((id, index) => (
                  <button key={id} type="button" onClick={() => showMemory(id)}
                          className="cursor-pointer rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-slate-300 hover:bg-white/10">
                    {index + 1}
                  </button>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="text-xs text-slate-400">
            {book.title_source === "user"
              ? "You named this book."
              : "Named from the people and dates in it. An AI summary appears once the book has been read."}
          </p>
        )}
      </section>

      {related.length > 0 && (
        <section>
          <h3 className="mb-1.5 flex items-center gap-1.5 text-xs uppercase tracking-wider text-slate-400">
            <Link2 className="size-3.5" /> Connected books
          </h3>
          <ul className="flex flex-col gap-1">
            {related.map((entry) => (
              <li key={entry.book.id}>
                <button type="button" onClick={() => onVisitBook(entry.book)}
                        className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-white/5">
                  <span className={cn("size-1.5 shrink-0 rounded-full",
                    entry.reason === "same_person" ? "bg-pink-300" : "bg-teal-300")} />
                  <span className="min-w-0 flex-1 truncate">{entry.book.title}</span>
                  <span className="shrink-0 text-[11px] text-slate-500">{entry.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3 className="mb-1.5 flex items-center justify-between text-xs uppercase tracking-wider text-slate-400">
          Pages
          {freshPageCount > 0 && (
            <span className="inline-flex items-center gap-1 normal-case tracking-normal text-amber-200">
              <Sparkles className="size-3" /> {freshPageCount} new
            </span>
          )}
        </h3>
        <ol className="flex flex-col gap-1">
          {pages.map((page) => (
            <li key={page.id}>
              <button type="button" onClick={() => onOpenPage(page.id)}
                      className="w-full cursor-pointer rounded-lg px-2 py-1.5 text-left hover:bg-white/5">
                <div className="flex items-center gap-2 text-xs">
                  {freshPages[page.id] && <Sparkles className="size-3 shrink-0 text-amber-200" />}
                  <span className="font-medium text-slate-200">{formatDate(page.day)}</span>
                  <span className="min-w-0 flex-1 truncate text-slate-500">{page.thread_name}</span>
                  <span className="shrink-0 text-slate-500">{page.memory_count}</span>
                </div>
                {page.preview && <p className="mt-0.5 truncate text-xs text-slate-400">{page.preview}</p>}
              </button>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function BookTitle({ book }: { book: Book }) {
  const rename = useRenameBook();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(book.title);

  if (editing) {
    return (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (draft.trim()) rename.mutate({ bookId: book.id, title: draft.trim() }, { onSuccess: () => setEditing(false) });
        }}
      >
        <input
          autoFocus
          value={draft}
          maxLength={120}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => event.key === "Escape" && setEditing(false)}
          aria-label="Book title"
          className="w-full rounded-md border border-white/20 bg-white/5 px-2 py-1 text-lg font-semibold text-white outline-none focus:border-indigo-300"
        />
        <p className="mt-1 text-[11px] text-slate-500">Enter to save · Esc to cancel. Your title is never replaced by AI.</p>
      </form>
    );
  }
  return (
    <h2 className="group flex items-start gap-2 text-lg font-semibold leading-snug text-white">
      <span>{book.title}</span>
      <button type="button" onClick={() => { setDraft(book.title); setEditing(true); }} aria-label="Rename book"
              className="mt-1 cursor-pointer rounded p-0.5 text-slate-500 opacity-0 transition-opacity hover:text-white group-hover:opacity-100 focus:opacity-100">
        <Pencil className="size-3.5" />
      </button>
    </h2>
  );
}
