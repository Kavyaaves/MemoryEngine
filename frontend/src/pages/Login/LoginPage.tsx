// Login / register page (the only page reachable without a token).
// Data flow: form → useLoginOrRegister (hooks/useAuth.ts) → POST /api/auth/login | /register
//            → token saved in authStore → this page re-renders and redirects to where the user was going.
import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router";
import { Brain } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Spinner } from "@/components/ui/Spinner";
import { useLoginOrRegister, type Credentials } from "@/hooks/useAuth";
import { useAuthStore } from "@/stores/authStore";
import { cn } from "@/lib/cn";

type Mode = Credentials["mode"];

export default function LoginPage() {
  const token = useAuthStore((state) => state.token);
  const location = useLocation();
  // RequireAuth stores the page the user originally asked for in the navigation state.
  const returnTo = (location.state as { from?: string } | null)?.from ?? "/ask";

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const authenticate = useLoginOrRegister();

  // Already signed in (or just signed in): go on to the app.
  if (token) return <Navigate to={returnTo} replace />;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    authenticate.mutate({ mode, email, password, displayName });
  };

  const switchMode = (nextMode: Mode) => {
    setMode(nextMode);
    authenticate.reset(); // clear an error from the other mode
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-[radial-gradient(ellipse_at_top,var(--color-accent),transparent_60%)] p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <div className="mb-2 flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Brain className="size-5" />
          </div>
          <CardTitle className="text-xl">Memory Engine</CardTitle>
          <CardDescription>
            {mode === "login" ? "Sign in to explore your memories" : "Create your private memory space"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-5 grid grid-cols-2 rounded-lg bg-muted p-1" role="group" aria-label="Sign in or register">
            {(["login", "register"] as const).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={mode === option}
                onClick={() => switchMode(option)}
                className={cn(
                  "cursor-pointer rounded-md py-1.5 text-sm font-medium transition-colors",
                  mode === option ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {option === "login" ? "Sign in" : "Register"}
              </button>
            ))}
          </div>

          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            {mode === "register" && (
              <div className="flex flex-col gap-2">
                <Label htmlFor="display_name">Display name (optional)</Label>
                <Input
                  id="display_name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  autoComplete="name"
                />
              </div>
            )}
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                required
                minLength={mode === "register" ? 8 : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </div>
            {authenticate.isError && (
              <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {authenticate.error.message}
              </p>
            )}
            <Button type="submit" disabled={authenticate.isPending} className="w-full">
              {authenticate.isPending && <Spinner />}
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
