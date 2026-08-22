"use client";

import Image from "next/image";
import { useTranslations } from "next-intl";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function SignInScreen() {
  const t = useTranslations("signIn");
  const loginUrl = `${process.env.NEXT_PUBLIC_API_URL}/auth/login`;

  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="flex h-full w-full max-w-[480px] flex-col items-center justify-between bg-surface px-8 pt-15 pb-12 lg:h-auto lg:w-[380px] lg:justify-center lg:gap-6 lg:bg-transparent">
        <div className="lg:hidden" />
        <div className="flex flex-col items-center gap-5">
          <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-2xl">
            <Image src="/icon-512.png" alt="Strides" width={80} height={80} className="h-full w-full object-cover" priority />
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold tracking-[-0.5px] text-primary">{t("title")}</div>
            <div className="mt-1.5 text-sm font-medium text-muted">{t("tagline")}</div>
          </div>
        </div>
        <div className="flex w-full flex-col gap-3">
          <a
            href={loginUrl}
            className={cn(
              buttonVariants(),
              "h-14 gap-2.5 rounded-2xl bg-primary text-base text-primary-foreground"
            )}
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path
                fill="#EA4335"
                d="M12 10.2v3.9h5.5c-.24 1.4-1.7 4.1-5.5 4.1-3.3 0-6-2.7-6-6.2s2.7-6.2 6-6.2c1.9 0 3.15.8 3.9 1.5l2.65-2.55C16.9 3.1 14.7 2.1 12 2.1 6.9 2.1 2.7 6.3 2.7 11.4S6.9 20.7 12 20.7c6.9 0 9.3-4.85 9.3-8.5 0-.55-.05-1-.15-1.4H12z"
              />
            </svg>
            {t("cta")}
          </a>
          <div className="text-center text-xs leading-relaxed text-disclaimer whitespace-pre-line">
            {t("disclaimer")}
          </div>
        </div>
      </div>
    </div>
  );
}
