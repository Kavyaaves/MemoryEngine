// People endpoints (docs/api-contract.md § People). Called from hooks/usePeople.ts.
import type { AliasFeedbackRequest, AliasSuggestion, OkResponse, Person, PersonDetail } from "@/types/api";
import { apiFetch } from "./client";

export function getPeople() {
  return apiFetch<Person[]>("/people");
}

export function getPerson(personId: string) {
  return apiFetch<PersonDetail>(`/people/${encodeURIComponent(personId)}`);
}

/** "Is alias X the same person as Y?" questions the backend is unsure about. */
export function getAliasSuggestions() {
  return apiFetch<AliasSuggestion[]>("/people/alias-suggestions");
}

export function sendAliasFeedback(body: AliasFeedbackRequest) {
  return apiFetch<OkResponse>("/people/alias-feedback", { method: "POST", json: body });
}
