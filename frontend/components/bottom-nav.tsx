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
        className={`flex flex-col items-center gap-1 ${
          active === "dashboard" ? "text-primary" : "text-muted-nav"
        }`}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <rect x="3" y="3" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          <rect x="13" y="3" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          <rect x="3" y="13" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          <rect x="13" y="13" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
        </svg>
        <span className="text-[10px] font-semibold">{t("dashboard")}</span>
      </Link>
      <Link
        href={`/${locale}/chat`}
        className={`flex flex-col items-center gap-1 ${
          active === "coach" ? "text-primary" : "text-muted-nav"
        }`}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <path d="M4 5h16v11H8l-4 4V5z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        </svg>
        <span className="text-[10px] font-semibold">{t("coach")}</span>
      </Link>
    </div>
  );
}
