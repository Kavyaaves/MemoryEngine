// "Sources" card: every imported export/file, with a delete button (which also deletes its memories).
// Data flow: SourcesList → useSources → GET /api/sources
//            Delete → useDeleteSource → DELETE /api/sources/{id} → refreshes timeline, people, search
import { useState } from "react";
import { Database, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SourceBadge } from "@/components/SourceBadge";
import { useDeleteSource, useSources } from "@/hooks/useUploads";
import type { Source } from "@/types/api";
import { formatDate, formatNumber, formatRelative } from "@/lib/format";

export function SourcesList() {
  const sources = useSources();
  const deleteSource = useDeleteSource();
  // The source waiting for confirmation in the dialog (null = dialog closed).
  const [sourceToDelete, setSourceToDelete] = useState<Source | null>(null);

  const askToDelete = (source: Source) => {
    deleteSource.reset(); // clear an error left over from a previous attempt
    setSourceToDelete(source);
  };

  const confirmDelete = () => {
    if (!sourceToDelete) return;
    deleteSource.mutate(sourceToDelete.id, { onSuccess: () => setSourceToDelete(null) });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sources</CardTitle>
      </CardHeader>
      <CardContent>
        {sources.isPending ? (
          <div className="flex flex-col gap-2">
            {[0, 1].map((index) => (
              <Skeleton key={index} className="h-10" />
            ))}
          </div>
        ) : sources.isError ? (
          <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />
        ) : sources.data.length === 0 ? (
          <EmptyState icon={<Database />} title="No sources" description="Uploaded exports show up here once processed." />
        ) : (
          <div className="-mx-5 overflow-x-auto px-5">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Type</th>
                  <th className="py-2 pr-3 text-right font-medium">Memories</th>
                  <th className="py-2 pr-3 font-medium">Added</th>
                  <th className="py-2 pr-3 font-medium">Last processed</th>
                  <th className="py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sources.data.map((source) => (
                  <tr key={source.id} className="border-b last:border-0">
                    <td className="max-w-[240px] truncate py-2 pr-3 font-medium" title={source.name}>
                      {source.name}
                    </td>
                    <td className="py-2 pr-3">
                      <SourceBadge type={source.source_type} />
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">{formatNumber(source.memory_count)}</td>
                    <td className="py-2 pr-3 text-muted-foreground">{formatDate(source.created_at)}</td>
                    <td className="py-2 pr-3 text-muted-foreground">{formatRelative(source.last_processed_at)}</td>
                    <td className="py-2 text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${source.name}`}
                        className="text-muted-foreground hover:text-destructive"
                        onClick={() => askToDelete(source)}
                      >
                        <Trash2 />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <ConfirmDialog
        open={sourceToDelete !== null}
        onOpenChange={(open) => {
          if (!open) setSourceToDelete(null);
        }}
        title="Delete source?"
        description={
          <>
            <span className="font-medium text-foreground">{sourceToDelete?.name}</span> and all{" "}
            {formatNumber(sourceToDelete?.memory_count ?? 0)} derived memories will be permanently removed.
            {deleteSource.isError && (
              <span role="alert" className="mt-2 block text-destructive">
                {deleteSource.error.message}
              </span>
            )}
          </>
        }
        confirmLabel="Delete"
        destructive
        pending={deleteSource.isPending}
        onConfirm={confirmDelete}
      />
    </Card>
  );
}
