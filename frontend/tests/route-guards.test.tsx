import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import en from "../messages/en.json";
import { RequireAuth } from "../components/require-auth";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("../lib/auth-context", () => ({
  useAuth: () => ({ user: null, isLoading: false }),
}));

describe("RequireAuth", () => {
  it("redirects to sign-in when signed out", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <NextIntlClientProvider locale="en" messages={en}>
          <RequireAuth locale="en">
            <div>protected content</div>
          </RequireAuth>
        </NextIntlClientProvider>
      </QueryClientProvider>
    );

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/en"));
  });
});
