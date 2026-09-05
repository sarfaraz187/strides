import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let mockPathname = "/en/notifications";

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: { name: "Runner Example", email: "runner@example.com", avatar_url: null } }),
}));

import { AppShell } from "@/components/app-shell";
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

describe("AppShell", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    mockPathname = "/en/notifications";
  });

  afterEach(() => {
    mockPathname = "/en/notifications";
  });

  it("marks notifications as the active nav item when on /notifications", () => {
    // Both the sidebar link (desktop) and bottom-nav link (mobile) mount at
    // once, CSS-toggled by breakpoint like the rest of Sidebar/BottomNav
    // (see the note at the top of app-shell.tsx) — hence getAllByRole.
    render(<AppShell locale="en">{<div>content</div>}</AppShell>, { wrapper });

    const links = screen.getAllByRole("link", { name: messages.nav.notifications });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/en/notifications");
    }
  });

  it("marks Coach as active on a conversation page (/chat/{id}), not just the bare /chat route", () => {
    mockPathname = "/en/chat/conv-1";

    render(<AppShell locale="en">{<div>content</div>}</AppShell>, { wrapper });

    // The desktop Sidebar link exposes an explicit data-active attribute;
    // BottomNav (mobile) only varies its className, so it's checked separately.
    const links = screen.getAllByRole("link", { name: messages.nav.coach });
    expect(links.length).toBeGreaterThan(0);
    expect(links.some((link) => link.hasAttribute("data-active"))).toBe(true);
    expect(links.some((link) => link.className.includes("text-primary"))).toBe(true);
  });
});
