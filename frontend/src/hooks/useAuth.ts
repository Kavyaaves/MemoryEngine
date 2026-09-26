// Auth hooks.
//   LoginPage → useLoginOrRegister → api/auth.ts → POST /api/auth/login | /register → token saved in authStore
//   Layout, SettingsPage → useMe → GET /api/auth/me
import { useMutation, useQuery } from "@tanstack/react-query";
import { getMe, login, register } from "@/api/auth";
import { queryKeys } from "@/api/queryKeys";
import { useAuthStore } from "@/stores/authStore";

export function useMe() {
  const token = useAuthStore((state) => state.token);
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: getMe,
    enabled: token !== null,
    staleTime: 5 * 60_000,
  });
}

export interface Credentials {
  mode: "login" | "register";
  email: string;
  password: string;
  /** Only used when registering. */
  displayName: string;
}

export function useLoginOrRegister() {
  const setSession = useAuthStore((state) => state.setSession);
  return useMutation({
    mutationFn: (credentials: Credentials) =>
      credentials.mode === "login"
        ? login({ email: credentials.email, password: credentials.password })
        : register({
            email: credentials.email,
            password: credentials.password,
            display_name: credentials.displayName.trim() || undefined,
          }),
    onSuccess: (response, credentials) => setSession(response.access_token, credentials.email),
  });
}
