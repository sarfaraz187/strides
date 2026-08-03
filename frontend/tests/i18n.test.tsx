import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import de from "../messages/de.json";

function Greeting() {
  const { useTranslations } = require("next-intl");
  const t = useTranslations("signIn");
  return <div>{t("title")}</div>;
}

describe("i18n", () => {
  it("renders English by default", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <Greeting />
      </NextIntlClientProvider>
    );
    expect(screen.getByText("Strides")).toBeInTheDocument();
  });

  it("renders German when locale is de", () => {
    render(
      <NextIntlClientProvider locale="de" messages={de}>
        <Greeting />
      </NextIntlClientProvider>
    );
    expect(screen.getByText("Strides")).toBeInTheDocument(); // brand name unchanged
  });

  it("has matching keys in both locale files", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(de).sort());
  });
});
