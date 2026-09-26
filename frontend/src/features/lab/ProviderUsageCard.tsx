// AI Lab table: requests, tokens (incl. prompt-cache hits), errors and latency per day × provider × model × task.
// Data: useLabUsage → GET /api/lab/usage
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { useLabUsage } from "@/hooks/useLab";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";

export function ProviderUsageCard({ className }: { className?: string }) {
  const usage = useLabUsage();
  // Newest day first; within a day, the busiest row first.
  const rows = [...(usage.data?.providers ?? [])].sort(
    (a, b) => b.day.localeCompare(a.day) || b.request_count - a.request_count,
  );

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Provider usage</CardTitle>
      </CardHeader>
      <CardContent>
        {usage.isPending ? (
          <Skeleton className="h-40" />
        ) : usage.isError ? (
          <ErrorState error={usage.error} onRetry={() => void usage.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="No AI calls yet" description="Usage appears after you ask questions or ingest data." />
        ) : (
          <div className="-mx-5 overflow-x-auto px-5">
            <table className="w-full min-w-[800px] text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="py-2 pr-3 font-medium">Day</th>
                  <th className="py-2 pr-3 font-medium">Provider</th>
                  <th className="py-2 pr-3 font-medium">Model</th>
                  <th className="py-2 pr-3 font-medium">Task</th>
                  <th className="py-2 pr-3 text-right font-medium">Requests</th>
                  <th className="py-2 pr-3 text-right font-medium">In tok</th>
                  <th className="py-2 pr-3 text-right font-medium" title="Input tokens served from OpenAI's prompt cache">
                    Cached
                  </th>
                  <th className="py-2 pr-3 text-right font-medium">Out tok</th>
                  <th className="py-2 pr-3 text-right font-medium">Errors</th>
                  <th className="py-2 text-right font-medium">Avg latency</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.day}-${row.provider}-${row.model}-${row.task}-${index}`} className="border-b last:border-0">
                    <td className="whitespace-nowrap py-1.5 pr-3 text-muted-foreground">{row.day.slice(0, 10)}</td>
                    <td className="py-1.5 pr-3">{row.provider}</td>
                    <td className="py-1.5 pr-3 font-mono text-xs">{row.model}</td>
                    <td className="py-1.5 pr-3">
                      <Badge variant="secondary">{row.task}</Badge>
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{formatNumber(row.request_count)}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{formatNumber(row.input_tokens)}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{formatNumber(row.cached_input_tokens ?? 0)}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{formatNumber(row.output_tokens)}</td>
                    <td className={cn("py-1.5 pr-3 text-right tabular-nums", row.errors > 0 && "text-destructive")}>
                      {formatNumber(row.errors)}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">{Math.round(row.avg_latency_ms)} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
