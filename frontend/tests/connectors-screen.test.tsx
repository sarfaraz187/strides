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
    user: { email: "runner@example.com", name: "Runner", created_at: "", health_connected: true },
    isLoading: false,
  }),
}));

vi.mock("@/hooks/use-health-connector", () => ({
  HEALTH_CONNECT_URL: "http://localhost:8000/auth/health/connect",
  useHealthDisconnect: () => ({ disconnect: vi.fn(), isPending: false, error: null }),
  useHealthConnectErrorFromUrl: () => false,
}));

describe("ConnectorsScreen", () => {
  it("shows Google Health as connected and offers disconnect", () => {
    renderWithIntl(<ConnectorsScreen />);

    expect(screen.getByText("Google Health")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /disconnect/i })).toBeInTheDocument();
  });

  it("does not render a Google Calendar card", () => {
    renderWithIntl(<ConnectorsScreen />);

    expect(screen.queryByText("Google Calendar")).not.toBeInTheDocument();
  });
});
