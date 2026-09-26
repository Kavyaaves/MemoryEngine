// AI Lab endpoints (docs/api-contract.md § AI Lab). Called from hooks/useLab.ts.
import type { LabConfig, LabUsage } from "@/types/api";
import { apiFetch } from "./client";

export function getLabUsage() {
  return apiFetch<LabUsage>("/lab/usage");
}

export function getLabConfig() {
  return apiFetch<LabConfig>("/lab/config");
}
