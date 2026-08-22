"use client";

import { useQuery } from "@tanstack/react-query";

import { reverseGeocode } from "@/lib/geocoding-api";

export function useLocationName(lat: number | null | undefined, lon: number | null | undefined) {
  const { data } = useQuery({
    queryKey: ["location-name", lat, lon],
    queryFn: () => reverseGeocode(lat as number, lon as number),
    enabled: lat != null && lon != null,
    staleTime: Infinity,
  });

  return data ?? null;
}
