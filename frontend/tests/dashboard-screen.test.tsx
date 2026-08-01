import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import { DashboardScreen } from "../components/dashboard-screen";

describe("DashboardScreen", () => {
  it("renders week stats, recent runs, and goals from mock data", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <DashboardScreen />
      </NextIntlClientProvider>
    );

    expect(screen.getByText(en.dashboard.thisWeek)).toBeInTheDocument();
    expect(screen.getByText(en.dashboard.recentRuns)).toBeInTheDocument();
    expect(screen.getByText(en.dashboard.goals)).toBeInTheDocument();
    expect(screen.getByText("21.9")).toBeInTheDocument(); // mock weekly km
  });
});
