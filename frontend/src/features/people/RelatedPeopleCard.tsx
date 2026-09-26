import { Link } from "react-router";
import { Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/EmptyState";
import { RelatedPeopleGraph } from "@/features/graph/RelatedPeopleGraph";
import type { RelatedPerson } from "@/types/api";

/** People who often appear together with this person: a graph plus a list of links. */
export function RelatedPeopleCard({ personName, related }: { personName: string; related: RelatedPerson[] }) {
  const strongestFirst = [...related].sort((a, b) => b.weight - a.weight);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="size-4" aria-hidden /> Related people
        </CardTitle>
      </CardHeader>
      <CardContent>
        {strongestFirst.length === 0 ? (
          <EmptyState title="No related people yet" className="py-6" />
        ) : (
          <>
            <RelatedPeopleGraph centerName={personName} related={strongestFirst} />
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {strongestFirst.map((person) => (
                <li key={person.id}>
                  <Link
                    to={`/people/${person.id}`}
                    className="memory-text inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs hover:bg-accent"
                  >
                    {person.display_name}
                    <span className="text-muted-foreground">{person.weight.toFixed(2)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
