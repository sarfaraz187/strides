import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "../messages/en.json";
import { Sidebar } from "../components/sidebar";
import { SidebarProvider } from "../components/ui/sidebar";
import { AuthContext } from "../lib/auth-context";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

function renderWithUser(name: string | null, ui: React.ReactElement) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider
        value={{
          user: {
            email: "runner@example.com",
            name,
            created_at: "",
            health_connected: false,
            calendar_connected: false,
            avatar_url: null,
          },
          isLoading: false,
        }}
      >
        <NextIntlClientProvider locale="en" messages={en}>
          <SidebarProvider>{ui}</SidebarProvider>
        </NextIntlClientProvider>
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}

function renderPlain(ui: React.ReactElement, { defaultOpen = true }: { defaultOpen?: boolean } = {}) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={en}>
        <SidebarProvider defaultOpen={defaultOpen}>{ui}</SidebarProvider>
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

describe("Sidebar", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  });

  it("links to dashboard and chat for the given locale", () => {
    renderPlain(<Sidebar active="dashboard" locale="en" />);

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
    renderPlain(<Sidebar active="dashboard" locale="en" />);

    expect(screen.getByRole("link", { name: en.nav.notifications })).toHaveAttribute(
      "href",
      "/en/notifications"
    );
  });

  it("marks the active nav item", () => {
    renderPlain(<Sidebar active="dashboard" locale="en" />);

    expect(screen.getByRole("link", { name: en.nav.dashboard })).toHaveAttribute("data-active");
    expect(screen.getByRole("link", { name: en.nav.coach })).not.toHaveAttribute("data-active");
  });
});

describe("Sidebar inline chat list", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  });

  it("renders the chat list under Coach when Coach is the active tab", () => {
    renderPlain(<Sidebar active="coach" locale="en" />);

    expect(screen.getByText(en.chat.newChat)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(en.chat.searchPlaceholder)).toBeInTheDocument();
  });

  it("does not render the chat list when another tab is active", () => {
    renderPlain(<Sidebar active="dashboard" locale="en" />);

    expect(screen.queryByText(en.chat.newChat)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(en.chat.searchPlaceholder)).not.toBeInTheDocument();
  });

  it("hides the chat list when the sidebar is collapsed, even if Coach is active", () => {
    renderPlain(<Sidebar active="coach" locale="en" />, { defaultOpen: false });

    expect(screen.queryByText(en.chat.newChat)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(en.chat.searchPlaceholder)).not.toBeInTheDocument();
  });
});

describe("Sidebar user display", () => {
  it("shows the signed-in user's name and initials, not the mock user", () => {
    renderWithUser("Runner Example", <Sidebar active="dashboard" locale="en" />);

    expect(screen.getByText("Runner Example")).toBeInTheDocument();
    expect(screen.getByText("RE")).toBeInTheDocument();
    expect(screen.queryByText("Sam B.")).not.toBeInTheDocument();
  });
});
