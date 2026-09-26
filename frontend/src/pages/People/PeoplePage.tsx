// People page (/people and /people/:personId): the list of people on the left, the selected person on the right.
// On small screens only one of the two columns is shown at a time.
import { useParams } from "react-router";
import { Users } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { AliasSuggestionCard } from "@/features/people/AliasSuggestionCard";
import { PeopleList } from "@/features/people/PeopleList";
import { PersonDetailView } from "@/features/people/PersonDetailView";
import { cn } from "@/lib/cn";

export default function PeoplePage() {
  const { personId } = useParams();

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-8">
      <PageHeader title="People" description="Everyone in your memories, with aliases merged across sources." />
      <div className="mb-4">
        <AliasSuggestionCard />
      </div>
      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <Card
          className={cn(
            "flex flex-col p-3 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)]",
            personId && "hidden lg:flex",
          )}
        >
          <PeopleList />
        </Card>

        <div className={cn(!personId && "hidden lg:block")}>
          {personId ? (
            // key: start fresh (scroll, hover state) when switching to another person.
            <PersonDetailView key={personId} personId={personId} />
          ) : (
            <EmptyState icon={<Users />} title="Select a person" description="Pick someone to see your shared history." />
          )}
        </div>
      </div>
    </div>
  );
}
