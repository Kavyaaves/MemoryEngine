// Right column of the People page: everything about one person (PLAN §29).
// People page → usePerson → api/people.ts → GET /api/people/{id}
import { Link } from "react-router";
import { ArrowLeft, CalendarClock, Smile } from "lucide-react";
import { buttonVariants } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ErrorState";
import { MoodChart } from "@/features/sentiment/MoodChart";
import { usePerson } from "@/hooks/usePeople";
import { PersonActivityChart } from "./PersonActivityChart";
import { PersonConversationsCard } from "./PersonConversationsCard";
import { PersonSummaryCard } from "./PersonSummaryCard";
import { RelatedPeopleCard } from "./RelatedPeopleCard";

export function PersonDetailView({ personId }: { personId: string }) {
  const person = usePerson(personId);

  if (person.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    );
  }
  if (person.isError) return <ErrorState error={person.error} onRetry={() => void person.refetch()} />;

  const detail = person.data;
  return (
    <div className="flex flex-col gap-4">
      {/* On small screens the list is hidden while a person is open, so offer a way back. */}
      <Link to="/people" className={buttonVariants({ variant: "ghost", size: "sm", className: "w-fit lg:hidden" })}>
        <ArrowLeft /> All people
      </Link>
      <PersonSummaryCard person={detail} />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock className="size-4" aria-hidden /> Timeline
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PersonActivityChart activity={detail.timeline} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Smile className="size-4" aria-hidden /> Mood of your chats with {detail.display_name}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <MoodChart personId={personId} />
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-2">
        <PersonConversationsCard conversations={detail.conversations} />
        <RelatedPeopleCard personName={detail.display_name} related={detail.related_people} />
      </div>
    </div>
  );
}
