// Light/dark theme preference, persisted in localStorage.
// index.html reads the same "pmme-theme" key before first paint (to avoid a flash);
// App.tsx calls applyTheme() whenever the preference changes.
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "dark" | "light";

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: "dark",
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set({ theme: get().theme === "dark" ? "light" : "dark" }),
    }),
    { name: "pmme-theme" },
  ),
);

/** Tailwind's `dark:` variants key off the `dark` class on <html> (see index.css). */
export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}
