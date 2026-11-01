// Quiet notifications in the corner: "New memories discovered", "New connection discovered".
// They never move the camera; "Open" is there if you want to go and look.
import { useEffect } from "react";
import { Sparkles, X } from "lucide-react";
import { useUniverseStore, type Toast } from "@/stores/universeStore";

const SHOW_FOR_MS = 9000;

export function DiscoveryToasts({ onOpenBook }: { onOpenBook: (bookId: string) => void }) {
  const toasts = useUniverseStore((state) => state.toasts);
  return (
    <div className="pointer-events-none flex flex-col gap-2" aria-live="polite">
      {toasts.map((toast) => <ToastCard key={toast.id} toast={toast} onOpenBook={onOpenBook} />)}
    </div>
  );
}

function ToastCard({ toast, onOpenBook }: { toast: Toast; onOpenBook: (bookId: string) => void }) {
  const dismiss = useUniverseStore((state) => state.dismissToast);
  useEffect(() => {
    const timer = window.setTimeout(() => dismiss(toast.id), SHOW_FOR_MS);
    return () => window.clearTimeout(timer);
  }, [toast.id, dismiss]);

  return (
    <div className="pointer-events-auto flex w-72 animate-[fade-in_0.6s_ease-out] items-start gap-2 rounded-xl border border-white/10 bg-slate-950/75 px-3 py-2.5 text-slate-100 shadow-xl backdrop-blur-xl">
      <Sparkles className="mt-0.5 size-4 shrink-0 text-amber-200" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.body && <p className="mt-0.5 text-xs text-slate-400">{toast.body}</p>}
        {toast.bookId && (
          <button type="button" onClick={() => { onOpenBook(toast.bookId!); dismiss(toast.id); }}
                  className="mt-1 cursor-pointer text-xs text-indigo-300 hover:underline">
            Open
          </button>
        )}
      </div>
      <button type="button" onClick={() => dismiss(toast.id)} aria-label="Dismiss"
              className="cursor-pointer text-slate-500 hover:text-white">
        <X className="size-3.5" />
      </button>
    </div>
  );
}
