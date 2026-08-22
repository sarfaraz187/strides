import { afterEach, describe, expect, it, vi } from "vitest";

import { reverseGeocode } from "../lib/geocoding-api";

describe("reverseGeocode", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the city name for a resolved coordinate", async () => {
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ city: "Hyderabad", locality: "Banjara Hills" }), { status: 200 })
    );

    const result = await reverseGeocode(17.38, 78.48);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=17.38&longitude=78.48")
    );
    expect(result).toBe("Hyderabad");
  });

  it("falls back to locality when city is empty", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ city: "", locality: "Banjara Hills" }), { status: 200 })
    );

    const result = await reverseGeocode(17.38, 78.48);

    expect(result).toBe("Banjara Hills");
  });

  it("returns null when the request fails", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("error", { status: 500 }));

    const result = await reverseGeocode(17.38, 78.48);

    expect(result).toBeNull();
  });
});
