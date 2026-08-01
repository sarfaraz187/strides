"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";

export function SignInScreen() {
  const t = useTranslations("signIn");
  const loginUrl = `${process.env.NEXT_PUBLIC_API_URL}/auth/login`;

  return (
    <div className="flex h-full flex-col items-center justify-between px-8 py-14">
      <div />
      <div className="flex flex-col items-center gap-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary" />
        <div className="text-center">
          <div className="text-2xl font-bold text-primary">{t("title")}</div>
          <div className="mt-1.5 text-sm font-medium text-muted">{t("tagline")}</div>
        </div>
      </div>
      <div className="flex w-full flex-col gap-3">
        <Button
          render={<a href={loginUrl} />}
          className="h-[54px] rounded-2xl bg-primary text-primary-foreground"
        >
          {t("cta")}
        </Button>
        <div className="text-center text-xs leading-relaxed text-muted-nav whitespace-pre-line">
          {t("disclaimer")}
        </div>
      </div>
    </div>
  );
}
