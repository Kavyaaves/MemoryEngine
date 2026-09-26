// Low-level HTTP helpers shared by every api/<domain>.ts module.
// Data flow: component → hook (hooks/use*.ts) → api/<domain>.ts → apiFetch() → fetch("/api/...")
// Responsibilities: build /api URLs, attach the bearer token (always as a header, never in the URL),
// turn error responses into ApiError, and end the session on a 401.
import { useAuthStore } from "@/stores/authStore";
import { ApiError, detailFromBody } from "./errors";

/** Origin of the backend; "" means same origin (the Vite dev proxy or nginx forwards /api). */
export const API_ORIGIN = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
/** Every endpoint in the contract lives under /api. */
export const API_BASE = `${API_ORIGIN}/api`;

export function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type QueryParams = Record<string, string | number | undefined>;

export function buildUrl(path: string, query?: QueryParams): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const queryString = params.toString();
  return queryString ? `${url}?${queryString}` : url;
}

/** fetch() that reports "backend unreachable" as ApiError(0) instead of a bare TypeError. */
export async function sendRequest(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error; // cancelled on purpose
    throw new ApiError(0, null);
  }
}

/** Build the ApiError for a non-2xx response. A 401 means the token is no longer valid, so the session ends. */
export function errorFromResponse(status: number, bodyText: string): ApiError {
  if (status === 401 && useAuthStore.getState().token) {
    useAuthStore.getState().logout();
  }
  let body: unknown = null;
  try {
    body = JSON.parse(bodyText);
  } catch {
    // Not JSON (HTML error page, plain text) — ApiError falls back to a message based on the status.
  }
  return new ApiError(status, detailFromBody(body));
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  /** Sent as a JSON body. */
  json?: unknown;
  query?: QueryParams;
  signal?: AbortSignal;
}

/** Call a JSON endpoint and return the parsed body (undefined for an empty body, e.g. 204). */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...authHeaders() };
  let body: string | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }

  const response = await sendRequest(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body,
    signal: options.signal,
  });
  const text = await response.text();
  if (!response.ok) throw errorFromResponse(response.status, text);
  if (!text) return undefined as T;

  try {
    return JSON.parse(text) as T;
  } catch {
    // Usually means /api is not proxied to the backend and we received the app's index.html instead.
    throw new Error("The backend sent a response that is not JSON. Check VITE_API_URL or the /api proxy.");
  }
}
