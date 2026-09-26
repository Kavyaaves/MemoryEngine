// AI Lab: the local sentiment model — is it installed, how many memories are analysed, and "Analyse now".
// New uploads are analysed automatically; this button catches up on memories imported earlier.
// Data: useSentimentStatus → GET /api/sentiment/status · button → POST /api/sentiment/analyze
import { Play } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Progress } from "@/components/ui/Progress";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { useSentimentStatus, useStartSentimentAnalysis } from "@/hooks/useSentiment";

export function SentimentCard() {
  const status = useSentimentStatus();
  const start = useStartSentimentAnalysis();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sentiment</CardTitle>
        <CardDescription>
          A local Tamil + Tanglish model on the server&apos;s CPU — no text leaves the server. Photos are only
          analysed through their ingested captions.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {status.isPending ? (
          <Skeleton className="h-24" />
        ) : status.isError ? (
          <ErrorState error={status.error} onRetry={() => void status.refetch()} />
        ) : (
          <div className="flex flex-col gap-3 text-sm">
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
              <dt className="text-muted-foreground">Model</dt>
              <dd className="break-all font-mono text-xs">{status.data.model}</dd>
              <dt className="text-muted-foreground">State</dt>
              <dd>
                {!status.data.enabled ? (
                  <Badge variant="muted">switched off</Badge>
                ) : !status.data.installed ? (
                  <Badge variant="warning">not installed (pip install -e &quot;.[sentiment]&quot;)</Badge>
                ) : (
                  <Badge variant="success">ready</Badge>
                )}
              </dd>
              <dt className="text-muted-foreground">Analysed</dt>
              <dd className="tabular-nums">
                {status.data.done.toLocaleString()} / {(status.data.done + status.data.remaining).toLocaleString()}
              </dd>
            </dl>
            <Progress
              value={status.data.done / Math.max(1, status.data.done + status.data.remaining)}
              aria-label="Memories analysed"
            />
            {start.isError && (
              <p role="alert" className="text-xs text-destructive">
                {start.error.message}
              </p>
            )}
            <div className="flex justify-end">
              <Button
                size="sm"
                onClick={() => start.mutate()}
                disabled={
                  !status.data.enabled || !status.data.installed || status.data.running ||
                  status.data.remaining === 0 || start.isPending
                }
              >
                {status.data.running || start.isPending ? <Spinner /> : <Play />}
                {status.data.running ? "Analysing…" : `Analyse ${status.data.remaining.toLocaleString()} remaining`}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
