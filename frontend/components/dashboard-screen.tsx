"use client";

import { useTranslations } from "next-intl";

import { Card } from "@/components/ui/card";
import { mockGoals, mockRecentRuns, mockWeekStats } from "@/lib/mock-data";

export function DashboardScreen() {
  const t = useTranslations("dashboard");

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5">
      <div className="mb-[22px] text-2xl font-bold text-primary">{t("thisWeek")}</div>

      <div className="mb-4 flex flex-col gap-4 rounded-[20px] bg-primary p-[22px]">
        <div className="flex justify-between">
          {mockWeekStats.map((stat) => (
            <div key={stat.label} className="flex flex-col gap-1">
              <div className="font-mono text-[26px] font-bold text-primary-foreground">
                {stat.value}
              </div>
              <div className="text-[11px] font-medium uppercase text-muted-light">
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mb-2.5 mt-5 text-[13px] font-semibold uppercase text-muted">
        {t("recentRuns")}
      </div>
      <div className="flex flex-col gap-2.5">
        {mockRecentRuns.map((run) => (
          <Card key={`${run.day}-${run.time}`} className="flex items-center justify-between p-4">
            <div>
              <div className="text-sm font-semibold text-primary">{run.day}</div>
              <div className="text-xs text-muted-light">{run.time}</div>
            </div>
            <div className="text-right font-mono">
              <div className="text-sm font-semibold text-primary">{run.distance}</div>
              <div className="text-xs text-muted-light">{run.pace}</div>
            </div>
          </Card>
        ))}
      </div>

      <div className="mb-2.5 mt-[22px] text-[13px] font-semibold uppercase text-muted">
        {t("goals")}
      </div>
      <div className="flex flex-col gap-2.5">
        {mockGoals.map((goal) => (
          <Card key={goal.title} className="flex flex-col gap-2 p-3.5">
            <div className="flex items-center justify-between">
              <div className="text-[13px] font-semibold text-primary">{goal.title}</div>
              <div className="font-mono text-xs font-semibold text-accent">{goal.pct}%</div>
            </div>
            <div className="h-[5px] w-full overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${goal.pct}%` }}
              />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
