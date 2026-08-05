"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import { apiFetch } from "./api";

type User = { email: string; health_connected: boolean; created_at: string; name: string | null };
type AuthState = { user: User | null; isLoading: boolean };

export const AuthContext = createContext<AuthState>({ user: null, isLoading: true });

// NEXT_PUBLIC_MOCK_AUTH=true skips the real auth check, for local UI work without a backend running.
const MOCK_AUTH = process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
const MOCK_USER: User = { email: "dev@example.com", name: "Dev User", created_at: "", health_connected: false };

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
