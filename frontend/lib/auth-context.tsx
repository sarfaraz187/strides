"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import { apiFetch } from "./api";

type User = { email: string };
type AuthState = { user: User | null; isLoading: boolean };

const AuthContext = createContext<AuthState>({ user: null, isLoading: true });

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
  });

  return (
    <AuthContext.Provider value={{ user: data ?? null, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
