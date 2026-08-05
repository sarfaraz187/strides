import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import { Sidebar } from "../components/sidebar";
import { SidebarProvider } from "../components/ui/sidebar";
import { AuthContext } from "../lib/auth-context";

function renderWithUser(name: string | null, ui: React.ReactElement) {
  return render(
    <AuthContext.Provider
      value={{
        user: { email: "runner@example.com", name, created_at: "", health_connected: false, avatar_url: null },
        isLoading: false,
      }}
    >
      <NextIntlClientProvider locale="en" messages={en}>
        <SidebarProvider>{ui}</SidebarProvider>
      </NextIntlClientProvider>
    </AuthContext.Provider>
  );
}

describe("Sidebar", () => {
  it("links to dashboard and chat for the given locale", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <SidebarProvider>
          <Sidebar active="dashboard" locale="en" />
        </SidebarProvider>
      </NextIntlClientProvider>
    );

    expect(screen.getByRole("link", { name: en.nav.dashboard })).toHaveAttribute(
      "href",
      "/en/dashboard"
    );
    expect(screen.getByRole("link", { name: en.nav.coach })).toHaveAttribute(
      "href",
      "/en/chat"
    );
  });

  it("marks the active nav item", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <SidebarProvider>
          <Sidebar active="dashboard" locale="en" />
        </SidebarProvider>
      </NextIntlClientProvider>
    );

    expect(screen.getByRole("link", { name: en.nav.dashboard })).toHaveAttribute("data-active");
    expect(screen.getByRole("link", { name: en.nav.coach })).not.toHaveAttribute("data-active");
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
