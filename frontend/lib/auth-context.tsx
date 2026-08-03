"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import { apiFetch } from "./api";

type User = { email: string };
type AuthState = { user: User | null; isLoading: boolean };

const AuthContext = createContext<AuthState>({ user: null, isLoading: true });

// Dev-only bypass: /auth/me isn't implemented on the backend yet (see
// CLAUDE.md), so there's no way to reach the authenticated UI locally
// without this. Set NEXT_PUBLIC_MOCK_AUTH=true in .env.local to skip the
// real auth check. Remove once /auth/me exists.
const MOCK_AUTH = process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
const MOCK_USER: User = { email: "dev@example.com" };

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useQuery<User | null>({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      try {
        return await apiFetch<User>("/auth/me");
      } catch {
        return null;
      }
    },
    enabled: !MOCK_AUTH,
  });

  const value = MOCK_AUTH ? { user: MOCK_USER, isLoading: false } : { user: data ?? null, isLoading };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
