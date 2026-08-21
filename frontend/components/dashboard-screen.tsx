"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { Avatar } from "@/components/avatar";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useDashboard } from "@/hooks/use-dashboard";
import { usePreferences } from "@/hooks/use-preferences";
import { usePlanRun } from "@/hooks/use-plan-run";
import { CALENDAR_CONNECT_URL } from "@/hooks/use-calendar-connector";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";
import type { RecentRun, UpcomingRun } from "@/lib/dashboard-api";

function formatPace(paceMinPerKm: number | null): string {
  if (paceMinPerKm === null) return "–";
  const minutes = Math.floor(paceMinPerKm);
  const seconds = Math.round((paceMinPerKm - minutes) * 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}/km`;
}

function formatRun(run: RecentRun, locale: string) {
  const date = new Date(run.date);
  return {
    day: date.toLocaleDateString(locale, { weekday: "long" }),
    time: date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" }),
    distance: `${run.distance_km} km`,
    pace: formatPace(run.pace_min_per_km),
  };
}

function formatUpcomingRun(run: UpcomingRun, locale: string) {
  const date = new Date(run.start.dateTime);
  return {
    id: run.id,
    summary: run.summary,
    day: date.toLocaleDateString(locale, { weekday: "long", month: "short", day: "numeric" }),
    time: date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" }),
    forecast: run.forecast,
  };
}

type PlanRunModalProps = {
  onClose: () => void;
};

function PlanRunModal({ onClose }: PlanRunModalProps) {
  const t = useTranslations("dashboard");
  const planRun = usePlanRun();
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [duration, setDuration] = useState("30");
  const [notes, setNotes] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    planRun.mutate(
      {
        title,
        start_time: `${date}T${time}:00`,
        duration_minutes: Number(duration),
        notes,
      },
      { onSuccess: onClose }
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 p-4">
      <Card className="w-full max-w-sm rounded-2xl p-5">
        <div className="mb-4 text-base font-semibold text-primary">{t("planRunTitle")}</div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunName")}
            <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunDate")}
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunTime")}
            <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunDuration")}
            <Input
              type="number"
              min={1}
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("planRunNotes")}
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>

          {planRun.isError && <div className="text-xs text-danger">{t("planRunError")}</div>}

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("planRunCancel")}
            </Button>
            <Button type="submit" disabled={planRun.isPending}>
              {t("planRunSubmit")}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

export function DashboardScreen({ locale }: { locale: string }) {
  const t = useTranslations("dashboard");
  const tConnectors = useTranslations("connectors");
  const { user } = useAuth();
  const { dashboard, isLoading } = useDashboard();
  const { preferences } = usePreferences();
  const [isPlanRunOpen, setIsPlanRunOpen] = useState(false);
  const today = new Date().toLocaleDateString(locale, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });

  const weeklyGoalKm = preferences?.weekly_goal_km ?? 30;
  const weekStats = [
    { value: isLoading ? "–" : String(dashboard?.weekly_stats?.total_distance_km ?? 0), label: "km" },
    {
      value: isLoading
        ? "–"
        : formatPace(dashboard?.weekly_stats?.avg_pace_min_per_km ?? null).replace("/km", ""),
      label: "avg /km",
    },
    { value: isLoading ? "–" : String(dashboard?.weekly_stats?.run_count ?? 0), label: "runs" },
  ];
  const weekGoalPct = dashboard?.weekly_stats
    ? Math.min(100, Math.round((dashboard.weekly_stats.total_distance_km / weeklyGoalKm) * 100))
    : 0;
  const recentRuns = dashboard?.recent_runs.map((run) => formatRun(run, locale)) ?? [];
  const calendarConnected = dashboard?.calendar_connected ?? false;
  const upcomingRuns = dashboard?.upcoming_runs?.map((run) => formatUpcomingRun(run, locale)) ?? [];
  const currentWeather = dashboard?.current_weather ?? null;

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:px-[44px] lg:py-9">
      <div className="mb-[22px] flex items-center justify-between lg:mb-[26px] lg:items-end">
        <div>
          <div className="text-[13px] text-muted lg:text-sm">{today}</div>
          <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-[30px]">
            {t("thisWeek")}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {calendarConnected && (
            <Button variant="outline" className="rounded-full" onClick={() => setIsPlanRunOpen(true)}>
              {t("planARun")}
            </Button>
          )}
          <Link href={`/${locale}/profile`} className="lg:hidden">
            <Avatar
              user={{ name: user?.name ?? null, avatar_url: user?.avatar_url ?? null }}
              size="md"
              className="h-[38px] w-[38px] rounded-xl"
            />
          </Link>
        </div>
      </div>

      {isPlanRunOpen && <PlanRunModal onClose={() => setIsPlanRunOpen(false)} />}

      {currentWeather && (
        <Card className="mb-5 flex flex-row items-center justify-between rounded-[16px] p-4 lg:mb-7 lg:px-5 lg:py-[18px]">
          <div>
            <div className="text-[13px] font-semibold uppercase text-muted">{t("weather")}</div>
            <div className="text-sm text-primary">
              {currentWeather.temp}°C, {currentWeather.condition}
            </div>
          </div>
          <div className="text-right text-xs text-muted-light">
            <div>Feels like {currentWeather.feels_like}°C</div>
            <div>
              Humidity {currentWeather.humidity}% · Wind {currentWeather.wind} km/h
            </div>
          </div>
        </Card>
      )}

      <div className="lg:mb-7">
        <div className="mb-4 flex flex-col gap-4 rounded-[20px] bg-primary p-[22px] lg:mb-0 lg:gap-[18px] lg:p-7">
          <div className="flex justify-between">
            {weekStats.map((stat) => (
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
              {t("goal", { distance: weeklyGoalKm })}
            </div>
            <div className="font-mono text-[13px] font-semibold text-primary-foreground lg:text-sm">
              {weekGoalPct}%
            </div>
          </div>
          <div className="h-[6px] w-full overflow-hidden rounded-full bg-primary-foreground/[0.14]">
            <div
              className="h-full rounded-full bg-accent-light"
              style={{ width: `${weekGoalPct}%` }}
            />
          </div>
        </div>
      </div>

      <div className="mb-2.5 mt-5 text-[13px] font-semibold uppercase text-muted lg:mt-0">
        {t("recentRuns")}
      </div>
      <div className="flex flex-col gap-2.5 lg:grid lg:grid-cols-2 lg:gap-3">
        {recentRuns.map((run) => (
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

      <div className="mb-2.5 mt-5 text-[13px] font-semibold uppercase text-muted lg:mt-7">
        {t("upcomingRuns")}
      </div>
      {calendarConnected ? (
        <div className="flex flex-col gap-2.5 lg:grid lg:grid-cols-2 lg:gap-3">
          {upcomingRuns.map((run) => (
            <Card
              key={run.id}
              className="flex flex-row items-center justify-between rounded-[16px] p-4 lg:px-5 lg:py-[18px]"
            >
              <div>
                <div className="text-sm font-semibold text-primary">{run.summary}</div>
                <div className="text-xs text-muted-light">
                  {run.day}, {run.time}
                </div>
              </div>
              {run.forecast && (
                <div className="text-right text-xs text-muted-light">
                  {run.forecast.temp}°C, {run.forecast.condition}
                </div>
              )}
            </Card>
          ))}
        </div>
      ) : (
        <Card className="rounded-[16px] p-4 text-sm text-muted lg:px-5 lg:py-[18px]">
          {t("connectCalendarPrompt")}{" "}
          <a href={CALENDAR_CONNECT_URL} className={cn(buttonVariants({ variant: "outline" }), "ml-2 rounded-full")}>
            {tConnectors("connect")}
          </a>
        </Card>
      )}
    </div>
  );
}
