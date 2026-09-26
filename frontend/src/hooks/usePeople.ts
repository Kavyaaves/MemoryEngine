// People hooks used by the People page (pages/People, features/people) → api/people.ts.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAliasSuggestions, getPeople, getPerson, sendAliasFeedback } from "@/api/people";
import { invalidateMemoryData, queryKeys } from "@/api/queryKeys";

export function usePeople() {
  return useQuery({ queryKey: queryKeys.people.list, queryFn: getPeople });
}

export function usePerson(personId: string) {
  return useQuery({ queryKey: queryKeys.people.detail(personId), queryFn: () => getPerson(personId) });
}

export function useAliasSuggestions() {
  return useQuery({ queryKey: queryKeys.people.aliasSuggestions, queryFn: getAliasSuggestions });
}

export function useAliasFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: sendAliasFeedback,
    onSuccess: (_response, feedback) => {
      if (feedback.answer === "yes") {
        // The alias was merged into the person: names in people, timeline and search results can change.
        invalidateMemoryData(queryClient);
      } else {
        void queryClient.invalidateQueries({ queryKey: queryKeys.people.aliasSuggestions });
      }
    },
  });
}
