import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import { Sidebar } from "../components/sidebar";

describe("Sidebar", () => {
  it("links to dashboard and chat for the given locale", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <Sidebar active="dashboard" locale="en" />
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

  it("marks the active nav item", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <Sidebar active="dashboard" locale="en" />
      </NextIntlClientProvider>
    );

    expect(screen.getByRole("link", { name: en.nav.dashboard })).toHaveClass(
      "text-primary-foreground"
    );
    expect(screen.getByRole("link", { name: en.nav.coach })).toHaveClass("text-[#B8C2B5]");
  });
});
