import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { useHealthDisconnect, useHealthConnectErrorFromUrl, HEALTH_CONNECT_URL } from "@/hooks/use-health-connector";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useHealthDisconnect", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "disconnected" }) });
  });

  it("posts to /auth/health/disconnect", async () => {
    const { result } = renderHook(() => useHealthDisconnect(), { wrapper });

    await result.current.disconnect();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/auth/health/disconnect"),
        expect.objectContaining({ method: "POST", credentials: "include" })
      );
    });
  });
});

describe("useHealthConnectErrorFromUrl", () => {
  it("returns true when the URL has health_connect_error=1", () => {
    window.history.pushState({}, "", "/?health_connect_error=1");
    const { result } = renderHook(() => useHealthConnectErrorFromUrl());
    expect(result.current).toBe(true);
  });

  it("returns false otherwise", () => {
    window.history.pushState({}, "", "/");
    const { result } = renderHook(() => useHealthConnectErrorFromUrl());
    expect(result.current).toBe(false);
  });
});

describe("HEALTH_CONNECT_URL", () => {
  it("points at the backend health connect route", () => {
    expect(HEALTH_CONNECT_URL).toContain("/auth/health/connect");
  });
});
