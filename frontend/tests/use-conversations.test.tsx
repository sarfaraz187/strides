import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useConversations } from "../hooks/use-conversations";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useConversations", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("splits conversations into pinned and recent", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([
        { id: "1", title: "Pinned chat", pinned: true, created_at: "t", updated_at: "t" },
        { id: "2", title: "Recent chat", pinned: false, created_at: "t", updated_at: "t" },
      ])
    );

    const { result } = renderHook(() => useConversations(""), { wrapper });

    await waitFor(() => expect(result.current.conversations).toHaveLength(2));
    expect(result.current.pinned.map((c) => c.id)).toEqual(["1"]);
    expect(result.current.recent.map((c) => c.id)).toEqual(["2"]);
  });

  it("rename calls the mutation and refetches the list", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse([]));

    const { result } = renderHook(() => useConversations(""), { wrapper });
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());

    result.current.rename({ id: "1", title: "New title" });

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "https://api.example.com/conversations/1",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ title: "New title" }) })
      )
    );
  });
});