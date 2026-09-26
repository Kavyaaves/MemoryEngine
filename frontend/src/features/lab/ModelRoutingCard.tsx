// AI Lab: for each task (e.g. "answer", "embed"), the chain of models tried in order until one succeeds.
// Data: useLabConfig → GET /api/lab/config (`routing`)
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useLabConfig } from "@/hooks/useLab";

export function ModelRoutingCard() {
  const config = useLabConfig();
  const routes = Object.entries(config.data?.routing ?? {});
  if (routes.length === 0) return null; // LabConfigCard already shows loading and error states

  return (
    <Card>
      <CardHeader>
        <CardTitle>Model routing</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="-mx-5 overflow-x-auto px-5">
          <table className="w-full min-w-[480px] text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="py-2 pr-3 font-medium">Task</th>
                <th className="py-2 font-medium">Fallback chain</th>
              </tr>
            </thead>
            <tbody>
              {routes.map(([task, modelChain]) => (
                <tr key={task} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-medium">{task}</td>
                  <td className="py-2">
                    <div className="flex flex-wrap items-center gap-1">
                      {modelChain.map((model, index) => (
                        <span key={`${model}-${index}`} className="flex items-center gap-1">
                          {index > 0 && <span className="text-muted-foreground">→</span>}
                          <Badge variant={index === 0 ? "info" : "secondary"} className="font-mono">
                            {model}
                          </Badge>
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
