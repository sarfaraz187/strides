"use client";

import { LayoutGrid, Lock, MessageSquare } from "lucide-react";
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
        "flex h-18 items-center justify-around border-t border-border bg-surface pb-2",
        className
      )}
    >
      <Link
        href={`/${locale}/dashboard`}
        className={`flex flex-col items-center gap-1 ${
          active === "dashboard" ? "text-primary" : "text-muted-nav"
        }`}
      >
        <LayoutGrid size={22} strokeWidth={1.8} />
        <span className="text-xs font-semibold">{t("dashboard")}</span>
      </Link>
      <Link
        href={`/${locale}/chat`}
        className={`flex flex-col items-center gap-1 ${
          active === "coach" ? "text-primary" : "text-muted-nav"
        }`}
      >
        <MessageSquare size={22} strokeWidth={1.8} />
        <span className="text-xs font-semibold">{t("coach")}</span>
      </Link>
      <Link
        href={`/${locale}/connectors`}
        className={`flex flex-col items-center gap-1 ${
          active === "connectors" ? "text-primary" : "text-muted-nav"
        }`}
      >
        <Lock size={22} strokeWidth={1.8} />
        <span className="text-xs font-semibold">{t("connectors")}</span>
      </Link>
    </div>
  );
}
