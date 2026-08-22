// frontend/hooks/use-health-connector.ts
"use client";

import { useConnectErrorFromUrl, useConnectorDisconnect } from "@/hooks/use-connector";

export const HEALTH_CONNECT_URL = `${process.env.NEXT_PUBLIC_API_URL}/auth/health/connect`;

export function useHealthDisconnect() {
  return useConnectorDisconnect("/auth/health/disconnect");
}

export function useHealthConnectErrorFromUrl(): boolean {
  return useConnectErrorFromUrl("health_connect_error");
}
