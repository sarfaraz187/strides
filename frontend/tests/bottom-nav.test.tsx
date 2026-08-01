import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import { BottomNav } from "../components/bottom-nav";

describe("BottomNav", () => {
  it("links to dashboard and chat for the given locale", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <BottomNav active="dashboard" locale="en" />
      </NextIntlClientProvider>
    );

    expect(screen.getByRole("link", { name: en.nav.dashboard })).toHaveAttribute(
      "href",
      "/en/dashboard"
    );
    expect(screen.getByRole("link", { name: en.nav.coach })).toHaveAttribute(
      "href",
      "/en/chat"
    );
  });
});
