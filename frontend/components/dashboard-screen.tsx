"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { mockGoals, mockRecentRuns, mockWeekGoalPct, mockWeekStats } from "@/lib/mock-data";

export function DashboardScreen({ locale }: { locale: string }) {
  const t = useTranslations("dashboard");
  const { user } = useAuth();
  const displayName = user?.name ?? user?.email ?? "";
  const initials = displayName
    ? displayName
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((word) => word[0]?.toUpperCase())
        .join("")
    : "?";
  const today = new Date().toLocaleDateString(locale, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:px-[44px] lg:py-9">
      <div className="mb-[22px] flex items-center justify-between lg:mb-[26px] lg:items-end">
        <div>
          <div className="text-[13px] text-muted lg:text-sm">{today}</div>
          <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-[30px]">
            {t("thisWeek")}
          </div>
        </div>
        <Link
          href={`/${locale}/profile`}
          className="flex h-[38px] w-[38px] items-center justify-center rounded-xl bg-avatar-bg text-[13px] font-semibold text-primary lg:hidden"
        >
          {initials}
        </Link>
      </div>

      <div className="lg:mb-7 lg:grid lg:grid-cols-[1.3fr_1fr] lg:gap-5">
        <div className="mb-4 flex flex-col gap-4 rounded-[20px] bg-primary p-[22px] lg:mb-0 lg:gap-[18px] lg:p-7">
          <div className="flex justify-between">
            {mockWeekStats.map((stat) => (
              <div key={stat.label} className="flex flex-col gap-1">
                <div className="font-mono text-[26px] font-bold text-primary-foreground lg:text-[32px]">
                  {stat.value}
                </div>
                <div className="text-[11px] font-medium uppercase text-stat-label">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
          <div className="h-px bg-primary-foreground/10" />
          <div className="flex items-center justify-between">
            <div className="text-[13px] text-goal-label lg:text-sm">
              {t("goal", { distance: 30 })}
            </div>
            <div className="font-mono text-[13px] font-semibold text-primary-foreground lg:text-sm">
              {mockWeekGoalPct}%
            </div>
          </div>
          <div className="h-[6px] w-full overflow-hidden rounded-full bg-primary-foreground/[0.14]">
            <div
              className="h-full rounded-full bg-accent-light"
              style={{ width: `${mockWeekGoalPct}%` }}
            />
          </div>
        </div>

        <div className="hidden rounded-[20px] border border-border bg-card p-6 lg:flex lg:flex-col lg:gap-[14px]">
          <div className="text-[13px] font-semibold uppercase tracking-[0.5px] text-muted">
            {t("goals")}
          </div>
          {mockGoals.map((goal) => (
            <div key={goal.title} className="flex flex-col gap-2">
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
            </div>
          ))}
        </div>
      </div>

      <div className="mb-2.5 mt-5 text-[13px] font-semibold uppercase text-muted lg:mt-0">
        {t("recentRuns")}
      </div>
      <div className="flex flex-col gap-2.5 lg:grid lg:grid-cols-2 lg:gap-3">
        {mockRecentRuns.map((run) => (
          <Card
            key={`${run.day}-${run.time}`}
            className="flex flex-row items-center justify-between rounded-[16px] p-4 lg:px-5 lg:py-[18px]"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-icon-tile lg:h-[38px] lg:w-[38px]">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path d="M13 3L4 14h7l-1 7 9-11h-7l1-7z" fill="#5C7A5E" />
                </svg>
              </div>
              <div>
                <div className="text-sm font-semibold text-primary">{run.day}</div>
                <div className="text-xs text-muted-light">{run.time}</div>
              </div>
            </div>
            <div className="text-right font-mono">
              <div className="text-sm font-semibold text-primary">{run.distance}</div>
              <div className="text-xs text-muted-light">{run.pace}</div>
            </div>
          </Card>
        ))}
      </div>

      <div className="mb-2.5 mt-[22px] text-[13px] font-semibold uppercase text-muted lg:hidden">
        {t("goals")}
      </div>
      <div className="flex flex-col gap-2.5 lg:hidden">
        {mockGoals.map((goal) => (
          <Card key={goal.title} className="flex flex-col gap-2 rounded-[16px] p-3.5">
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
