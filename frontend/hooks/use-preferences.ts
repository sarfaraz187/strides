"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";

import { getPreferences, Preferences, updatePreferences } from "@/lib/preferences-api";

const GOAL_DEBOUNCE_MS = 500;

export const DEFAULT_PREFERENCES: Preferences = {
  weekly_goal_km: 30,
  units: "km",
  notifications_enabled: true,
  language: "en",
  location_lat: null,
  location_lon: null,
};

export function usePreferences() {
  const queryClient = useQueryClient();
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["preferences"],
    queryFn: getPreferences,
  });

  // GET failure: fall back to the same defaults the backend uses for a
  // user with no row yet, so the UI still renders sensible values.
  const preferences = data ?? (isLoading ? undefined : isError ? DEFAULT_PREFERENCES : undefined);

  const mutation = useMutation({
    mutationFn: updatePreferences,
    onSuccess: (updated) => {
      queryClient.setQueryData(["preferences"], updated);
    },
  });

  function updateNow(partial: Partial<Preferences>) {
    mutation.mutate(partial);
  }

  function updateDebounced(partial: Partial<Preferences>) {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      mutation.mutate(partial);
    }, GOAL_DEBOUNCE_MS);
  }

  return {
    preferences,
    isLoading,
    updateNow,
    updateDebounced,
    error: mutation.error,
  };
}
