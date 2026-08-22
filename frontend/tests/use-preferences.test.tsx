import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { usePreferences } from "@/hooks/use-preferences";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("usePreferences", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("loads preferences via GET on mount", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          weekly_goal_km: 30,
          units: "km",
          notifications_enabled: true,
          language: "en",
        }),
        { status: 200 }
      )
    );

    const { result } = renderHook(() => usePreferences(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.preferences?.language).toBe("en");
  });

  it("falls back to default preferences when the GET fails", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("Server error", { status: 500 }));

    const { result } = renderHook(() => usePreferences(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.preferences).toEqual({
      weekly_goal_km: 30,
      units: "km",
      notifications_enabled: true,
      language: "en",
      location_lat: null,
      location_lon: null,
    });
  });

  it("updateNow fires a PUT immediately", async () => {
    const mockFetch = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            weekly_goal_km: 30,
            units: "km",
            notifications_enabled: true,
            language: "de",
          }),
          { status: 200 }
        )
      );

    const { result } = renderHook(() => usePreferences(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => {
      result.current.updateNow({ language: "de" });
    });

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/preferences"),
        expect.objectContaining({ method: "PUT" })
      )
    );
  });

  it("updateDebounced collapses rapid calls into a single PUT after 500ms", async () => {
    vi.useFakeTimers();
    const mockFetch = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            weekly_goal_km: 40,
            units: "km",
            notifications_enabled: true,
            language: "en",
          }),
          { status: 200 }
        )
      );

    const { result } = renderHook(() => usePreferences(), { wrapper });

    act(() => {
      result.current.updateDebounced({ weekly_goal_km: 35 });
      result.current.updateDebounced({ weekly_goal_km: 40 });
      result.current.updateDebounced({ weekly_goal_km: 45 });
    });

    const putCallsBefore = mockFetch.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method === "PUT"
    );
    expect(putCallsBefore).toHaveLength(0);

    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    const putCallsAfter = mockFetch.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method === "PUT"
    );
    expect(putCallsAfter).toHaveLength(1);
    expect(JSON.parse((putCallsAfter[0][1] as RequestInit).body as string)).toEqual({
      weekly_goal_km: 45,
    });
  });
});
