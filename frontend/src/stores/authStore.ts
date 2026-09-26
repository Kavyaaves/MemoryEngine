// Who is signed in: the bearer token (persisted in localStorage) and the email used to sign in.
// api/client.ts reads the token for every request and calls logout() on a 401.
// Other modules react when the token changes (sign-in, logout) by subscribing to this store:
//   api/queryClient.ts clears the server-data cache, features/chat/chatStore.ts clears the conversation.
import { create } from "zustand";
import { persist } from "zustand/middleware";

const STORAGE_KEY = "pmme-auth";

interface AuthState {
  token: string | null;
  email: string | null;
  setSession: (token: string, email: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      email: null,
      setSession: (token, email) => set({ token, email }),
      logout: () => set({ token: null, email: null }),
    }),
    { name: STORAGE_KEY },
  ),
);

// Keep open tabs in sync: signing out (or in) in one tab updates the others.
window.addEventListener("storage", (event) => {
  if (event.key === STORAGE_KEY) void useAuthStore.persist.rehydrate();
});
