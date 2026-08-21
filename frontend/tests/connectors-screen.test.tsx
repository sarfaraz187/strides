import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConnectorsScreen } from "@/components/connectors-screen";
import en from "../messages/en.json";

function renderWithIntl(ui: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      {ui}
    </NextIntlClientProvider>
  );
}

const baseUser = {
  email: "runner@example.com",
  name: "Runner",
  created_at: "",
  health_connected: true,
  calendar_connected: false,
  avatar_url: null,
};

const useAuthMock = vi.fn();
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock("@/hooks/use-health-connector", () => ({
  HEALTH_CONNECT_URL: "http://localhost:8000/auth/health/connect",
  useHealthDisconnect: () => ({ disconnect: vi.fn(), isPending: false, error: null }),
  useHealthConnectErrorFromUrl: () => false,
}));

const disconnectCalendarMock = vi.fn();
vi.mock("@/hooks/use-calendar-connector", () => ({
  CALENDAR_CONNECT_URL: "http://localhost:8000/auth/calendar/connect",
  useCalendarDisconnect: () => ({ disconnect: disconnectCalendarMock, isPending: false, error: null }),
  useCalendarConnectErrorFromUrl: () => false,
}));

const useDashboardMock = vi.fn();
vi.mock("@/hooks/use-dashboard", () => ({
  useDashboard: () => useDashboardMock(),
}));

describe("ConnectorsScreen", () => {
  beforeEach(() => {
    disconnectCalendarMock.mockClear();
    useAuthMock.mockReturnValue({ user: baseUser, isLoading: false });
    useDashboardMock.mockReturnValue({ dashboard: undefined, isLoading: false, isError: false });
  });

  it("shows Google Health as connected and offers disconnect", () => {
    renderWithIntl(<ConnectorsScreen />);

    expect(screen.getByText("Google Health")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /disconnect/i }).length).toBeGreaterThan(0);
  });

  it("shows a Google Calendar card with a Connect link when not connected", () => {
    renderWithIntl(<ConnectorsScreen />);

    expect(screen.getByText("Google Calendar")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en.connectors.connect })).toHaveAttribute(
      "href",
      "http://localhost:8000/auth/calendar/connect"
    );
  });

  it("shows Disconnect for Google Calendar when connected and calls the calendar disconnect hook", () => {
    useAuthMock.mockReturnValue({ user: { ...baseUser, calendar_connected: true }, isLoading: false });
    renderWithIntl(<ConnectorsScreen />);

    const disconnectButtons = screen.getAllByRole("button", { name: /disconnect/i });
    fireEvent.click(disconnectButtons[disconnectButtons.length - 1]);

    expect(disconnectCalendarMock).toHaveBeenCalled();
  });

  it("shows the account-not-linked notice with a link when health_error is present", () => {
    useDashboardMock.mockReturnValue({
      dashboard: {
        weekly_stats: null,
        recent_runs: [],
        health_error: {
          error: "ACCOUNT_NOT_LINKED",
          message: "The account is not linked to Google Health.",
          redirect_uri: "https://fitbit.google.com/auth/signup",
        },
      },
      isLoading: false,
      isError: false,
    });
    renderWithIntl(<ConnectorsScreen />);

    expect(screen.getByText("The account is not linked to Google Health.")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: en.connectors.healthErrorAction });
    expect(link).toHaveAttribute("href", "https://fitbit.google.com/auth/signup");
  });

  it("does not show the notice when there is no health_error", () => {
    useDashboardMock.mockReturnValue({
      dashboard: { weekly_stats: null, recent_runs: [], health_error: null },
      isLoading: false,
      isError: false,
    });
    renderWithIntl(<ConnectorsScreen />);

    expect(
      screen.queryByText("The account is not linked to Google Health.")
    ).not.toBeInTheDocument();
  });
});
