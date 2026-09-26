// Settings page: account, theme, and which backend this app talks to (with a live health check).
// Data: useMe → GET /api/auth/me, useHealth → GET /api/health
import { CheckCircle2, LogOut, Moon, Sun, XCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { API_BASE } from "@/api/client";
import { useMe } from "@/hooks/useAuth";
import { useHealth } from "@/hooks/useHealth";
import { useAuthStore } from "@/stores/authStore";
import { useThemeStore } from "@/stores/themeStore";
import { formatDate } from "@/lib/format";

export default function SettingsPage() {
  const logout = useAuthStore((state) => state.logout);
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const me = useMe();
  const health = useHealth();
  // API_BASE is "/api" when the backend is same-origin; show the full URL for clarity.
  const apiUrl = API_BASE.startsWith("/") ? `${window.location.origin}${API_BASE}` : API_BASE;

  return (
    <div className="mx-auto max-w-3xl p-4 md:p-8">
      <PageHeader title="Settings" />
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Account</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            {me.isPending ? (
              <Skeleton className="h-10 w-48" />
            ) : me.isError ? (
              <p className="text-sm text-destructive">Couldn't load profile: {me.error.message}</p>
            ) : (
              <div className="text-sm">
                <div className="font-medium">{me.data.display_name || me.data.email}</div>
                <div className="text-muted-foreground">
                  {me.data.email} · joined {formatDate(me.data.created_at)}
                </div>
              </div>
            )}
            <Button variant="outline" onClick={logout}>
              <LogOut /> Log out
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Appearance</CardTitle>
          </CardHeader>
          <CardContent className="flex gap-2">
            <Button
              variant={theme === "dark" ? "default" : "outline"}
              aria-pressed={theme === "dark"}
              onClick={() => setTheme("dark")}
            >
              <Moon /> Dark
            </Button>
            <Button
              variant={theme === "light" ? "default" : "outline"}
              aria-pressed={theme === "light"}
              onClick={() => setTheme("light")}
            >
              <Sun /> Light
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Backend</CardTitle>
            <CardDescription>
              Configured at build time via <code className="font-mono">VITE_API_URL</code>. AI provider keys live only on
              the server — never in this app.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <div>
              <div className="text-xs text-muted-foreground">API base</div>
              <code className="break-all font-mono">{apiUrl}</code>
            </div>
            {health.isPending ? (
              <Skeleton className="h-12 w-40" />
            ) : health.isError ? (
              <ErrorState error={health.error} title="Health check failed" onRetry={() => void health.refetch()} />
            ) : (
              <div className="flex flex-wrap gap-4">
                <StatusRow label={`API: ${health.data.status}`} ok={health.data.status === "ok"} />
                <StatusRow label="Database" ok={health.data.db} />
                <StatusRow label="Redis" ok={health.data.redis} />
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StatusRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2">
      {ok ? (
        <CheckCircle2 className="size-4 text-success" aria-hidden />
      ) : (
        <XCircle className="size-4 text-destructive" aria-hidden />
      )}
      <span>
        {label}
        <span className="sr-only">{ok ? " — OK" : " — not OK"}</span>
      </span>
    </div>
  );
}
