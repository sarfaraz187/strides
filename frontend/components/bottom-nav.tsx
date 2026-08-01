"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

export function BottomNav({
  active,
  locale,
}: {
  active: "dashboard" | "coach";
  locale: string;
}) {
  const t = useTranslations("nav");

  return (
    <div className="flex h-[74px] items-center justify-around border-t border-border bg-surface pb-2">
      <Link
        href={`/${locale}/dashboard`}
        className={active === "dashboard" ? "text-primary" : "text-muted-nav"}
      >
        {t("dashboard")}
      </Link>
      <Link
        href={`/${locale}/chat`}
        className={active === "coach" ? "text-primary" : "text-muted-nav"}
      >
        {t("coach")}
      </Link>
    </div>
  );
}
