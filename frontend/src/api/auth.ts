// Auth endpoints (docs/api-contract.md § Auth). Called from hooks/useAuth.ts.
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "@/types/api";
import { apiFetch } from "./client";

export function login(body: LoginRequest) {
  return apiFetch<TokenResponse>("/auth/login", { method: "POST", json: body });
}

export function register(body: RegisterRequest) {
  return apiFetch<TokenResponse>("/auth/register", { method: "POST", json: body });
}

export function getMe() {
  return apiFetch<User>("/auth/me");
}
