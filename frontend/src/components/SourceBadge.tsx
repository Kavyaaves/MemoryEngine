import { sourceMeta } from "@/lib/sources";
import { cn } from "@/lib/cn";

/** Coloured "WhatsApp" / "Journal" / … label for a memory's source type. */
export function SourceBadge({ type, className }: { type: string; className?: string }) {
  const meta = sourceMeta(type);
  const Icon = meta.icon;
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium", className)}
      // "1f" appended to the hex colour = ~12% opacity background.
      style={{ color: meta.color, backgroundColor: `${meta.color}1f` }}
    >
      <Icon className="size-3" aria-hidden />
      {meta.label}
    </span>
  );
}
