import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { ProfileScreen } from "@/components/profile-screen";
import { AuthContext } from "@/lib/auth-context";
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

  it("shows the signed-in user's name, email, and join date instead of the mock user", async () => {
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

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <AuthContext.Provider
        value={{
          user: {
            email: "runner@example.com",
            name: "Runner Example",
            created_at: "2026-01-15T00:00:00Z",
            health_connected: false,
            calendar_connected: false,
            avatar_url: null,
          },
          isLoading: false,
        }}
      >
        <QueryClientProvider client={queryClient}>
          <NextIntlClientProvider locale="en" messages={en}>
            <ProfileScreen locale="en" />
          </NextIntlClientProvider>
        </QueryClientProvider>
      </AuthContext.Provider>
    );

    await waitFor(() => expect(screen.getByText("Runner Example")).toBeInTheDocument());
    expect(screen.getByText("runner@example.com")).toBeInTheDocument();
    expect(screen.getByText("Jan 2026")).toBeInTheDocument();
  });

  it("rejects an oversized file before making any network call", async () => {
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

    const fetchCallsBefore = (global.fetch as ReturnType<typeof vi.spyOn>).mock.calls.length;
    const input = screen.getByLabelText(en.profile.changeAvatar) as HTMLInputElement;
    const oversizedFile = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.jpg", {
      type: "image/jpeg",
    });

    await userEvent.upload(input, oversizedFile);

    expect(screen.getByText(en.profile.avatarTooLarge)).toBeInTheDocument();
    expect((global.fetch as ReturnType<typeof vi.spyOn>).mock.calls.length).toBe(fetchCallsBefore);
  });
});

describe("ProfileScreen location", () => {
  function mockFetch() {
    return vi.spyOn(global, "fetch").mockImplementation((url, options) => {
      const urlString = String(url);
      if (urlString.endsWith("/preferences") && options?.method === "PUT") {
        const body = JSON.parse(options.body as string);
        return Promise.resolve(
          new Response(
            JSON.stringify({
              weekly_goal_km: 30,
              units: "km",
              notifications_enabled: true,
              language: "en",
              location_lat: body.location_lat ?? null,
              location_lon: body.location_lon ?? null,
            })
          )
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            weekly_goal_km: 30,
            units: "km",
            notifications_enabled: true,
            language: "en",
            location_lat: null,
            location_lon: null,
          })
        )
      );
    });
  }

  it("uses geolocation and saves the returned coordinates", async () => {
    mockFetch();
    const getCurrentPosition = vi.fn((success: PositionCallback) =>
      success({ coords: { latitude: 17.385, longitude: 78.4867 } } as GeolocationPosition)
    );
    Object.defineProperty(global.navigator, "geolocation", {
      value: { getCurrentPosition },
      configurable: true,
    });

    renderWithProviders(<ProfileScreen locale="en" />);
    await waitFor(() => expect(screen.getByText(en.profile.useMyLocation)).toBeInTheDocument());

    (await screen.findByText(en.profile.useMyLocation)).click();

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/preferences"),
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({ location_lat: 17.385, location_lon: 78.4867 }),
        })
      )
    );
  });

  it("shows an error message on geolocation failure without throwing", async () => {
    mockFetch();
    const getCurrentPosition = vi.fn((_success: PositionCallback, error?: PositionErrorCallback) =>
      error?.({ code: 1, message: "denied" } as GeolocationPositionError)
    );
    Object.defineProperty(global.navigator, "geolocation", {
      value: { getCurrentPosition },
      configurable: true,
    });

    renderWithProviders(<ProfileScreen locale="en" />);
    await waitFor(() => expect(screen.getByText(en.profile.useMyLocation)).toBeInTheDocument());

    (await screen.findByText(en.profile.useMyLocation)).click();

    await waitFor(() => expect(screen.getByText(en.profile.locationDenied)).toBeInTheDocument());
  });
});
