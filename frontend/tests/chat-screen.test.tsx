import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import en from "../messages/en.json";
import { ChatScreen } from "../components/chat-screen";

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

describe("ChatScreen", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the typed message with the current locale and shows the reply", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    const mockFetch = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ reply: "8km easy Saturday." }), { status: 200 })
      );

    renderWithProviders(<ChatScreen locale="en" />);

    const input = screen.getByPlaceholderText(en.chat.placeholder);
    fireEvent.change(input, { target: { value: "what should I do saturday?" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByText("8km easy Saturday.")).toBeInTheDocument());

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/chat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ message: "what should I do saturday?", locale: "en" }),
      })
    );
  });
});
