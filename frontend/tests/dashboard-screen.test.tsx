import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import en from "../messages/en.json";
import { DashboardScreen } from "../components/dashboard-screen";

type DashboardOverrides = {
  calendar_connected?: boolean;
  upcoming_runs?: unknown[];
  current_weather?: unknown;
};

function mockFetchResponses(overrides: DashboardOverrides = {}) {
  vi.spyOn(global, "fetch").mockImplementation((url, options) => {
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
            calendar_connected: overrides.calendar_connected ?? false,
            upcoming_runs: overrides.upcoming_runs ?? [],
            current_weather: overrides.current_weather ?? null,
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
    if (String(url).endsWith("/calendar/events") && options?.method === "POST") {
      return Promise.resolve(
        new Response(JSON.stringify({ id: "e1", summary: "Easy 5K", start: { dateTime: "2026-08-25T07:00:00" } }))
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

    await waitFor(() => expect(screen.getByText("21.9")).toBeInTheDocument());
    expect(screen.getByText(en.dashboard.recentRuns)).toBeInTheDocument();
    expect(screen.getByText("Monday")).toBeInTheDocument();
    expect(screen.getByText("6.1 km")).toBeInTheDocument();
  });
});

describe("DashboardScreen calendar + weather", () => {
  it("hides upcoming runs section when calendar is not connected", async () => {
    mockFetchResponses({ calendar_connected: false });
    renderWithProviders(<DashboardScreen locale="en" />);

    await waitFor(() => expect(screen.queryByText(en.dashboard.planARun)).not.toBeInTheDocument());
    expect(screen.queryByText(en.dashboard.upcomingRuns)).not.toBeInTheDocument();
  });

  it("renders upcoming runs and weather when calendar is connected", async () => {
    mockFetchResponses({
      calendar_connected: true,
      upcoming_runs: [
        {
          id: "e1",
          summary: "Easy 5K",
          start: { dateTime: "2026-08-25T07:00:00" },
          forecast: { temp: 22, condition: "clear" },
        },
      ],
      current_weather: {
        temp: 27,
        feels_like: 30,
        humidity: 74,
        wind: 9,
        condition: "partly cloudy",
        aqi: 42,
        hourly: [
          { time: "2026-08-22T18:00", temp: 28 },
          { time: "2026-08-22T19:00", temp: 27 },
        ],
      },
    });
    renderWithProviders(<DashboardScreen locale="en" />);

    await waitFor(() => expect(screen.getByText("Easy 5K")).toBeInTheDocument());
    expect(screen.getByText(en.dashboard.planARun)).toBeInTheDocument();
    expect(screen.getAllByText("27°").length).toBeGreaterThan(0);
    expect(screen.getByText(/partly cloudy · Feels like 30°C/)).toBeInTheDocument();

    expect(screen.getByText(en.dashboard.humidity)).toBeInTheDocument();
    expect(screen.getByText("74%")).toBeInTheDocument();
    expect(screen.getByText(en.dashboard.wind)).toBeInTheDocument();
    expect(screen.getByText("9 km/h")).toBeInTheDocument();
    expect(screen.getByText(en.dashboard.aqi)).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();

    expect(screen.getByText("22° clear")).toBeInTheDocument();
  });

  it("plans a run through the modal", async () => {
    mockFetchResponses({ calendar_connected: true });
    renderWithProviders(<DashboardScreen locale="en" />);

    await waitFor(() => expect(screen.getByText(en.dashboard.planARun)).toBeInTheDocument());
    fireEvent.click(screen.getByText(en.dashboard.planARun));

    fireEvent.change(screen.getByLabelText(en.dashboard.planRunName), { target: { value: "Tempo run" } });
    fireEvent.change(screen.getByLabelText(en.dashboard.planRunDate), { target: { value: "2026-08-25" } });
    fireEvent.change(screen.getByLabelText(en.dashboard.planRunTime), { target: { value: "07:00" } });
    fireEvent.change(screen.getByLabelText(en.dashboard.planRunDuration), { target: { value: "45" } });

    fireEvent.click(screen.getByText(en.dashboard.planRunSubmit));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/calendar/events"),
        expect.objectContaining({ method: "POST" })
      )
    );
  });
});
