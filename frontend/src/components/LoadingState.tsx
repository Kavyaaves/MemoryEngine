import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";

export function LoadingState({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div
      role="status"
      className={cn("flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground", className)}
    >
      <Spinner /> {label}
    </div>
  );
}
