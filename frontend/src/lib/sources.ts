// Display metadata (label, colour, icon) for each memory source type, used by badges, charts and the 3D scene.
import { Database, FileText, Image, Instagram, MessageCircle, Mic, NotebookPen, Video, type LucideIcon } from "lucide-react";
import type { SourceType, TimelineBucket } from "@/types/api";

export interface SourceMeta {
  label: string;
  /** Hex colour; also used by three.js, which can't read CSS variables. */
  color: string;
  icon: LucideIcon;
}

export const SOURCE_META: Record<SourceType, SourceMeta> = {
  whatsapp: { label: "WhatsApp", color: "#22c55e", icon: MessageCircle },
  instagram: { label: "Instagram", color: "#ec4899", icon: Instagram },
  journal: { label: "Journal", color: "#f59e0b", icon: NotebookPen },
  document: { label: "Document", color: "#3b82f6", icon: FileText },
  image: { label: "Photo", color: "#a855f7", icon: Image },
  audio: { label: "Audio", color: "#06b6d4", icon: Mic },
  video: { label: "Video", color: "#ef4444", icon: Video },
};

function isKnownSourceType(type: string): type is SourceType {
  return type in SOURCE_META;
}

/** Metadata for any source type string; unknown types get a neutral look and their raw name as label. */
export function sourceMeta(type: string | null | undefined): SourceMeta {
  if (type && isKnownSourceType(type)) return SOURCE_META[type];
  return { label: type || "Other", color: "#94a3b8", icon: Database };
}

/** The source type with the most memories in a `{type: count}` map, or null if empty. */
export function dominantSource(countsBySource: Record<string, number>): string | null {
  let best: string | null = null;
  let bestCount = -1;
  for (const [type, count] of Object.entries(countsBySource)) {
    if (count > bestCount) {
      best = type;
      bestCount = count;
    }
  }
  return best;
}

/** Add up the per-source counts of many timeline buckets. */
export function totalsBySource(buckets: TimelineBucket[]): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const bucket of buckets) {
    for (const [type, count] of Object.entries(bucket.sources)) {
      totals[type] = (totals[type] ?? 0) + count;
    }
  }
  return totals;
}
