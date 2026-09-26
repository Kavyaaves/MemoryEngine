// The app shell around every signed-in page: sidebar (desktop) or top bar (mobile) plus the page itself.
// App.tsx renders the current page into <Outlet />.
import { Suspense } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import {
  Brain,
  FlaskConical,
  Images,
  LogOut,
  MessageSquareText,
  Moon,
  Orbit,
  Settings,
  Sun,
  Upload,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { useMe } from "@/hooks/useAuth";
import { useAuthStore } from "@/stores/authStore";
import { useThemeStore } from "@/stores/themeStore";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { to: "/ask", label: "Ask", icon: MessageSquareText },
  { to: "/upload", label: "Upload", icon: Upload },
  { to: "/life", label: "Life", icon: Orbit },
  { to: "/people", label: "People", icon: Users },
  { to: "/media", label: "Media", icon: Images },
  { to: "/lab", label: "AI Lab", icon: FlaskConical },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Layout() {
  const location = useLocation();
  const logout = useAuthStore((state) => state.logout);
  const signedInEmail = useAuthStore((state) => state.email);
  const me = useMe();
  const userLabel = me.data?.display_name || me.data?.email || signedInEmail;

  return (
    <div className="flex min-h-full flex-col md:flex-row">
      {/* Sidebar (desktop) */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-card/40 md:flex">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Brain className="size-4" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">Memory Engine</div>
            <div className="text-xs text-muted-foreground">personal · multimodal</div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 px-3" aria-label="Main">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t p-3">
          {userLabel && (
            <div className="truncate px-2 pb-2 text-xs text-muted-foreground" title={userLabel}>
              {userLabel}
            </div>
          )}
          <div className="flex gap-1">
            <ThemeToggleButton />
            <Button variant="ghost" className="flex-1 justify-start" onClick={logout}>
              <LogOut /> Log out
            </Button>
          </div>
        </div>
      </aside>

      {/* Top bar (mobile) */}
      <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur md:hidden">
        <div className="flex items-center justify-between px-4 py-2">
          <div className="flex items-center gap-2 font-semibold">
            <Brain className="size-5 text-primary" /> Memory Engine
          </div>
          <div className="flex">
            <ThemeToggleButton />
            <Button variant="ghost" size="icon" onClick={logout} aria-label="Log out">
              <LogOut />
            </Button>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2" aria-label="Main">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium",
                  isActive ? "bg-primary/15 text-primary" : "text-muted-foreground",
                )
              }
            >
              <Icon className="size-3.5" />
              {label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="min-w-0 flex-1">
        {/* A crash in one page shows an error there but keeps the navigation usable;
            navigating to another URL clears it. */}
        <ErrorBoundary
          resetKey={location.pathname}
          fallback={(error, reset) => (
            <div className="p-4 md:p-8">
              <ErrorState error={error} title="This page crashed" onRetry={reset} />
            </div>
          )}
        >
          {/* Pages are lazy-loaded (see App.tsx); this shows while a page's code downloads. */}
          <Suspense fallback={<LoadingState />}>
            <Outlet />
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  );
}

function ThemeToggleButton() {
  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  return (
    <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
      {theme === "dark" ? <Sun /> : <Moon />}
    </Button>
  );
}
