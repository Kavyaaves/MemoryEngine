// Left column of the People page: everyone found in your memories, filterable by name or alias.
// People page → usePeople → api/people.ts → GET /api/people
import { useState } from "react";
import { NavLink } from "react-router";
import { Search, Users } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { usePeople } from "@/hooks/usePeople";
import type { Person } from "@/types/api";
import { cn } from "@/lib/cn";
import { formatDate, formatNumber, initialOf } from "@/lib/format";

function matchesSearch(person: Person, search: string): boolean {
  const needle = search.toLocaleLowerCase();
  return (
    person.display_name.toLocaleLowerCase().includes(needle) ||
    person.aliases.some((alias) => alias.toLocaleLowerCase().includes(needle))
  );
}

export function PeopleList() {
  const people = usePeople();
  const [search, setSearch] = useState("");
  const trimmedSearch = search.trim();

  const visiblePeople = [...(people.data ?? [])]
    .sort((a, b) => b.memory_count - a.memory_count)
    .filter((person) => !trimmedSearch || matchesSearch(person, trimmedSearch));

  return (
    <>
      <div className="relative mb-3">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search names or aliases"
          className="memory-text pl-8"
          aria-label="Search people"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {people.isPending ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2, 3, 4].map((index) => (
              <Skeleton key={index} className="h-12" />
            ))}
          </div>
        ) : people.isError ? (
          <ErrorState error={people.error} onRetry={() => void people.refetch()} />
        ) : visiblePeople.length === 0 ? (
          <EmptyState
            icon={<Users />}
            title={trimmedSearch ? "No matches" : "No people yet"}
            description={trimmedSearch ? undefined : "People are extracted from your chats as they're ingested."}
            className="py-6"
          />
        ) : (
          <ul className="flex flex-col gap-0.5">
            {visiblePeople.map((person) => (
              <li key={person.id}>
                <NavLink
                  to={`/people/${person.id}`}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors",
                      isActive ? "bg-primary/15" : "hover:bg-accent",
                    )
                  }
                >
                  <span
                    className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold"
                    aria-hidden
                  >
                    {initialOf(person.display_name)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="memory-text block truncate font-medium leading-snug">{person.display_name}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {person.aliases.length > 0
                        ? `aka ${person.aliases.slice(0, 2).join(", ")}`
                        : `last seen ${formatDate(person.last_seen)}`}
                    </span>
                  </span>
                  <span className="text-xs tabular-nums text-muted-foreground">{formatNumber(person.memory_count)}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
