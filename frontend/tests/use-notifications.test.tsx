import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { useNotifications } from "@/hooks/use-notifications";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useNotifications", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (options?.method === "PATCH") {
        return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [
          { id: 1, user_id: "u1", type: "health_reauth_required", action_href: "/connectors", status: "unread", created_at: "2026-08-31T00:00:00Z" },
          { id: 2, user_id: "u1", type: "calendar_reauth_required", action_href: "/connectors", status: "read", created_at: "2026-08-30T00:00:00Z" },
        ],
      });
    });
  });

  it("computes unreadCount from the fetched list", async () => {
    const { result } = renderHook(() => useNotifications(), { wrapper });

    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    expect(result.current.unreadCount).toBe(1);
  });

  it("markAllRead posts to /notifications/read-all", async () => {
    const { result } = renderHook(() => useNotifications(), { wrapper });
    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    result.current.markAllRead();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/read-all"),
        expect.objectContaining({ method: "PATCH", credentials: "include" })
      );
    });
  });
});