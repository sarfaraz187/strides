import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { ConnectorsScreen } from "@/components/connectors-screen";
import en from "../messages/en.json";

function renderWithIntl(ui: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      {ui}
    </NextIntlClientProvider>
  );
}

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { email: "runner@example.com", name: "Runner", created_at: "", health_connected: true, avatar_url: null },
    isLoading: false,
  }),
}));

vi.mock("@/hooks/use-health-connector", () => ({
  HEALTH_CONNECT_URL: "http://localhost:8000/auth/health/connect",
  useHealthDisconnect: () => ({ disconnect: vi.fn(), isPending: false, error: null }),
  useHealthConnectErrorFromUrl: () => false,
}));

const useDashboardMock = vi.fn();
vi.mock("@/hooks/use-dashboard", () => ({
  useDashboard: () => useDashboardMock(),
}));

describe("ConnectorsScreen", () => {
  it("shows Google Health as connected and offers disconnect", () => {
    useDashboardMock.mockReturnValue({ dashboard: undefined, isLoading: false, isError: false });
    renderWithIntl(<ConnectorsScreen />);

    expect(screen.getByText("Google Health")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /disconnect/i })).toBeInTheDocument();
  });

  it("does not render a Google Calendar card", () => {
    useDashboardMock.mockReturnValue({ dashboard: undefined, isLoading: false, isError: false });
    renderWithIntl(<ConnectorsScreen />);

    expect(screen.queryByText("Google Calendar")).not.toBeInTheDocument();
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
