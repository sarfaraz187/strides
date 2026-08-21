import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";

import {
  useCalendarDisconnect,
  useCalendarConnectErrorFromUrl,
  CALENDAR_CONNECT_URL,
} from "@/hooks/use-calendar-connector";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useCalendarDisconnect", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "disconnected" }) });
  });

  it("posts to /auth/calendar/disconnect", async () => {
    const { result } = renderHook(() => useCalendarDisconnect(), { wrapper });

    await result.current.disconnect();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/auth/calendar/disconnect"),
        expect.objectContaining({ method: "POST", credentials: "include" })
      );
    });
  });
});

describe("useCalendarConnectErrorFromUrl", () => {
  it("returns true when the URL has calendar_connect_error=1", () => {
    window.history.pushState({}, "", "/?calendar_connect_error=1");
    const { result } = renderHook(() => useCalendarConnectErrorFromUrl());
    expect(result.current).toBe(true);
  });

  it("returns false otherwise", () => {
    window.history.pushState({}, "", "/");
    const { result } = renderHook(() => useCalendarConnectErrorFromUrl());
    expect(result.current).toBe(false);
  });
});

describe("CALENDAR_CONNECT_URL", () => {
  it("points at the backend calendar connect route", () => {
    expect(CALENDAR_CONNECT_URL).toContain("/auth/calendar/connect");
  });
});
