// AI Lab: which AI providers have keys configured on the server, and the retrieval settings.
// Data: useLabConfig → GET /api/lab/config
import { CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ErrorState";
import { useLabConfig } from "@/hooks/useLab";

export function LabConfigCard() {
  const config = useLabConfig();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Configuration</CardTitle>
      </CardHeader>
      <CardContent>
        {config.isPending ? (
          <Skeleton className="h-40" />
        ) : config.isError ? (
          <ErrorState error={config.error} onRetry={() => void config.refetch()} />
        ) : (
          <div className="flex flex-col gap-5 text-sm">
            <section>
              <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Providers</h4>
              <ul className="flex flex-col gap-1">
                {config.data.providers.map((provider) => (
                  <li key={provider.name} className="flex items-center gap-2">
                    {provider.configured ? (
                      <CheckCircle2 className="size-4 text-success" aria-hidden />
                    ) : (
                      <XCircle className="size-4 text-muted-foreground" aria-hidden />
                    )}
                    <span className="flex-1">{provider.name}</span>
                    <Badge variant={provider.configured ? "success" : "muted"}>
                      {provider.configured ? "configured" : "missing key"}
                    </Badge>
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Retrieval</h4>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                <dt className="text-muted-foreground">Embedding</dt>
                <dd className="break-all font-mono text-xs">{config.data.embedding_model}</dd>
                <dt className="text-muted-foreground">Dimensions</dt>
                <dd className="font-mono text-xs">{config.data.embedding_dim}</dd>
                <dt className="text-muted-foreground">Reranker</dt>
                <dd className="font-mono text-xs">{config.data.reranker ?? "none"}</dd>
                <dt className="text-muted-foreground">Top K</dt>
                <dd className="font-mono text-xs">{config.data.top_k}</dd>
              </dl>
            </section>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
