import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import { DashboardScreen } from "../components/dashboard-screen";
import { AuthContext } from "../lib/auth-context";

describe("DashboardScreen", () => {
  it("renders week stats, recent runs, and goals from mock data", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <DashboardScreen locale="en" />
      </NextIntlClientProvider>
    );

    expect(screen.getByText(en.dashboard.thisWeek)).toBeInTheDocument();
    expect(screen.getByText(en.dashboard.recentRuns)).toBeInTheDocument();
    // "Goals" renders twice: mobile section header + desktop grid-card header
    // (both present in the DOM regardless of viewport; CSS `hidden`/`lg:` toggles visibility).
    expect(screen.getAllByText(en.dashboard.goals)).toHaveLength(2);
    expect(screen.getByText("21.9")).toBeInTheDocument(); // mock weekly km
  });
});

describe("DashboardScreen user display", () => {
  it("shows the signed-in user's initials on the mobile avatar link, not the mock user's", () => {
    render(
      <AuthContext.Provider
        value={{
          user: { email: "runner@example.com", name: "Runner Example", created_at: "", health_connected: false, avatar_url: null },
          isLoading: false,
        }}
      >
        <NextIntlClientProvider locale="en" messages={en}>
          <DashboardScreen locale="en" />
        </NextIntlClientProvider>
      </AuthContext.Provider>
    );

    expect(screen.getByText("RE")).toBeInTheDocument();
    expect(screen.queryByText("SB")).not.toBeInTheDocument();
  });
});
