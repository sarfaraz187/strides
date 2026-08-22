"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera } from "lucide-react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Avatar } from "@/components/avatar";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { useDashboard } from "@/hooks/use-dashboard";
import { useLocationName } from "@/hooks/use-location-name";
import { usePreferences } from "@/hooks/use-preferences";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Preferences } from "@/lib/preferences-api";

const GOAL_STEP_KM = 1;
const MIN_GOAL_KM = 0;
const MAX_GOAL_KM = 50;
const KM_TO_MI = 0.621;

type LocationEditorProps = {
  onUseMyLocation: () => void;
  geoError: string | null;
};

function LocationEditor({ onUseMyLocation, geoError }: LocationEditorProps) {
  const t = useTranslations("profile");
  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={onUseMyLocation}
        className="h-8 w-fit cursor-pointer rounded-full border border-primary-foreground/25 bg-primary-foreground/10 px-3.5 text-xs font-semibold text-primary-foreground"
      >
        {t("useMyLocation")}
      </button>
      {geoError && <div className="text-xs text-danger">{geoError}</div>}
    </div>
  );
}

function PreferenceRow({ label, subtitle, children }: { label: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
      <div>
        <div className="text-sm font-semibold text-primary lg:text-[15px]">{label}</div>
        <div className="text-xs text-muted-light">{subtitle}</div>
      </div>
      {children}
    </div>
  );
}

export function ProfileScreen({ locale }: { locale: string }) {
  const t = useTranslations("profile");
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { preferences, isLoading, updateNow, updateDebounced, error } = usePreferences();
  const { dashboard } = useDashboard();
  const { user } = useAuth();
  const displayName = user?.name ?? user?.email ?? "";
  const memberSince = user?.created_at ? new Date(user.created_at).toLocaleDateString("en", { month: "short", year: "numeric" }) : "";

  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  // Pending, not-yet-confirmed goal value shown while the debounced save is
  // in flight. `null` means "show the server-confirmed value". Reset to
  // `null` whenever the confirmed value changes underneath us (debounced
  // save landed, or another tab/device changed it).
  const [pendingGoalKm, setPendingGoalKm] = useState<number | null>(null);
  useEffect(() => {
    setPendingGoalKm(null);
  }, [preferences?.weekly_goal_km]);

  const logOut = useMutation({
    mutationFn: () => apiFetch("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      queryClient.setQueryData(["auth", "me"], null);
      router.push(`/${locale}`);
    },
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const uploadAvatar = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      const response = await fetch(`${baseUrl}/profile/avatar`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!response.ok) throw new Error("Upload failed");
      return (await response.json()) as { avatar_url: string };
    },
    onSuccess: ({ avatar_url }) => {
      setUploadError(null);
      queryClient.setQueryData(["auth", "me"], (previous: typeof user) => (previous ? { ...previous, avatar_url } : previous));
    },
    onError: () => setUploadError(t("avatarUploadFailed")),
  });

  function onAvatarFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!["image/jpeg", "image/png"].includes(file.type)) {
      setUploadError(t("avatarInvalidType"));
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setUploadError(t("avatarTooLarge"));
      return;
    }
    setUploadError(null);
    uploadAvatar.mutate(file);
  }

  const locationName = useLocationName(preferences?.location_lat ?? null, preferences?.location_lon ?? null);

  function useMyLocation() {
    setGeoError(null);
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoError(t("locationDenied"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        updateNow({ location_lat: position.coords.latitude, location_lon: position.coords.longitude });
        setIsEditingProfile(false);
      },
      () => setGeoError(t("locationDenied")),
    );
  }

  if (isLoading || !preferences) {
    return (
      <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[960px] lg:px-0 lg:pt-6 lg:pb-9">
        <div className="text-sm text-muted">{t("weeklyGoal")}</div>
      </div>
    );
  }

  const locationSet = preferences.location_lat !== null && preferences.location_lon !== null;
  const showLocationEditor = isEditingProfile || !locationSet;

  const displayedGoalKm = pendingGoalKm ?? preferences.weekly_goal_km;
  const weeklyGoalValue = preferences.units === "km" ? displayedGoalKm : Math.round(displayedGoalKm * KM_TO_MI);
  const weeklyGoalUnit = preferences.units === "km" ? "km" : "mi";

  const doneKm = dashboard?.weekly_stats?.total_distance_km ?? 0;
  const toGoKm = Math.max(0, displayedGoalKm - doneKm);
  const goalPct = displayedGoalKm > 0 ? Math.min(100, Math.round((doneKm / displayedGoalKm) * 100)) : 0;
  const formatKm = (km: number) => (preferences.units === "km" ? `${km} km` : `${Math.round(km * KM_TO_MI)} mi`);

  function setGoal(nextGoal: number) {
    setPendingGoalKm(nextGoal);
    updateDebounced({ weekly_goal_km: nextGoal });
  }

  function adjustGoal(deltaKm: number) {
    setGoal(Math.min(MAX_GOAL_KM, Math.max(MIN_GOAL_KM, displayedGoalKm + deltaKm)));
  }

  function onLanguageChange(newLanguage: Preferences["language"] | null) {
    if (newLanguage === null) return;
    updateNow({ language: newLanguage });
    const segments = pathname.split("/");
    segments[1] = newLanguage;
    router.replace(segments.join("/"));
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 lg:mx-auto lg:w-full lg:max-w-[960px] lg:px-0 lg:pb-9">
      <div className="mb-3">
        <div className="text-[13px] font-semibold uppercase text-muted">{t("eyebrow")}</div>
        <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-[30px]">{t("title")}</div>
      </div>

      {uploadError && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">{uploadError}</div>}
      {error && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">{t("saveFailed")}</div>}

      <div className="mb-3 flex flex-col gap-4 rounded-xl bg-primary p-[22px] lg:mb-4 lg:gap-[18px] lg:p-7">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3.5 lg:gap-4">
            <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploadAvatar.isPending} className="group relative flex-none rounded-full disabled:cursor-not-allowed">
              <Avatar user={{ name: user?.name ?? null, avatar_url: user?.avatar_url ?? null }} size="lg" />
              <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50 opacity-0 transition-opacity group-hover:opacity-100">
                {uploadAvatar.isPending ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" /> : <Camera size={18} className="text-white" />}
              </div>
            </button>
            <input ref={fileInputRef} type="file" accept="image/jpeg,image/png" aria-label={t("changeAvatar")} className="hidden" onChange={onAvatarFileChosen} />
            <div>
              <div className="text-lg font-bold text-primary-foreground lg:text-[22px]">{displayName}</div>
              <div className="text-[13px] text-goal-label lg:text-sm">{user?.email ?? ""}</div>
            </div>
          </div>
          <button
            onClick={() => setIsEditingProfile((editing) => !editing)}
            className="h-[30px] flex-none cursor-pointer rounded-full border border-primary-foreground/25 bg-primary-foreground/10 px-3.5 text-xs font-semibold text-primary-foreground lg:h-[34px] lg:px-4 lg:text-[13px]"
          >
            {isEditingProfile ? t("doneEditing") : t("editProfile")}
          </button>
        </div>

        <div className="h-px bg-primary-foreground/10" />

        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="text-[11px] font-medium uppercase text-stat-label">{t("location")}</div>
            {showLocationEditor ? (
              <LocationEditor onUseMyLocation={useMyLocation} geoError={geoError} />
            ) : (
              <div className="text-sm font-semibold text-primary-foreground lg:text-[15px]">{locationName ?? t("locationSet")}</div>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <div className="text-[11px] font-medium uppercase text-stat-label">{t("memberSince")}</div>
            <div className="text-sm font-semibold text-primary-foreground lg:text-[15px]">{memberSince}</div>
          </div>
        </div>
      </div>

      <Card className="mb-3 gap-3.5 rounded-xl px-4 py-3.5 lg:mb-4 lg:px-[22px] lg:py-[18px]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("weeklyGoal")}</div>
            <div className="text-xs text-muted-light">
              {t("weeklyGoalSubtitle")} · {t("goalPercentComplete", { percent: goalPct })}
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-full bg-surface px-1.5 py-1.5 lg:gap-3.5 lg:py-2">
            <button
              onClick={() => adjustGoal(-GOAL_STEP_KM)}
              aria-label={t("decreaseGoal")}
              className="h-7 w-7 cursor-pointer rounded-full bg-card text-[15px] font-semibold text-primary shadow-sm lg:h-8 lg:w-8 lg:text-base"
            >
              –
            </button>
            <div className="flex min-w-[52px] items-baseline justify-center gap-1 text-sm font-semibold text-primary lg:min-w-[60px] lg:text-[15px]">
              <span className="font-mono">{weeklyGoalValue}</span>
              <span>{weeklyGoalUnit}</span>
            </div>
            <button
              onClick={() => adjustGoal(GOAL_STEP_KM)}
              aria-label={t("increaseGoal")}
              className="h-7 w-7 cursor-pointer rounded-full bg-primary text-[15px] font-semibold text-primary-foreground lg:h-8 lg:w-8 lg:text-base"
            >
              +
            </button>
          </div>
        </div>
        <Slider aria-label={t("weeklyGoal")} min={MIN_GOAL_KM} max={MAX_GOAL_KM} step={1} value={displayedGoalKm} onValueChange={(nextGoal) => setGoal(nextGoal)} />
        <div className="flex items-center justify-between text-xs text-muted-light">
          <div>{t("doneThisWeek", { distance: formatKm(doneKm) })}</div>
          <div>{t("toGo", { distance: formatKm(toGoKm) })}</div>
        </div>
      </Card>

      <Card className="mb-3 gap-0 rounded-xl p-4 lg:mb-4 lg:px-[22px]">
        <div className="text-[13px] font-semibold uppercase text-muted">{t("preferences")}</div>
        <div className="divide-y divide-border">
          <PreferenceRow label={t("units")} subtitle={t("unitsSubtitle")}>
            <div className="flex rounded-full border border-border bg-surface p-0.5">
              <button
                onClick={() => updateNow({ units: "km" })}
                className={`h-7 cursor-pointer rounded-full px-3 text-xs font-semibold lg:h-[30px] lg:px-3.5 lg:text-[13px] ${
                  preferences.units === "km" ? "bg-card text-primary shadow-sm" : "text-muted-light"
                }`}
              >
                {t("kilometers")}
              </button>
              <button
                onClick={() => updateNow({ units: "mi" })}
                className={`h-7 cursor-pointer rounded-full px-3 text-xs font-semibold lg:h-[30px] lg:px-3.5 lg:text-[13px] ${
                  preferences.units === "mi" ? "bg-card text-primary shadow-sm" : "text-muted-light"
                }`}
              >
                {t("miles")}
              </button>
            </div>
          </PreferenceRow>

          <PreferenceRow label={t("language")} subtitle={t("languageSubtitle")}>
            <Select items={{ en: t("english"), de: t("german") }} value={preferences.language} onValueChange={onLanguageChange}>
              <SelectTrigger className="h-[30px] w-auto rounded-full border border-border bg-surface px-3.5 text-xs font-semibold text-primary lg:h-[34px] lg:px-4 lg:text-[13px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">{t("english")}</SelectItem>
                <SelectItem value="de">{t("german")}</SelectItem>
              </SelectContent>
            </Select>
          </PreferenceRow>

          <PreferenceRow label={t("notifications")} subtitle={t("notificationsSubtitle")}>
            <button
              onClick={() => updateNow({ notifications_enabled: !preferences.notifications_enabled })}
              aria-pressed={preferences.notifications_enabled}
              aria-label={t("notifications")}
              className="relative h-[27px] w-[46px] flex-none cursor-pointer rounded-full"
              style={{
                background: preferences.notifications_enabled ? "var(--color-accent)" : "var(--color-border)",
              }}
            >
              <span
                className="absolute top-[3px] h-[21px] w-[21px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.2)] transition-[left]"
                style={{ left: preferences.notifications_enabled ? "22px" : "3px" }}
              />
            </button>
          </PreferenceRow>
        </div>
      </Card>

      <Card className="gap-0 rounded-xl px-4 py-1 lg:px-[22px]">
        <div className="pt-3 text-[13px] font-semibold uppercase text-muted">{t("account")}</div>
        <div className="flex items-center justify-between gap-3 py-3.5">
          <div>
            <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("signOut")}</div>
            <div className="text-xs text-muted-light">{t("signOutSubtitle")}</div>
          </div>
          <button
            onClick={() => logOut.mutate()}
            disabled={logOut.isPending}
            className="h-[34px] cursor-pointer rounded-full border border-danger-border bg-danger-bg px-4 text-xs font-semibold text-danger disabled:cursor-not-allowed disabled:opacity-60 lg:h-9 lg:text-[13px]"
          >
            {t("logOut")}
          </button>
        </div>
      </Card>
    </div>
  );
}
