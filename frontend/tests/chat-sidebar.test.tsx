import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import en from "../messages/en.json";
import { ChatSidebar } from "../components/chat-sidebar";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={en}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}

describe("ChatSidebar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    replaceMock.mockClear();
  });

  it("renders pinned and recent sections separately", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([
        { id: "1", title: "Weather & last run", pinned: true, created_at: "t", updated_at: "2026-09-01T13:04:00Z" },
        { id: "2", title: "Shin pain advice", pinned: false, created_at: "t", updated_at: "2026-08-20T18:45:00Z" },
      ])
    );

    renderWithProviders(<ChatSidebar locale="en" />);

    await waitFor(() => expect(screen.getByText("Weather & last run")).toBeInTheDocument());
    expect(screen.getByText(en.chat.pinnedSection)).toBeInTheDocument();
    expect(screen.getByText("Shin pain advice")).toBeInTheDocument();
    expect(screen.getByText(en.chat.recentSection)).toBeInTheDocument();
  });

  it("filters the list as the user types in search", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse([]));

    renderWithProviders(<ChatSidebar locale="en" />);

    const search = screen.getByPlaceholderText(en.chat.searchPlaceholder);
    fireEvent.change(search, { target: { value: "shin" } });

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/conversations?search=shin"),
        expect.anything()
      )
    );
  });

  it("deleting a conversation calls the DELETE endpoint", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([{ id: "1", title: "Old chat", pinned: false, created_at: "t", updated_at: "t" }])
    );

    renderWithProviders(<ChatSidebar locale="en" />);

    await waitFor(() => expect(screen.getByText("Old chat")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("delete"));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "https://api.example.com/conversations/1",
        expect.objectContaining({ method: "DELETE" })
      )
    );
  });

  it("deleting the active conversation redirects to the empty new-chat state", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([{ id: "1", title: "Active chat", pinned: false, created_at: "t", updated_at: "t" }])
    );

    renderWithProviders(<ChatSidebar locale="en" activeConversationId="1" />);

    await waitFor(() => expect(screen.getByText("Active chat")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("delete"));

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/en/chat"));
  });

  it("deleting a non-active conversation does not redirect", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([{ id: "1", title: "Other chat", pinned: false, created_at: "t", updated_at: "t" }])
    );

    renderWithProviders(<ChatSidebar locale="en" activeConversationId="2" />);

    await waitFor(() => expect(screen.getByText("Other chat")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("delete"));

    await waitFor(() => expect(replaceMock).not.toHaveBeenCalled());
  });
});