// Turns a media URL from the API into something an <img>/<audio>/<video> can display.
// Backend-hosted files need the bearer token, so they are downloaded (api/media.ts) and shown via a
// temporary blob: URL; other URLs (e.g. pre-signed storage links) are used as they are.
// Data flow: MediaThumb → useAuthedMedia → fetchMediaBlob → GET <media url>
import { useEffect, useState } from "react";
import { fetchMediaBlob, isBackendUrl, resolveMediaUrl } from "@/api/media";

interface LoadedMedia {
  url: string;
  objectUrl: string | null;
  failed: boolean;
}

export function useAuthedMedia(url: string): { src: string | null; failed: boolean } {
  const resolvedUrl = resolveMediaUrl(url);
  const needsToken = isBackendUrl(resolvedUrl);
  const [loaded, setLoaded] = useState<LoadedMedia | null>(null);

  useEffect(() => {
    if (!needsToken) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;

    fetchMediaBlob(resolvedUrl, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setLoaded({ url: resolvedUrl, objectUrl, failed: false });
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoaded({ url: resolvedUrl, objectUrl: null, failed: true });
      });

    return () => {
      controller.abort();
      // Blob URLs keep the file in memory until revoked.
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [resolvedUrl, needsToken]);

  if (!needsToken) return { src: resolvedUrl, failed: false };
  // `loaded` may still describe the previous URL while the new one downloads.
  if (loaded?.url !== resolvedUrl) return { src: null, failed: false };
  return { src: loaded.objectUrl, failed: loaded.failed };
}
