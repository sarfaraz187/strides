"use client";

import { Bell, LayoutGrid, Lock, MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { Avatar } from "@/components/avatar";
import { NotificationBadge } from "@/components/notification-badge";
import { useAuth } from "@/lib/auth-context";
import { useNotifications } from "@/hooks/use-notifications";
import { cn } from "@/lib/utils";

export function BottomNav({ active, locale, className }: { active: "dashboard" | "coach" | "connectors" | "notifications" | "profile"; locale: string; className?: string }) {
  const t = useTranslations("nav");
  const { user } = useAuth();
  const { unreadCount } = useNotifications();

  return (
    <div className={cn("flex h-18 items-center justify-around border-t border-border bg-surface pb-2", className)}>
      <Link href={`/${locale}/dashboard`} className={`flex flex-col items-center gap-1 ${active === "dashboard" ? "text-primary" : "text-muted-nav"}`}>
        <LayoutGrid size={22} strokeWidth={1.8} />
        <span className="text-xs font-semibold">{t("dashboard")}</span>
      </Link>
      <Link href={`/${locale}/chat`} className={`flex flex-col items-center gap-1 ${active === "coach" ? "text-primary" : "text-muted-nav"}`}>
        <MessageSquare size={22} strokeWidth={1.8} />
        <span className="text-xs font-semibold">{t("coach")}</span>
      </Link>
      <Link href={`/${locale}/connectors`} className={`flex flex-col items-center gap-1 ${active === "connectors" ? "text-primary" : "text-muted-nav"}`}>
        <Lock size={22} strokeWidth={1.8} />
        <span className="text-xs font-semibold">{t("connectors")}</span>
      </Link>
      <Link href={`/${locale}/notifications`} className={`flex flex-col items-center gap-1 ${active === "notifications" ? "text-primary" : "text-muted-nav"}`}>
        <span className="relative">
          <Bell size={22} strokeWidth={1.8} />
          <NotificationBadge count={unreadCount} />
        </span>
        <span className="text-xs font-semibold">{t("notifications")}</span>
      </Link>
      <Link href={`/${locale}/profile`} className={`flex flex-col items-center gap-1 ${active === "profile" ? "text-primary" : "text-muted-nav"}`}>
        <Avatar user={user ?? null} size="sm" className={active === "profile" ? "ring-2 ring-primary" : ""} />
        <span className="text-xs font-semibold">{t("profile")}</span>
      </Link>
    </div>
  );
}
