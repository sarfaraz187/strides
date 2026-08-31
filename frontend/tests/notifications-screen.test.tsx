import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NotificationsScreen } from "@/components/notifications-screen";
import messages from "@/messages/en.json";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={messages}>
        {children}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

describe("NotificationsScreen", () => {
  it("shows the empty state when there are no notifications", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });

    render(<NotificationsScreen locale="en" />, { wrapper });

    await waitFor(() => expect(screen.getByText("You're all caught up.")).toBeInTheDocument());
  });

  it("translates each notification's type to display text and links via action_href", async () => {
    global.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (options?.method === "PATCH") return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
      return Promise.resolve({
        ok: true,
        json: async () => [
          { id: 1, user_id: "u1", type: "health_reauth_required", action_href: "/connectors", status: "unread", created_at: "2026-08-31T00:00:00Z" },
        ],
      });
    });

    render(<NotificationsScreen locale="en" />, { wrapper });

    const text = await screen.findByText("Your Google Health connection expired. Please reconnect.");
    expect(text.closest("a")).toHaveAttribute("href", "/en/connectors");
  });

  it("marks all as read once, on mount", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (options?.method === "PATCH") return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
      return Promise.resolve({ ok: true, json: async () => [] });
    });
    global.fetch = fetchMock;

    render(<NotificationsScreen locale="en" />, { wrapper });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/read-all"),
        expect.objectContaining({ method: "PATCH" })
      );
    });
  });
});
