"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Card } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { mockUser } from "@/lib/mock-data";

const GOAL_STEP_KM = 5;
const MIN_GOAL_KM = 5;
const KM_TO_MI = 0.621;

export function ProfileScreen({ locale }: { locale: string }) {
  const t = useTranslations("profile");
  const router = useRouter();
  const queryClient = useQueryClient();

  const [weeklyGoalKm, setWeeklyGoalKm] = useState(30);
  const [units, setUnits] = useState<"km" | "mi">("km");
  const [notifications, setNotifications] = useState(true);

  const logOut = useMutation({
    mutationFn: () => apiFetch("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      queryClient.setQueryData(["auth", "me"], null);
      router.push(`/${locale}`);
    },
  });

  const weeklyGoalText =
    units === "km" ? `${weeklyGoalKm} km` : `${Math.round(weeklyGoalKm * KM_TO_MI)} mi`;

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[560px] lg:px-0 lg:py-9">
      <div className="mb-6 flex items-center gap-3.5 lg:mb-7 lg:gap-4">
        <div className="flex h-14 w-14 flex-none items-center justify-center rounded-full bg-avatar-bg text-lg font-semibold text-primary lg:h-16 lg:w-16 lg:text-xl">
          {mockUser.initials}
        </div>
        <div>
          <div className="text-lg font-bold text-primary lg:text-[22px]">{mockUser.name}</div>
          <div className="text-[13px] text-muted lg:text-sm">{mockUser.email}</div>
        </div>
      </div>

      <div className="flex flex-col gap-2.5 lg:gap-3">
        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("weeklyGoal")}</div>
          <div className="flex items-center gap-3 lg:gap-3.5">
            <button
              onClick={() => setWeeklyGoalKm((v) => Math.max(MIN_GOAL_KM, v - GOAL_STEP_KM))}
              aria-label={t("decreaseGoal")}
              className="h-7 w-7 cursor-pointer rounded-full border border-border bg-surface text-[15px] font-semibold text-primary lg:h-8 lg:w-8 lg:text-base"
            >
              –
            </button>
            <div className="min-w-[52px] text-center font-mono text-sm font-semibold text-primary lg:min-w-[60px] lg:text-[15px]">
              {weeklyGoalText}
            </div>
            <button
              onClick={() => setWeeklyGoalKm((v) => v + GOAL_STEP_KM)}
              aria-label={t("increaseGoal")}
              className="h-7 w-7 cursor-pointer rounded-full border border-border bg-surface text-[15px] font-semibold text-primary lg:h-8 lg:w-8 lg:text-base"
            >
              +
            </button>
          </div>
        </Card>

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("units")}</div>
          <button
            onClick={() => setUnits((v) => (v === "km" ? "mi" : "km"))}
            className="h-[30px] cursor-pointer rounded-full border border-border bg-surface px-3.5 text-xs font-semibold text-primary lg:h-[34px] lg:px-4 lg:text-[13px]"
          >
            {units === "km" ? t("kilometers") : t("miles")}
          </button>
        </Card>

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("notifications")}</div>
          <button
            onClick={() => setNotifications((v) => !v)}
            aria-pressed={notifications}
            aria-label={t("notifications")}
            className="relative h-[27px] w-[46px] flex-none cursor-pointer rounded-full"
            style={{ background: notifications ? "var(--color-accent)" : "var(--color-border)" }}
          >
            <span
              className="absolute top-[3px] h-[21px] w-[21px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.2)] transition-[left]"
              style={{ left: notifications ? "22px" : "3px" }}
            />
          </button>
        </Card>

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("memberSince")}</div>
          <div className="text-[13px] text-muted-light">{mockUser.memberSince}</div>
        </Card>
      </div>

      <button
        onClick={() => logOut.mutate()}
        disabled={logOut.isPending}
        className="mt-6 h-[50px] w-full cursor-pointer rounded-2xl border border-danger-border bg-danger-bg text-sm font-semibold text-danger disabled:cursor-not-allowed disabled:opacity-60 lg:mt-7 lg:h-[52px]"
      >
        {t("logOut")}
      </button>
    </div>
  );
}
