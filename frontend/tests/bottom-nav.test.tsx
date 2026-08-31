import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ user: { name: "Runner Example", email: "runner@example.com", avatar_url: null } }),
}));

import en from "../messages/en.json";
import { BottomNav } from "../components/bottom-nav";

function renderBottomNav() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={en}>
        <BottomNav active="dashboard" locale="en" />
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

describe("BottomNav", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  });

  it("links to dashboard and chat for the given locale", () => {
    renderBottomNav();

    expect(screen.getByRole("link", { name: en.nav.dashboard })).toHaveAttribute(
      "href",
      "/en/dashboard"
    );
    expect(screen.getByRole("link", { name: en.nav.coach })).toHaveAttribute(
      "href",
      "/en/chat"
    );
  });

  it("links to a dedicated notifications page", () => {
    renderBottomNav();

    expect(screen.getByRole("link", { name: en.nav.notifications })).toHaveAttribute(
      "href",
      "/en/notifications"
    );
  });

  it("links to profile", () => {
    renderBottomNav();

    // Regex, not exact string: the link's accessible name also includes the
    // avatar's initials ("RE"), since Avatar renders those as sibling text.
    expect(screen.getByRole("link", { name: new RegExp(en.nav.profile) })).toHaveAttribute(
      "href",
      "/en/profile"
    );
  });
});
