"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { Card } from "@/components/ui/card";
import { useNotifications } from "@/hooks/use-notifications";
import type { Notification } from "@/lib/notifications-api";
import { cn } from "@/lib/utils";

function NotificationRow({ notification, locale }: { notification: Notification; locale: string }) {
  const t = useTranslations("notifications");

  const card = (
    <Card className="rounded-2xl p-4 lg:px-6 lg:py-5">
      <div className={cn("text-sm font-medium lg:text-base", notification.status === "unread" ? "text-primary" : "text-muted")}>{t(`types.${notification.type}`)}</div>
    </Card>
  );

  return notification.action_href ? <Link href={`/${locale}${notification.action_href}`}>{card}</Link> : card;
}

export function NotificationsScreen({ locale }: { locale: string }) {
  const t = useTranslations("notifications");
  const { notifications, markAllRead } = useNotifications();

  // Fire once per page visit, not on every notifications refetch (the 5-min
  // poll would otherwise call this repeatedly while the page stays open).
  const hasMarkedRead = useRef(false);
  useEffect(() => {
    if (!hasMarkedRead.current) {
      hasMarkedRead.current = true;
      markAllRead();
    }
  }, [markAllRead]);

  return (
    <div className="flex-1 overflow-y-auto px-3 py-5 lg:mx-auto lg:w-full lg:max-w-200 lg:px-0 lg:py-9">
      <div className="mb-5 lg:mb-7">
        <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-3xl">{t("title")}</div>
      </div>

      <div className="flex flex-col gap-2.5 lg:gap-3">
        {notifications.length === 0 && <div className="py-8 text-center text-sm text-muted">{t("empty")}</div>}
        {notifications.map((notification) => (
          <NotificationRow key={notification.id} notification={notification} locale={locale} />
        ))}
      </div>
    </div>
  );
}
