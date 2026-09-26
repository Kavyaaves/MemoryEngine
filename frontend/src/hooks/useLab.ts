// AI Lab hooks used by features/lab/* → api/lab.ts.
import { useQuery } from "@tanstack/react-query";
import { getLabConfig, getLabUsage } from "@/api/lab";
import { queryKeys } from "@/api/queryKeys";

export function useLabUsage() {
  // Refresh every 30 s while the page is open so the quota tiles stay current.
  return useQuery({ queryKey: queryKeys.lab.usage, queryFn: getLabUsage, refetchInterval: 30_000 });
}

export function useLabConfig() {
  return useQuery({ queryKey: queryKeys.lab.config, queryFn: getLabConfig });
}
