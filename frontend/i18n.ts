import { getRequestConfig } from "next-intl/server";

export const locales = ["en", "de"] as const;
export const defaultLocale = "en" as const;

export default getRequestConfig(async ({ locale }) => ({
  locale: locale ?? defaultLocale,
  messages: (await import(`./messages/${locale ?? defaultLocale}.json`)).default,
}));
