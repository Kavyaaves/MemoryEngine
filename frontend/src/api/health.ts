// GET /api/health (docs/api-contract.md § Health). Called from hooks/useHealth.ts.
import type { Health } from "@/types/api";
import { apiFetch } from "./client";

export function getHealth() {
  return apiFetch<Health>("/health");
}
