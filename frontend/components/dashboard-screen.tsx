"use client";

import { useState } from "react";
import { MapPin, Zap } from "lucide-react";
import { useTranslations } from "next-intl";

import { PlanRunModal } from "@/components/plan-run-modal";
import { RunCard } from "@/components/run-card";
import { SectionLabel } from "@/components/section-label";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useDashboard } from "@/hooks/use-dashboard";
import { useLocationName } from "@/hooks/use-location-name";
import { usePreferences } from "@/hooks/use-preferences";
import type { RecentRun, UpcomingRun } from "@/lib/dashboard-api";
import { computeGoalProgress } from "@/lib/goal-progress";

function formatPace(paceMinPerKm: number | null): string {
  if (paceMinPerKm === null) return "–";
  const minutes = Math.floor(paceMinPerKm);
  const seconds = Math.round((paceMinPerKm - minutes) * 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}/km`;
}

function formatRun(run: RecentRun, locale: string) {
  const date = new Date(run.date);
  return {
    id: run.date,
    day: date.toLocaleDateString(locale, { weekday: "long", month: "short", day: "numeric" }),
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

function formatHour(isoTime: string, locale: string): string {
  return new Date(isoTime).toLocaleTimeString(locale, { hour: "numeric" });
}

function insightKey(humidity: number, aqi: number): "insightPoorAir" | "insightHumid" | "insightGood" {
  if (aqi > 100) return "insightPoorAir";
  if (humidity > 70) return "insightHumid";
  return "insightGood";
}

export function DashboardScreen({ locale }: { locale: string }) {
  const t = useTranslations("dashboard");
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
      value: isLoading ? "–" : formatPace(dashboard?.weekly_stats?.avg_pace_min_per_km ?? null).replace("/km", ""),
      label: "avg /km",
    },
    { value: isLoading ? "–" : String(dashboard?.weekly_stats?.run_count ?? 0), label: "runs" },
  ];
  const { goalPct: weekGoalPct } = computeGoalProgress(dashboard?.weekly_stats?.total_distance_km ?? 0, weeklyGoalKm);
  const recentRuns = dashboard?.recent_runs.map((run) => formatRun(run, locale)) ?? [];
  const calendarConnected = dashboard?.calendar_connected ?? false;
  const upcomingRuns = dashboard?.upcoming_runs?.map((run) => formatUpcomingRun(run, locale)) ?? [];
  const currentWeather = dashboard?.current_weather ?? null;
  const locationName = useLocationName(preferences?.location_lat, preferences?.location_lon);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5 lg:px-11 lg:py-9">
      <div className="mb-6 flex items-center justify-between lg:mb-7 lg:items-end">
        <div>
          <div className="text-sm text-muted">{today}</div>
          <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-3xl">{t("thisWeek")}</div>
        </div>
        <div className="flex items-center gap-3">
          {calendarConnected && (
            <Button className="rounded-full px-4" onClick={() => setIsPlanRunOpen(true)}>
              {t("planARun")}
            </Button>
          )}
        </div>
      </div>

      {isPlanRunOpen && <PlanRunModal onClose={() => setIsPlanRunOpen(false)} />}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 lg:gap-7">
        <div className="flex flex-col gap-4 rounded-2xl bg-primary p-6 lg:gap-5 lg:p-7">
          <div className="flex justify-between">
            {weekStats.map((stat) => (
              <div key={stat.label} className="flex flex-col gap-1">
                <div className="font-mono text-2xl font-bold text-primary-foreground lg:text-3xl">{stat.value}</div>
                <div className="text-xs font-medium uppercase text-stat-label">{stat.label}</div>
              </div>
            ))}
          </div>
          <div className="h-px bg-primary-foreground/10" />
          <div className="flex items-center justify-between">
            <div className="text-sm text-goal-label">{t("goal", { distance: weeklyGoalKm })}</div>
            <div className="font-mono text-sm font-semibold text-primary-foreground">{weekGoalPct}%</div>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-primary-foreground/[0.14]">
            <div className="h-full rounded-full bg-accent-light" style={{ width: `${weekGoalPct}%` }} />
          </div>
        </div>

        {currentWeather && (
          <Card className="flex flex-col gap-2 rounded-2xl p-6 lg:p-7">
            <div className="flex items-start justify-between">
              <SectionLabel>{t("weather")}</SectionLabel>
              {locationName && (
                <div className="flex items-center gap-1 text-xs text-muted-light">
                  <MapPin size={16} />
                  <span>{locationName}</span>
                </div>
              )}
            </div>
            <div>
              <div className="text-3xl font-bold text-primary">{currentWeather.temp}°</div>
              <div className="text-sm text-muted-light">
                {currentWeather.condition} · {t("feelsLike", { temp: currentWeather.feels_like })}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2.5">
              <div className="rounded-xl bg-icon-tile p-3">
                <div className="text-xs font-medium uppercase text-muted">{t("humidity")}</div>
                <div className="text-sm font-semibold text-primary">{currentWeather.humidity}%</div>
              </div>
              <div className="rounded-xl bg-icon-tile p-3">
                <div className="text-xs font-medium uppercase text-muted">{t("wind")}</div>
                <div className="text-sm font-semibold text-primary">{currentWeather.wind} km/h</div>
              </div>
              <div className="rounded-xl bg-icon-tile p-3">
                <div className="text-xs font-medium uppercase text-muted">{t("aqi")}</div>
                <div className="text-sm font-semibold text-primary">{currentWeather.aqi}</div>
              </div>
            </div>

            <div className="rounded-xl bg-icon-tile p-3 text-xs text-primary">{t(insightKey(currentWeather.humidity, currentWeather.aqi))}</div>

            {currentWeather.hourly.length > 0 && (
              <div className="flex justify-between px-2">
                {currentWeather.hourly.map((entry) => (
                  <div key={entry.time} className="flex flex-col items-center gap-1 text-xs">
                    <div className="text-muted-light">{formatHour(entry.time, locale)}</div>
                    <div className="font-mono font-semibold text-primary">{entry.temp}°</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-x-7 gap-y-5 lg:mt-7 lg:grid-cols-2">
        {recentRuns.length > 0 && (
          <div>
            <SectionLabel className="mb-2.5">{t("recentRuns")}</SectionLabel>
            <div className="flex flex-col gap-2.5">
              {recentRuns.map((run) => (
                <RunCard
                  key={run.id}
                  title={run.day}
                  subtitle={run.time}
                  leading={
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-icon-tile lg:h-10 lg:w-10">
                      <Zap size={16} fill="#5C7A5E" stroke="none" />
                    </div>
                  }
                  trailing={
                    <div className="text-right font-mono">
                      <div className="text-sm font-semibold text-primary">{run.distance}</div>
                      <div className="text-xs text-muted-light">{run.pace}</div>
                    </div>
                  }
                />
              ))}
            </div>
          </div>
        )}

        {calendarConnected && upcomingRuns.length > 0 && (
          <div>
            <SectionLabel className="mb-2.5">{t("upcomingRuns")}</SectionLabel>
            <div className="flex flex-col gap-2.5">
              {upcomingRuns.map((run) => (
                <RunCard
                  key={run.id}
                  title={run.summary}
                  subtitle={`${run.day}, ${run.time}`}
                  trailing={
                    run.forecast && (
                      <div className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                        {run.forecast.temp}° {run.forecast.condition}
                      </div>
                    )
                  }
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
