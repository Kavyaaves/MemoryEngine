import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

interface ProgressProps extends ComponentProps<"div"> {
  /** 0..1 */
  value: number;
  indicatorClassName?: string;
}

/** A horizontal progress bar. Pass `aria-label` so screen readers know what is progressing. */
export function Progress({ value, className, indicatorClassName, ...props }: ProgressProps) {
  const percent = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0)) * 100;
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(percent)}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-muted", className)}
      {...props}
    >
      <div
        className={cn("h-full rounded-full bg-primary transition-[width] duration-500", indicatorClassName)}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
