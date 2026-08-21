"use client";

import { useTranslations } from "next-intl";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { useDashboard } from "@/hooks/use-dashboard";
import { cn } from "@/lib/utils";
import { HEALTH_CONNECT_URL, useHealthConnectErrorFromUrl, useHealthDisconnect } from "@/hooks/use-health-connector";
import { CALENDAR_CONNECT_URL, useCalendarConnectErrorFromUrl, useCalendarDisconnect } from "@/hooks/use-calendar-connector";

export function ConnectorsScreen() {
  const t = useTranslations("connectors");
  const { user } = useAuth();
  const { disconnect, isPending, error: disconnectError } = useHealthDisconnect();
  const showConnectError = useHealthConnectErrorFromUrl();
  const {
    disconnect: disconnectCalendar,
    isPending: isCalendarPending,
    error: calendarDisconnectError,
  } = useCalendarDisconnect();
  const showCalendarConnectError = useCalendarConnectErrorFromUrl();
  const { dashboard } = useDashboard();

  const isConnected = user?.health_connected ?? false;
  const isCalendarConnected = user?.calendar_connected ?? false;
  const healthError = dashboard?.health_error;

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[720px] lg:px-0 lg:py-9">
      <div className="mb-5 lg:mb-[26px]">
        <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-[30px]">{t("title")}</div>
        <div className="mt-1 text-[13px] text-muted lg:mt-1.5 lg:text-sm">{t("subtitle")}</div>
      </div>

      {(showConnectError || disconnectError) && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">{t("connectFailed")}</div>}
      {(showCalendarConnectError || calendarDisconnectError) && (
        <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">{t("connectFailedCalendar")}</div>
      )}

      <div className="flex flex-col gap-2.5 lg:gap-3">
        <Card className="flex-row items-center justify-between gap-4 rounded-2xl p-4 lg:gap-5 lg:px-6 lg:py-5">
          <div className="flex min-w-0 items-center gap-4 lg:gap-5">
            <div className="flex h-12 w-12 flex-none items-center justify-center rounded-xl p-2.5 lg:h-14 lg:w-14" style={{ background: "var(--color-icon-tile)" }}>
              <img src="/Google_Health_app_logo.svg" alt="" className="h-full w-full object-contain" />
            </div>
            <div className="min-w-0">
              <div className="text-base font-semibold text-primary lg:text-lg">Google Health</div>
              <div
                className="text-sm lg:text-sm"
                style={{
                  color: isConnected ? "var(--color-status-connected)" : "var(--color-status-disconnected)",
                }}
              >
                {isConnected ? t("connected") : t("notConnected")}
              </div>
              {isConnected && healthError && (
                <div className="mt-1 text-xs lg:text-[13px]">
                  {healthError.message}
                  {healthError.redirect_uri && (
                    <>
                      {" "}
                      <a href={healthError.redirect_uri} target="_blank" rel="noopener noreferrer" className="underline">
                        {t("healthErrorAction")}
                      </a>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

          {isConnected ? (
            <Button variant="ghost" onClick={() => disconnect()} disabled={isPending} className="flex-none text-danger hover:bg-danger/10 hover:text-danger">
              {t("disconnect")}
            </Button>
          ) : (
            <a href={HEALTH_CONNECT_URL} className={cn(buttonVariants({ variant: "outline" }), "flex-none rounded-full")}>
              {t("connect")}
            </a>
          )}
        </Card>

        <Card className="flex-row items-center justify-between gap-4 rounded-2xl p-4 lg:gap-5 lg:px-6 lg:py-5">
          <div className="flex min-w-0 items-center gap-4 lg:gap-5">
            <div className="flex h-12 w-12 flex-none items-center justify-center rounded-xl p-2.5 lg:h-14 lg:w-14" style={{ background: "var(--color-icon-tile)" }}>
              <img src="/calendar-icon.svg" alt="" className="h-full w-full object-contain" />
            </div>
            <div className="min-w-0">
              <div className="text-base font-semibold text-primary lg:text-lg">Google Calendar</div>
              <div
                className="text-sm lg:text-sm"
                style={{
                  color: isCalendarConnected ? "var(--color-status-connected)" : "var(--color-status-disconnected)",
                }}
              >
                {isCalendarConnected ? t("connected") : t("notConnected")}
              </div>
            </div>
          </div>

          {isCalendarConnected ? (
            <Button
              variant="ghost"
              onClick={() => disconnectCalendar()}
              disabled={isCalendarPending}
              className="flex-none text-danger hover:bg-danger/10 hover:text-danger"
            >
              {t("disconnect")}
            </Button>
          ) : (
            <a href={CALENDAR_CONNECT_URL} className={cn(buttonVariants({ variant: "outline" }), "flex-none rounded-full")}>
              {t("connect")}
            </a>
          )}
        </Card>
      </div>
    </div>
  );
}
