"use client";

import { useState } from "react";
import { MapPin, Zap } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { Avatar } from "@/components/avatar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useDashboard } from "@/hooks/use-dashboard";
import { useLocationName } from "@/hooks/use-location-name";
import { usePreferences } from "@/hooks/use-preferences";
import { usePlanRun } from "@/hooks/use-plan-run";
import { useAuth } from "@/lib/auth-context";
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

function upcomingRunTint(summary: string): string {
  const lower = summary.toLowerCase();
  if (lower.includes("race")) return "bg-badge-pink";
  if (lower.includes("interval") || lower.includes("speed") || lower.includes("tempo")) return "bg-badge-periwinkle";
  if (lower.includes("recovery") || lower.includes("easy")) return "bg-badge-tan";
  if (lower.includes("long")) return "bg-badge-blue";
  return "bg-card";
}

function formatUpcomingRun(run: UpcomingRun, locale: string) {
  const date = new Date(run.start.dateTime);
  return {
    id: run.id,
    summary: run.summary,
    day: date.toLocaleDateString(locale, { weekday: "long", month: "short", day: "numeric" }),
    time: date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" }),
    forecast: run.forecast,
    tint: upcomingRunTint(run.summary),
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
      { onSuccess: onClose },
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
            <Input type="number" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} required />
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
      value: isLoading ? "–" : formatPace(dashboard?.weekly_stats?.avg_pace_min_per_km ?? null).replace("/km", ""),
      label: "avg /km",
    },
    { value: isLoading ? "–" : String(dashboard?.weekly_stats?.run_count ?? 0), label: "runs" },
  ];
  const weekGoalPct = dashboard?.weekly_stats ? Math.min(100, Math.round((dashboard.weekly_stats.total_distance_km / weeklyGoalKm) * 100)) : 0;
  const recentRuns = dashboard?.recent_runs.map((run) => formatRun(run, locale)) ?? [];
  const calendarConnected = dashboard?.calendar_connected ?? false;
  const upcomingRuns = dashboard?.upcoming_runs?.map((run) => formatUpcomingRun(run, locale)) ?? [];
  const currentWeather = dashboard?.current_weather ?? null;
  const locationName = useLocationName(preferences?.location_lat, preferences?.location_lon);

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:px-[44px] lg:py-9">
      <div className="mb-[22px] flex items-center justify-between lg:mb-[26px] lg:items-end">
        <div>
          <div className="text-[13px] text-muted lg:text-sm">{today}</div>
          <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-[30px]">{t("thisWeek")}</div>
        </div>
        <div className="flex items-center gap-3">
          {calendarConnected && (
            <Button variant="outline" className="rounded-full" onClick={() => setIsPlanRunOpen(true)}>
              {t("planARun")}
            </Button>
          )}
          <Link href={`/${locale}/profile`} className="lg:hidden">
            <Avatar user={{ name: user?.name ?? null, avatar_url: user?.avatar_url ?? null }} size="md" className="h-[38px] w-[38px] rounded-xl" />
          </Link>
        </div>
      </div>

      {isPlanRunOpen && <PlanRunModal onClose={() => setIsPlanRunOpen(false)} />}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 lg:gap-7">
        <div className="flex flex-col gap-4 rounded-[20px] bg-primary p-[22px] lg:gap-[18px] lg:p-7">
          <div className="flex justify-between">
            {weekStats.map((stat) => (
              <div key={stat.label} className="flex flex-col gap-1">
                <div className="font-mono text-[26px] font-bold text-primary-foreground lg:text-[32px]">{stat.value}</div>
                <div className="text-[11px] font-medium uppercase text-stat-label">{stat.label}</div>
              </div>
            ))}
          </div>
          <div className="h-px bg-primary-foreground/10" />
          <div className="flex items-center justify-between">
            <div className="text-[13px] text-goal-label lg:text-sm">{t("goal", { distance: weeklyGoalKm })}</div>
            <div className="font-mono text-[13px] font-semibold text-primary-foreground lg:text-sm">{weekGoalPct}%</div>
          </div>
          <div className="h-[6px] w-full overflow-hidden rounded-full bg-primary-foreground/[0.14]">
            <div className="h-full rounded-full bg-accent-light" style={{ width: `${weekGoalPct}%` }} />
          </div>
        </div>

        {currentWeather && (
          <Card className="flex flex-col gap-2 rounded-[20px] p-[22px] lg:p-7">
            <div className="flex items-start justify-between">
              <div className="text-[13px] font-semibold uppercase text-muted">{t("weather")}</div>
              {locationName && (
                <div className="flex items-center gap-1 text-xs text-muted-light">
                  <MapPin size={16} />
                  <span>{locationName}</span>
                </div>
              )}
            </div>
            <div>
              <div className="text-[32px] font-bold text-primary">{currentWeather.temp}°</div>
              <div className="text-sm text-muted-light">
                {currentWeather.condition} · {t("feelsLike", { temp: currentWeather.feels_like })}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2.5">
              <div className="rounded-[12px] bg-icon-tile p-3">
                <div className="text-[10px] font-medium uppercase text-muted">{t("humidity")}</div>
                <div className="text-sm font-semibold text-primary">{currentWeather.humidity}%</div>
              </div>
              <div className="rounded-[12px] bg-icon-tile p-3">
                <div className="text-[10px] font-medium uppercase text-muted">{t("wind")}</div>
                <div className="text-sm font-semibold text-primary">{currentWeather.wind} km/h</div>
              </div>
              <div className="rounded-[12px] bg-icon-tile p-3">
                <div className="text-[10px] font-medium uppercase text-muted">{t("aqi")}</div>
                <div className="text-sm font-semibold text-primary">{currentWeather.aqi}</div>
              </div>
            </div>

            <div className="rounded-[12px] bg-icon-tile p-3 text-xs text-primary">{t(insightKey(currentWeather.humidity, currentWeather.aqi))}</div>

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
        <div>
          <div className="mb-2.5 text-[13px] font-semibold uppercase text-muted">{t("recentRuns")}</div>
          <div className="flex flex-col gap-2.5">
            {recentRuns.map((run) => (
              <Card key={`${run.day}-${run.time}`} className="flex flex-row items-center justify-between rounded-[16px] p-4 lg:px-5 lg:py-[18px]">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-icon-tile lg:h-[38px] lg:w-[38px]">
                    <Zap size={16} fill="#5C7A5E" stroke="none" />
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
        </div>

        {calendarConnected && (
          <div>
            <div className="mb-2.5 text-[13px] font-semibold uppercase text-muted">{t("upcomingRuns")}</div>
            <div className="flex flex-col gap-2.5">
              {upcomingRuns.map((run) => (
                <Card key={run.id} className={`flex flex-row items-center justify-between rounded-[16px] p-4 lg:px-5 lg:py-[18px] ${run.tint}`}>
                  <div>
                    <div className="text-sm font-semibold text-primary">{run.summary}</div>
                    <div className="text-xs text-muted-light">
                      {run.day}, {run.time}
                    </div>
                  </div>
                  {run.forecast && (
                    <div className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                      {run.forecast.temp}° {run.forecast.condition}
                    </div>
                  )}
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
