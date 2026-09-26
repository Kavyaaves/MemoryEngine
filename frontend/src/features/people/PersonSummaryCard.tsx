import { Badge } from "@/components/ui/Badge";
import { Card, CardContent } from "@/components/ui/Card";
import type { Person } from "@/types/api";
import { formatDate, formatNumber, initialOf } from "@/lib/format";

/** Name, aliases and headline numbers for one person. */
export function PersonSummaryCard({ person }: { person: Person }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
        <div
          className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xl font-semibold text-primary"
          aria-hidden
        >
          {initialOf(person.display_name)}
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="memory-text text-xl font-semibold">{person.display_name}</h2>
          {person.aliases.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {person.aliases.map((alias) => (
                <Badge key={alias} variant="secondary" className="memory-text">
                  {alias}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <dl className="grid grid-cols-3 gap-4 text-sm sm:text-right">
          <div>
            <dt className="text-xs text-muted-foreground">Memories</dt>
            <dd className="font-semibold tabular-nums">{formatNumber(person.memory_count)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">First seen</dt>
            <dd className="font-medium">{formatDate(person.first_seen)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Last seen</dt>
            <dd className="font-medium">{formatDate(person.last_seen)}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
