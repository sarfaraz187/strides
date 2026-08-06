import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import en from "../messages/en.json";
import { DashboardScreen } from "../components/dashboard-screen";
import { AuthContext } from "../lib/auth-context";

function mockFetchResponses() {
  vi.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).endsWith("/dashboard")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            weekly_stats: {
              run_count: 4,
              total_distance_km: 21.9,
              total_duration_min: 121.0,
              avg_pace_min_per_km: 5.53,
            },
            recent_runs: [
              {
                date: "2026-08-03T06:42:00",
                distance_km: 6.1,
                duration_min: 33.4,
                pace_min_per_km: 5.47,
                calories: 320,
              },
            ],
            goals: [
              {
                id: "goal-1",
                description: "Run 30km this week",
                target_value: 30,
                metric: "distance_km",
                period: "week",
                deadline: null,
                progress_pct: 73,
              },
            ],
          })
        )
      );
    }
    if (String(url).endsWith("/preferences")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            weekly_goal_km: 30,
            units: "km",
            notifications_enabled: true,
            language: "en",
          })
        )
      );
    }
    return Promise.reject(new Error(`Unexpected fetch to ${url}`));
  });
}

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={en}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

describe("DashboardScreen", () => {
  it("renders week stats and recent runs from the backend", async () => {
    mockFetchResponses();
    renderWithProviders(<DashboardScreen locale="en" />);

    expect(screen.getByText(en.dashboard.thisWeek)).toBeInTheDocument();
    expect(screen.getByText(en.dashboard.recentRuns)).toBeInTheDocument();
    // "Goals" renders twice: mobile section header + desktop grid-card header
    // (both present in the DOM regardless of viewport; CSS `hidden`/`lg:` toggles visibility).
    expect(screen.getAllByText(en.dashboard.goals)).toHaveLength(2);

    await waitFor(() => expect(screen.getByText("21.9")).toBeInTheDocument());
    expect(screen.getByText("Monday")).toBeInTheDocument();
    expect(screen.getByText("6.1 km")).toBeInTheDocument();
    expect(screen.getAllByText("Run 30km this week")).toHaveLength(2);
  });
});

describe("DashboardScreen user display", () => {
  it("shows the signed-in user's initials on the mobile avatar link, not a mock user's", () => {
    mockFetchResponses();
    render(
      <AuthContext.Provider
        value={{
          user: { email: "runner@example.com", name: "Runner Example", created_at: "", health_connected: false, avatar_url: null },
          isLoading: false,
        }}
      >
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <NextIntlClientProvider locale="en" messages={en}>
            <DashboardScreen locale="en" />
          </NextIntlClientProvider>
        </QueryClientProvider>
      </AuthContext.Provider>
    );

    expect(screen.getByText("RE")).toBeInTheDocument();
    expect(screen.queryByText("SB")).not.toBeInTheDocument();
  });
});
