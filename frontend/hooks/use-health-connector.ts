// frontend/hooks/use-health-connector.ts
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiFetch } from "@/lib/api";

export const HEALTH_CONNECT_URL = `${process.env.NEXT_PUBLIC_API_URL}/auth/health/connect`;

export function useHealthDisconnect() {
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function disconnect() {
    setIsPending(true);
    setError(null);
    try {
      await apiFetch("/auth/health/disconnect", { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Disconnect failed"));
    } finally {
      setIsPending(false);
    }
  }

  return { disconnect, isPending, error };
}

export function useHealthConnectErrorFromUrl(): boolean {
  const [hasError] = useState(() => {
    if (typeof window === "undefined") return false;
    const params = new URLSearchParams(window.location.search);
    return params.get("health_connect_error") === "1";
  });

  return hasError;
}
