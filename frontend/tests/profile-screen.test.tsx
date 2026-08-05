import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { ProfileScreen } from "@/components/profile-screen";
import en from "../messages/en.json";

const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  usePathname: () => "/en/profile",
}));

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={en}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

describe("ProfileScreen", () => {
  it("loads preferences and shows the current language", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          weekly_goal_km: 30,
          units: "km",
          notifications_enabled: true,
          language: "en",
        }),
        { status: 200 }
      )
    );

    renderWithProviders(<ProfileScreen locale="en" />);

    await waitFor(() => expect(screen.getByText("English")).toBeInTheDocument());
  });
});
