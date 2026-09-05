import { afterEach, describe, expect, it, vi } from "vitest";

import {
  deleteConversation,
  getConversationMessages,
  listConversations,
  updateConversation,
} from "../lib/conversations-api";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}

describe("conversations-api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("listConversations calls /conversations without a search param when omitted", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse([]));

    await listConversations();

    expect(mockFetch).toHaveBeenCalledWith("https://api.example.com/conversations", expect.anything());
  });

  it("listConversations includes an encoded search param when given", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse([]));

    await listConversations("shin pain");

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/conversations?search=shin%20pain",
      expect.anything()
    );
  });

  it("updateConversation PATCHes the given fields", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ status: "ok" }));

    await updateConversation("conv-1", { title: "Renamed" });

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/conversations/conv-1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ title: "Renamed" }) })
    );
  });

  it("deleteConversation DELETEs the conversation", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ status: "ok" }));

    await deleteConversation("conv-1");

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/conversations/conv-1",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("getConversationMessages includes limit and before_id", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ messages: [], has_more: false }));

    await getConversationMessages("conv-1", 5, 20);

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/conversations/conv-1/messages?limit=20&before_id=5",
      expect.anything()
    );
  });
});