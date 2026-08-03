"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Card } from "@/components/ui/card";
import { mockConnectors, type Connector } from "@/lib/mock-data";

const CONNECT_DELAY_MS = 1400;

export function ConnectorsScreen() {
  const t = useTranslations("connectors");
  const [connectors, setConnectors] = useState<Connector[]>(mockConnectors);

  function toggleConnector(id: string) {
    const target = connectors.find((c) => c.id === id);
    if (!target) return;

    if (target.status === "connected") {
      // In production: revoke token server-side, then clear local state.
      setConnectors((prev) =>
        prev.map((c) => (c.id === id ? { ...c, status: "disconnected" } : c))
      );
      return;
    }

    // In production: open OAuth consent (redirect or popup) for this provider.
    setConnectors((prev) => prev.map((c) => (c.id === id ? { ...c, status: "pending" } : c)));
    setTimeout(() => {
      setConnectors((prev) =>
        prev.map((c) => (c.id === id ? { ...c, status: "connected" } : c))
      );
    }, CONNECT_DELAY_MS);
  }

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[720px] lg:px-0 lg:py-9">
      <div className="mb-5 lg:mb-[26px]">
        <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-[30px]">
          {t("title")}
        </div>
        <div className="mt-1 text-[13px] text-muted lg:mt-1.5 lg:text-sm">{t("subtitle")}</div>
      </div>

      <div className="flex flex-col gap-2.5 lg:gap-3">
        {connectors.map((c) => (
          <Card
            key={c.id}
            className="flex-row items-center justify-between gap-3 rounded-2xl p-[14px_16px] lg:gap-[14px] lg:px-5 lg:py-[18px]"
          >
            <div className="flex min-w-0 items-center gap-3 lg:gap-[14px]">
              <div
                className="flex h-[38px] w-[38px] flex-none items-center justify-center rounded-[10px] text-[13px] font-semibold lg:h-[42px] lg:w-[42px] lg:text-sm"
                style={{ background: c.tileBg, color: c.tileColor }}
              >
                {c.initials}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-primary lg:text-[15px]">{c.name}</div>
                <div
                  className="text-xs lg:text-[13px]"
                  style={{
                    color:
                      c.status === "connected"
                        ? "var(--color-status-connected)"
                        : c.status === "pending"
                          ? "var(--color-status-pending)"
                          : "var(--color-status-disconnected)",
                  }}
                >
                  {c.status === "connected"
                    ? t("connected")
                    : c.status === "pending"
                      ? t("connecting")
                      : t("notConnected")}
                </div>
                <div className="mt-0.5 text-[11px] text-disclaimer lg:text-xs">{c.scope}</div>
              </div>
            </div>

            {c.status === "connected" && (
              <button
                onClick={() => toggleConnector(c.id)}
                className="flex-none cursor-pointer px-1 py-1.5 text-xs font-semibold text-danger lg:text-[13px]"
              >
                {t("disconnect")}
              </button>
            )}
            {c.status === "pending" && (
              <div className="flex-none px-1 py-1.5 text-xs font-semibold text-muted lg:text-[13px]">
                {t("connecting")}
              </div>
            )}
            {c.status === "disconnected" && (
              <button
                onClick={() => toggleConnector(c.id)}
                className="h-8 flex-none cursor-pointer rounded-full border border-primary bg-card px-3.5 text-xs font-semibold text-primary lg:h-9 lg:px-[18px] lg:text-[13px]"
              >
                {t("connect")}
              </button>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
