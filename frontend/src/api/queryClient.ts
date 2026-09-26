// The app's single TanStack Query client: the in-memory cache of server data. Provided in main.tsx.
import { QueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/authStore";
import { ApiError } from "./errors";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // A 4xx will not fix itself by asking again; network errors and 5xx (e.g. 503 while the
        // database restarts) might, so retry those twice.
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return failureCount < 2;
      },
    },
  },
});

// Cached data belongs to the signed-in user: drop all of it whenever the session changes
// (logout button, a 401 handled in api/client.ts, or another tab signing in as someone else).
useAuthStore.subscribe((state, previousState) => {
  const sessionEndedOrChanged = previousState.token !== null && state.token !== previousState.token;
  if (sessionEndedOrChanged) queryClient.clear();
});
