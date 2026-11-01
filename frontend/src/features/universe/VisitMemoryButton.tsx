// "Visit memory" from outside the universe (e.g. the Ask page): opens the Memories page, which
// flies Universe → year → month → book → page and highlights the exact message.
import { Link } from "react-router";
import { Navigation } from "lucide-react";
import { cn } from "@/lib/cn";

export function visitMemoryPath(memoryId: string): string {
  return `/memories?memory=${encodeURIComponent(memoryId)}`;
}

export function VisitMemoryButton({ memoryId, className, label = "Visit" }: { memoryId: string; className?: string; label?: string }) {
  return (
    <Link
      to={visitMemoryPath(memoryId)}
      onClick={(event) => event.stopPropagation()}
      className={cn(
        "inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary hover:bg-primary/20",
        className,
      )}
    >
      <Navigation className="size-3" /> {label}
    </Link>
  );
}
