"use client";

import { useTranslations } from "next-intl";

import { ConnectorCard, type ConnectorConfig } from "@/components/connector-card";
import { useAuth } from "@/lib/auth-context";
import { useDashboard } from "@/hooks/use-dashboard";
import { HEALTH_CONNECT_URL, useHealthConnectErrorFromUrl, useHealthDisconnect } from "@/hooks/use-health-connector";
import { CALENDAR_CONNECT_URL, useCalendarConnectErrorFromUrl, useCalendarDisconnect } from "@/hooks/use-calendar-connector";

export function ConnectorsScreen() {
  const t = useTranslations("connectors");
  const { user } = useAuth();
  const { disconnect, isPending, error: disconnectError } = useHealthDisconnect();
  const showConnectError = useHealthConnectErrorFromUrl();
  const { disconnect: disconnectCalendar, isPending: isCalendarPending, error: calendarDisconnectError } = useCalendarDisconnect();
  const showCalendarConnectError = useCalendarConnectErrorFromUrl();
  const { dashboard } = useDashboard();

  const isConnected = user?.health_connected ?? false;
  const isCalendarConnected = user?.calendar_connected ?? false;
  const healthError = dashboard?.health_error;

  const connectors: ConnectorConfig[] = [
    {
      name: t("googleHealth"),
      iconSrc: "/google_health_app_logo.svg",
      isConnected,
      connectUrl: HEALTH_CONNECT_URL,
      onDisconnect: disconnect,
      isDisconnecting: isPending,
      errorDetail: healthError ? { message: healthError.message, actionHref: healthError.redirect_uri, actionLabel: t("healthErrorAction") } : null,
    },
    {
      name: t("googleCalendar"),
      iconSrc: "/google_calendar-logo.svg",
      isConnected: isCalendarConnected,
      connectUrl: CALENDAR_CONNECT_URL,
      onDisconnect: disconnectCalendar,
      isDisconnecting: isCalendarPending,
    },
  ];

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[720px] lg:px-0 lg:py-9">
      <div className="mb-5 lg:mb-[26px]">
        <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-[30px]">{t("title")}</div>
        <div className="mt-1 text-[13px] text-muted lg:mt-1.5 lg:text-sm">{t("subtitle")}</div>
      </div>

      {(showConnectError || disconnectError) && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">{t("connectFailed")}</div>}
      {(showCalendarConnectError || calendarDisconnectError) && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">{t("connectFailedCalendar")}</div>}

      <div className="flex flex-col gap-2.5 lg:gap-3">
        {connectors.map((connector) => (
          <ConnectorCard key={connector.name} {...connector} />
        ))}
      </div>
    </div>
  );
}
