// AI Lab headline tiles: requests today / this month and tokens in the current window against
// their limits (or total tokens when no token budget is set), and errors.
// Data: useLabUsage → GET /api/lab/usage (refreshed every 30 s)
import { Card } from "@/components/ui/Card";
import { Progress } from "@/components/ui/Progress";
import { useLabUsage } from "@/hooks/useLab";
import type { ProviderUsageRow } from "@/types/api";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";

function summarise(rows: ProviderUsageRow[]) {
  // Usage rows are per UTC day, so compare against today's UTC date.
  const today = new Date().toISOString().slice(0, 10);
  const thisMonth = today.slice(0, 7);
  let requestsToday = 0;
  let requestsThisMonth = 0;
  let tokens = 0;
  let errors = 0;
  for (const row of rows) {
    if (row.day.startsWith(today)) requestsToday += row.request_count;
    if (row.day.startsWith(thisMonth)) requestsThisMonth += row.request_count;
    tokens += row.input_tokens + row.output_tokens;
    errors += row.errors;
  }
  return { requestsToday, requestsThisMonth, tokens, errors };
}

export function UsageSummary() {
  const usage = useLabUsage();
  if (!usage.data) return null; // the usage table below shows loading and error states

  const summary = summarise(usage.data.providers);
  const { limits } = usage.data;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <QuotaTile label="Requests today" value={summary.requestsToday} limit={limits.max_daily_requests} />
      <QuotaTile label="Requests this month" value={summary.requestsThisMonth} limit={limits.max_monthly_requests} />
      {limits.max_tokens_per_window ? (
        <QuotaTile
          label={`Tokens this ${limits.token_window_hours ?? 24} h window`}
          value={limits.tokens_used_in_window ?? 0}
          limit={limits.max_tokens_per_window}
        />
      ) : (
        <Tile label="Tokens (all rows)" value={formatNumber(summary.tokens)} />
      )}
      <Tile label="Errors" value={formatNumber(summary.errors)} warn={summary.errors > 0} />
    </div>
  );
}

function Tile({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("mt-1 text-2xl font-semibold tabular-nums", warn && "text-warning")}>{value}</div>
    </Card>
  );
}

/** A number with its limit and a bar that turns amber above 70 % and red above 90 %. */
function QuotaTile({ label, value, limit }: { label: string; value: number; limit: number }) {
  const usedFraction = limit > 0 ? value / limit : 0;
  return (
    <Card className="p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="text-2xl font-semibold tabular-nums">{formatNumber(value)}</span>
        {limit > 0 && <span className="text-xs text-muted-foreground">/ {formatNumber(limit)}</span>}
      </div>
      {limit > 0 && (
        <Progress
          value={usedFraction}
          aria-label={`${label}: ${formatNumber(value)} of ${formatNumber(limit)}`}
          className="mt-2 h-1.5"
          indicatorClassName={usedFraction > 0.9 ? "bg-destructive" : usedFraction > 0.7 ? "bg-warning" : undefined}
        />
      )}
    </Card>
  );
}
