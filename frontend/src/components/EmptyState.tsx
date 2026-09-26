import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { cn } from "@/lib/cn";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-lg border border-dashed px-4 py-10 text-center text-muted-foreground",
        className,
      )}
    >
      <div className="text-muted-foreground [&_svg]:size-8" aria-hidden>
        {icon ?? <Inbox />}
      </div>
      <div>
        <p className="font-medium text-foreground">{title}</p>
        {description && <div className="mx-auto mt-1 max-w-md text-sm">{description}</div>}
      </div>
      {action}
    </div>
  );
}
