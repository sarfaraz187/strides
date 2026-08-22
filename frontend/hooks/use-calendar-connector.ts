// frontend/hooks/use-calendar-connector.ts
"use client";

import { useConnectErrorFromUrl, useConnectorDisconnect } from "@/hooks/use-connector";

export const CALENDAR_CONNECT_URL = `${process.env.NEXT_PUBLIC_API_URL}/auth/calendar/connect`;

export function useCalendarDisconnect() {
  return useConnectorDisconnect("/auth/calendar/disconnect");
}

export function useCalendarConnectErrorFromUrl(): boolean {
  return useConnectErrorFromUrl("calendar_connect_error");
}
