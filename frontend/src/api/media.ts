// Loading media files (photos, audio, video) referenced by Evidence.media[].url.
// <img>/<audio>/<video> tags cannot send an Authorization header, and the token must never go in a URL,
// so media hosted by our backend is downloaded with fetch + token and shown through a blob: URL.
// Data flow: MediaThumb → useAuthedMedia (hooks/useAuthedMedia.ts) → fetchMediaBlob() → GET <media url>
import { API_BASE, API_ORIGIN, authHeaders, errorFromResponse, sendRequest } from "./client";

/** Absolute URLs pass through; "/x" is relative to the backend origin; "x" is relative to /api. */
export function resolveMediaUrl(url: string): string {
  if (/^(https?:|data:|blob:)/i.test(url)) return url;
  if (url.startsWith("/")) return `${API_ORIGIN}${url}`;
  return `${API_BASE}/${url}`;
}

/** True when the URL points at our backend (so it needs the token), false for e.g. pre-signed storage links. */
export function isBackendUrl(resolvedUrl: string): boolean {
  if (/^(data:|blob:)/i.test(resolvedUrl)) return false;
  if (!/^https?:/i.test(resolvedUrl)) return true; // relative → same origin as the app, proxied to the backend
  return resolvedUrl.startsWith(API_ORIGIN || window.location.origin);
}

export async function fetchMediaBlob(resolvedUrl: string, signal: AbortSignal): Promise<Blob> {
  const response = await sendRequest(resolvedUrl, { headers: authHeaders(), signal });
  if (!response.ok) throw errorFromResponse(response.status, await response.text());
  return response.blob();
}
