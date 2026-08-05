"use client";

import { useQuery } from "@tanstack/react-query";

import { getDashboard } from "@/lib/dashboard-api";

export function useDashboard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
  });

  return { dashboard: data, isLoading, isError };
}
