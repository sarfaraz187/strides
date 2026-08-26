// frontend/hooks/use-connector.ts
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiFetch } from "@/lib/api";

export function useConnectorDisconnect(disconnectPath: string) {
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function disconnect() {
    setIsPending(true);
    setError(null);
    try {
      await apiFetch(disconnectPath, { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Disconnect failed"));
    } finally {
      setIsPending(false);
    }
  }

  return { disconnect, isPending, error };
}

export function useConnectErrorFromUrl(paramName: string): boolean {
  const [hasError] = useState(() => {
    if (typeof window === "undefined") return false;
    const params = new URLSearchParams(window.location.search);
    return params.get(paramName) === "1";
  });

  return hasError;
}
