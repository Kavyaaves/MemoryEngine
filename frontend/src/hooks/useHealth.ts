// Settings page → useHealth → api/health.ts → GET /api/health
import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/api/health";
import { queryKeys } from "@/api/queryKeys";

export function useHealth() {
  // No retries: a health check should report the current state immediately.
  return useQuery({ queryKey: queryKeys.health, queryFn: getHealth, retry: false });
}
