import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import en from "../messages/en.json";
import { SignInScreen } from "../components/sign-in-screen";

vi.mock("../lib/auth-context", () => ({
  useAuth: () => ({ user: null, isLoading: false }),
}));

function renderWithIntl(ui: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      {ui}
    </NextIntlClientProvider>
  );
}

describe("SignInScreen", () => {
  it("shows the sign-in button with the correct href", () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    renderWithIntl(<SignInScreen />);

    const link = screen.getByRole("link", { name: en.signIn.cta });
    expect(link).toHaveAttribute("href", "https://api.example.com/auth/login");
  });

  it("shows the tagline", () => {
    renderWithIntl(<SignInScreen />);
    expect(screen.getByText(en.signIn.tagline)).toBeInTheDocument();
  });
});
