import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";

describe("apiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("sends credentials include and returns parsed JSON", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200 })
      );

    const result = await apiFetch<{ ok: boolean }>("/chat");

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/chat",
      expect.objectContaining({ credentials: "include" })
    );
    expect(result).toEqual({ ok: true });
  });

  it("throws on a non-2xx response", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response("Unauthorized", { status: 401 })
    );

    await expect(apiFetch("/chat")).rejects.toThrow("401");
  });
});
