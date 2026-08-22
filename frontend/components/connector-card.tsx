"use client";

import { useTranslations } from "next-intl";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type ConnectorErrorDetail = {
  message: string;
  actionHref?: string;
  actionLabel?: string;
};

export type ConnectorConfig = {
  name: string;
  iconSrc: string;
  isConnected: boolean;
  connectUrl: string;
  onDisconnect: () => void;
  isDisconnecting: boolean;
  errorDetail?: ConnectorErrorDetail | null;
};

export function ConnectorCard({ name, iconSrc, isConnected, connectUrl, onDisconnect, isDisconnecting, errorDetail }: ConnectorConfig) {
  const t = useTranslations("connectors");

  return (
    <Card className="flex-row items-center justify-between gap-4 rounded-2xl p-4 lg:gap-5 lg:px-6 lg:py-5">
      <div className="flex min-w-0 items-center gap-4 lg:gap-5">
        <div className="flex h-12 w-12 flex-none items-center justify-center rounded-xl p-2.5 lg:h-14 lg:w-14" style={{ background: "var(--color-icon-tile)" }}>
          <img src={iconSrc} alt="" className="h-full w-full object-contain" />
        </div>
        <div className="min-w-0">
          <div className="text-base font-semibold text-primary lg:text-lg">{name}</div>
          <div
            className="text-sm lg:text-sm"
            style={{
              color: isConnected ? "var(--color-status-connected)" : "var(--color-status-disconnected)",
            }}
          >
            {isConnected ? t("connected") : t("notConnected")}
          </div>
          {isConnected && errorDetail && (
            <div className="mt-1 text-xs lg:text-[13px]">
              {errorDetail.message}
              {errorDetail.actionHref && (
                <>
                  {" "}
                  <a href={errorDetail.actionHref} target="_blank" rel="noopener noreferrer" className="underline">
                    {errorDetail.actionLabel}
                  </a>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {isConnected ? (
        <Button variant="ghost" onClick={onDisconnect} disabled={isDisconnecting} className="flex-none text-danger hover:bg-danger/10 hover:text-danger">
          {t("disconnect")}
        </Button>
      ) : (
        <a href={connectUrl} className={cn(buttonVariants({ variant: "outline" }), "flex-none rounded-full")}>
          {t("connect")}
        </a>
      )}
    </Card>
  );
}
