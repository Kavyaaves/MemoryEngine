// How a failed HTTP call becomes a message a person can read.
// api/client.ts throws an ApiError for every non-2xx response; components simply show `error.message`
// (see components/ErrorState.tsx), so all wording decisions live here.

export class ApiError extends Error {
  /** HTTP status code, or 0 when the backend could not be reached at all. */
  readonly status: number;
  /** The server's own explanation (FastAPI's `detail`), when it sent one. */
  readonly detail: string | null;

  constructor(status: number, detail: string | null) {
    super(readableMessage(status, detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function readableMessage(status: number, detail: string | null): string {
  switch (status) {
    case 0:
      return "Cannot reach the backend. Is it running?";
    case 401:
      return detail ?? "Your session has expired. Please sign in again.";
    case 404:
      return detail ? `Not found: ${detail}` : "Not found.";
    case 501:
      return detail ? `Not available yet: ${detail}` : "This feature is not available yet.";
    case 502:
    case 503:
    case 504:
      // The backend answers 503 {"detail": "..."} when its database is unreachable.
      return detail
        ? `Service unavailable: ${detail}`
        : "The server is temporarily unavailable. Please try again in a moment.";
  }
  if (detail) return detail;
  if (status >= 500) return `The server hit an unexpected error (HTTP ${status}). Please try again.`;
  return `Request failed (HTTP ${status}).`;
}

/**
 * Pull the human-readable part out of an error body:
 *   {"detail": "..."}                    — FastAPI HTTPException
 *   {"detail": [{"msg": "..."}, ...]}    — FastAPI validation error (422)
 *   {"message": "..."}                   — other JSON errors
 * Anything else (an HTML error page from a proxy, a bare "Internal Server Error") is ignored,
 * because showing it to the user would not help.
 */
export function detailFromBody(body: unknown): string | null {
  if (typeof body !== "object" || body === null) return null;

  if ("detail" in body) {
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item: unknown) =>
          typeof item === "object" && item !== null && "msg" in item ? String(item.msg) : "",
        )
        .filter(Boolean);
      if (messages.length > 0) return messages.join("; ");
    }
  }
  if ("message" in body && typeof body.message === "string") return body.message;
  return null;
}
