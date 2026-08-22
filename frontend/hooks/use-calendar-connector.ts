// frontend/hooks/use-calendar-connector.ts
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiFetch } from "@/lib/api";

export const CALENDAR_CONNECT_URL = `${process.env.NEXT_PUBLIC_API_URL}/auth/calendar/connect`;

export function useCalendarDisconnect() {
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function disconnect() {
    setIsPending(true);
    setError(null);
    try {
      await apiFetch("/auth/calendar/disconnect", { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Disconnect failed"));
    } finally {
      setIsPending(false);
    }
  }

  return { disconnect, isPending, error };
}

export function useCalendarConnectErrorFromUrl(): boolean {
  const [hasError] = useState(() => {
    if (typeof window === "undefined") return false;
    const params = new URLSearchParams(window.location.search);
    return params.get("calendar_connect_error") === "1";
  });

  return hasError;
}
