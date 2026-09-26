// Upload / ingestion endpoints (docs/api-contract.md § Uploads). Called from hooks/useUploads.ts.
// Data flow for an upload: UploadForm → useUploadFiles → uploadFiles() → POST /api/uploads → the backend queues jobs.
import type { Job, Source, UploadResponse, UploadSourceType } from "@/types/api";
import { ApiError } from "./errors";
import { apiFetch, authHeaders, buildUrl, errorFromResponse } from "./client";

export function getJobs() {
  return apiFetch<Job[]>("/uploads/jobs");
}

export function retryJob(jobId: string) {
  return apiFetch<Job>(`/uploads/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST" });
}

export function getSources() {
  return apiFetch<Source[]>("/sources");
}

/** Deletes the source and every memory derived from it (responds 204). */
export function deleteSource(sourceId: string) {
  return apiFetch<void>(`/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
}

export interface UploadInput {
  files: File[];
  sourceType: UploadSourceType;
  /** The user's own name in chat exports, so the backend can tell "me" from others. */
  selfName: string;
}

/**
 * POST /uploads as multipart form data: one repeated `files` part per file, plus `source_type` and `self_name`.
 * Each file also sends its "last modified" time (`last_modified`, same order as `files`): the uploaded bytes
 * don't carry it, and photos use it as a date when they have no EXIF date.
 * Uses XMLHttpRequest instead of fetch because only XHR reports upload progress.
 */
export function uploadFiles(input: UploadInput, onProgress: (fraction: number) => void): Promise<UploadResponse> {
  const form = new FormData();
  for (const file of input.files) {
    form.append("files", file, file.name);
    form.append("last_modified", String(file.lastModified));
  }
  form.append("source_type", input.sourceType);
  if (input.selfName.trim()) form.append("self_name", input.selfName.trim());

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", buildUrl("/uploads"));
    for (const [name, value] of Object.entries(authHeaders())) request.setRequestHeader(name, value);
    request.setRequestHeader("Accept", "application/json");

    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    request.onerror = () => reject(new ApiError(0, null));
    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {
        reject(errorFromResponse(request.status, request.responseText));
        return;
      }
      try {
        resolve(JSON.parse(request.responseText) as UploadResponse);
      } catch {
        reject(new Error("The backend sent a response that is not JSON. Check VITE_API_URL or the /api proxy."));
      }
    };
    request.send(form);
  });
}
