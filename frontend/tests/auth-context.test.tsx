import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "../lib/auth-context";

function TestConsumer() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <div>loading</div>;
  return <div>{user ? `signed in as ${user.email}` : "signed out"}</div>;
}

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>
  );
}

describe("AuthProvider", () => {
  afterEach(() => vi.restoreAllMocks());

  it("exposes the signed-in user when /auth/me succeeds", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ email: "runner@example.com" }), { status: 200 })
    );

    renderWithProviders(<TestConsumer />);

    await waitFor(() =>
      expect(screen.getByText("signed in as runner@example.com")).toBeInTheDocument()
    );
  });

  it("exposes null when /auth/me returns 401", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    renderWithProviders(<TestConsumer />);

    await waitFor(() => expect(screen.getByText("signed out")).toBeInTheDocument());
  });
});
