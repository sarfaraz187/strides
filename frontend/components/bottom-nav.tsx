"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { cn } from "@/lib/utils";

export function BottomNav({
  active,
  locale,
  className,
}: {
  active: "dashboard" | "coach" | "connectors" | "profile";
  locale: string;
  className?: string;
}) {
  const t = useTranslations("nav");

  return (
    <div
      className={cn(
        "flex h-[74px] items-center justify-around border-t border-border bg-surface pb-2",
        className
      )}
    >
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
      <Link
        href={`/${locale}/connectors`}
        className={`flex flex-col items-center gap-1 ${
          active === "connectors" ? "text-primary" : "text-muted-nav"
        }`}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <path
            d="M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M6 10h12v4a6 6 0 01-6 6 6 6 0 01-6-6v-4z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
        </svg>
        <span className="text-[10px] font-semibold">{t("connectors")}</span>
      </Link>
    </div>
  );
}
