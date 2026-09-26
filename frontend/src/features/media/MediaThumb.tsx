// Shows one media attachment (photo, audio or video) of a memory.
// The file is loaded through useAuthedMedia because backend media needs the bearer token.
import type { ReactNode } from "react";
import { FileAudio, FileVideo, ImageOff } from "lucide-react";
import { useAuthedMedia } from "@/hooks/useAuthedMedia";
import type { MediaRef } from "@/types/api";
import { cn } from "@/lib/cn";

function mediaKind(media: MediaRef): "image" | "audio" | "video" | "other" {
  const kind = (media.kind || media.mime_type || "").toLowerCase();
  if (kind.startsWith("image") || kind === "photo") return "image"; // the backend calls photos "photo"
  if (kind.startsWith("audio")) return "audio";
  if (kind.startsWith("video")) return "video";
  return "other";
}

interface MediaThumbProps {
  media: MediaRef;
  className?: string;
  /** Show playable <audio>/<video> players instead of an icon. */
  controls?: boolean;
  /** Describes the photo for screen readers. */
  alt?: string;
}

export function MediaThumb({ media, className, controls = false, alt = "Photo" }: MediaThumbProps) {
  const { src, failed } = useAuthedMedia(media.url);
  const kind = mediaKind(media);

  if (failed) return <IconTile icon={<ImageOff className="size-6" />} label="Media unavailable" className={className} />;
  if (!src) return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;

  if (kind === "image") {
    return (
      <a
        href={src}
        target="_blank"
        rel="noreferrer"
        aria-label={`Open ${alt} in a new tab`}
        className={cn("block overflow-hidden rounded-md bg-muted", className)}
      >
        <img src={src} alt={alt} loading="lazy" className="size-full object-cover transition-transform hover:scale-105" />
      </a>
    );
  }
  if (kind === "video") {
    return controls ? (
      <video src={src} controls preload="metadata" className={cn("w-full rounded-md bg-black", className)} />
    ) : (
      <IconTile icon={<FileVideo className="size-6" />} label="Video" className={className} />
    );
  }
  if (kind === "audio") {
    return controls ? (
      <audio src={src} controls preload="metadata" className={cn("w-full", className)} />
    ) : (
      <IconTile icon={<FileAudio className="size-6" />} label="Audio" className={className} />
    );
  }
  return <IconTile icon={<ImageOff className="size-6" />} label="Unsupported media" className={className} />;
}

function IconTile({ icon, label, className }: { icon: ReactNode; label: string; className?: string }) {
  return (
    <div
      role="img"
      aria-label={label}
      className={cn("flex items-center justify-center rounded-md bg-muted text-muted-foreground", className)}
    >
      {icon}
    </div>
  );
}
