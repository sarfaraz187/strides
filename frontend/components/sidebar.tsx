"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { mockUser } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

export function Sidebar({
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
    <div className={cn("w-[240px] flex-col bg-primary px-5 py-7", className)}>
      <div className="mb-9 flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-[#3F5245]">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path
              d="M4 17L9 10L13 14L20 5"
              stroke="#D8DED0"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <span className="text-lg font-bold tracking-[-0.3px] text-primary-foreground">
          Strides
        </span>
      </div>

      <Link
        href={`/${locale}/dashboard`}
        className={cn(
          "mb-1.5 flex items-center gap-3 rounded-[10px] px-3 py-[11px] text-sm font-semibold",
          active === "dashboard" ? "bg-[#3F5245] text-primary-foreground" : "text-[#B8C2B5]"
        )}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <rect x="3" y="3" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          <rect x="13" y="3" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          <rect x="3" y="13" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          <rect x="13" y="13" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
        </svg>
        {t("dashboard")}
      </Link>
      <Link
        href={`/${locale}/chat`}
        className={cn(
          "flex items-center gap-3 rounded-[10px] px-3 py-[11px] text-sm font-semibold",
          active === "coach" ? "bg-[#3F5245] text-primary-foreground" : "text-[#B8C2B5]"
        )}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M4 5h16v11H8l-4 4V5z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        </svg>
        {t("coach")}
      </Link>
      <Link
        href={`/${locale}/connectors`}
        className={cn(
          "mt-1.5 flex items-center gap-3 rounded-[10px] px-3 py-[11px] text-sm font-semibold",
          active === "connectors" ? "bg-[#3F5245] text-primary-foreground" : "text-[#B8C2B5]"
        )}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path
            d="M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M6 10h12v4a6 6 0 01-6 6 6 6 0 01-6-6v-4z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
        </svg>
        {t("connectors")}
      </Link>

      <div className="flex-1" />

      <Link
        href={`/${locale}/profile`}
        className="flex items-center gap-2.5 border-t border-primary-foreground/[0.12] pt-4"
      >
        <div className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-[#3F5245] text-xs font-semibold text-primary-foreground">
          {mockUser.initials}
        </div>
        <div className="text-[13px] font-medium text-[#D8DED0]">{mockUser.name}</div>
      </Link>
    </div>
  );
}
