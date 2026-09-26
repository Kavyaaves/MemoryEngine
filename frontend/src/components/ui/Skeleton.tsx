import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/** A grey pulsing placeholder shown while content loads. */
export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}
