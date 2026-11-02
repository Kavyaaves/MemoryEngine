# 0012. People are only merged automatically when the names are identical

- **Status:** Accepted

## Context

One person shows up under many names: "Rahul", "rahul", "Rahul ❤️", "R", "Rahu". Merging two
different people is much worse than leaving one person split in two, because every answer about
either of them becomes wrong, and it is hard to notice.

## Decision

- Names are normalised first: NFKC, lower-case, emoji and symbols dropped, letters of every script
  kept (including Tamil vowel signs). "Rahul ❤️" becomes "rahul".
- **Only identical normalised names are merged without asking.**
- Weaker matches (similarity ≥ 0.72, such as a bare initial or a shortened name) become suggestions
  on the People page: "Is R Rahul? Yes / No / Not sure". A "yes" merges the two people.

## Consequences

- No silent wrong merges. The user may have to answer a few questions after a big import.
- The answers are labelled data for later fine-tuning of entity resolution (PLAN.md §20 C, §35).

## Where in the code

`backend/app/people/aliases.py` (pure functions), `people/resolver.py`, `api/people.py`,
`frontend/src/features/people/AliasSuggestionCard.tsx`. PLAN.md §13.
