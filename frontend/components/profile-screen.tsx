"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera } from "lucide-react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Avatar } from "@/components/avatar";
import { SectionLabel } from "@/components/section-label";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { WeeklyGoalStepper } from "@/components/weekly-goal-stepper";
import { useAvatarUpload } from "@/hooks/use-avatar-upload";
import { useDashboard } from "@/hooks/use-dashboard";
import { useLocationName } from "@/hooks/use-location-name";
import { usePreferences } from "@/hooks/use-preferences";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { computeGoalProgress } from "@/lib/goal-progress";
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
      <Button
        variant="ghost"
        onClick={onUseMyLocation}
        className="h-8 w-fit rounded-full border border-primary-foreground/25 bg-primary-foreground/10 px-3.5 text-xs font-semibold text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground"
      >
        {t("useMyLocation")}
      </Button>
      {geoError && <div className="text-xs text-danger">{geoError}</div>}
    </div>
  );
}

function PreferenceRow({ label, subtitle, children }: { label: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
      <div>
        <div className="text-sm font-semibold text-primary lg:text-base">{label}</div>
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
  const memberSince = user?.created_at ? new Date(user.created_at).toLocaleDateString(locale, { month: "short", year: "numeric" }) : "";

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

  const { fileInputRef, error: avatarError, isUploading, onFileChosen, triggerUpload } = useAvatarUpload();
  const uploadErrorMessage =
    avatarError === "invalidType" ? t("avatarInvalidType") : avatarError === "tooLarge" ? t("avatarTooLarge") : avatarError === "uploadFailed" ? t("avatarUploadFailed") : null;

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
      <div className="flex-1 overflow-y-auto px-6 py-5 lg:mx-auto lg:w-full lg:max-w-[960px] lg:px-0 lg:pt-6 lg:pb-9">
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
  const { toGoKm, goalPct } = computeGoalProgress(doneKm, displayedGoalKm);
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
      <div className="mb-3 mt-4 lg:mt-1">
        <SectionLabel>{t("eyebrow")}</SectionLabel>
        <div className="text-2xl font-bold tracking-[-0.3px] text-primary lg:text-3xl">{t("title")}</div>
      </div>

      {uploadErrorMessage && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-sm text-danger">{uploadErrorMessage}</div>}
      {error && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-sm text-danger">{t("saveFailed")}</div>}

      <div className="mb-3 flex flex-col gap-4 rounded-xl bg-primary p-6 lg:mb-4 lg:gap-5 lg:p-7">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3.5 lg:gap-4">
            <Button type="button" variant="ghost" onClick={triggerUpload} disabled={isUploading} className="group relative h-auto flex-none rounded-xl p-0 hover:bg-transparent">
              <Avatar user={user} size="lg" />
              <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50 opacity-0 transition-opacity group-hover:opacity-100">
                {isUploading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" /> : <Camera size={18} className="text-white" />}
              </div>
            </Button>
            <input ref={fileInputRef} type="file" accept="image/jpeg,image/png" aria-label={t("changeAvatar")} className="hidden" onChange={onFileChosen} />
            <div className="min-w-0">
              <div className="truncate text-lg font-bold text-primary-foreground lg:text-2xl">{displayName}</div>
              <div className="truncate text-sm text-goal-label lg:text-sm">{user?.email ?? ""}</div>
            </div>
          </div>
          <Button
            variant="ghost"
            onClick={() => setIsEditingProfile((editing) => !editing)}
            className="h-8 flex-none rounded-xl border border-primary-foreground/25 bg-primary-foreground/10 px-3.5 text-xs font-semibold text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground lg:h-9 lg:px-4 lg:text-sm"
          >
            {isEditingProfile ? t("doneEditing") : t("editProfile")}
          </Button>
        </div>

        <div className="h-px bg-primary-foreground/10" />

        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="text-xs font-medium uppercase text-stat-label">{t("location")}</div>
            {showLocationEditor ? (
              <LocationEditor onUseMyLocation={useMyLocation} geoError={geoError} />
            ) : (
              <div className="text-sm font-semibold text-primary-foreground lg:text-base">{locationName ?? t("locationSet")}</div>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <div className="text-xs font-medium uppercase text-stat-label">{t("memberSince")}</div>
            <div className="text-sm font-semibold text-primary-foreground lg:text-base">{memberSince}</div>
          </div>
        </div>
      </div>

      <Card className="mb-3 gap-3.5 rounded-xl px-4 py-3.5 lg:mb-4 lg:px-6 lg:py-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-primary lg:text-base">{t("weeklyGoal")}</div>
            <div className="text-xs text-muted-light">
              {t("weeklyGoalSubtitle")} · {t("goalPercentComplete", { percent: goalPct })}
            </div>
          </div>
          <WeeklyGoalStepper
            value={weeklyGoalValue}
            unit={weeklyGoalUnit}
            onDecrement={() => adjustGoal(-GOAL_STEP_KM)}
            onIncrement={() => adjustGoal(GOAL_STEP_KM)}
            decrementLabel={t("decreaseGoal")}
            incrementLabel={t("increaseGoal")}
          />
        </div>
        <Slider aria-label={t("weeklyGoal")} min={MIN_GOAL_KM} max={MAX_GOAL_KM} step={1} value={displayedGoalKm} onValueChange={(nextGoal) => setGoal(nextGoal)} />
        <div className="flex items-center justify-between text-xs text-muted-light">
          <div>{t("doneThisWeek", { distance: formatKm(doneKm) })}</div>
          <div>{t("toGo", { distance: formatKm(toGoKm) })}</div>
        </div>
      </Card>

      <Card className="mb-3 gap-0 rounded-xl p-4 lg:mb-4 lg:px-6">
        <SectionLabel>{t("preferences")}</SectionLabel>
        <div className="divide-y divide-border">
          <PreferenceRow label={t("units")} subtitle={t("unitsSubtitle")}>
            <div className="flex rounded-full border border-border bg-surface p-0.5">
              <Button
                variant="ghost"
                onClick={() => updateNow({ units: "km" })}
                className={`h-7 rounded-full px-3 text-xs font-semibold hover:bg-transparent lg:h-8 lg:px-3.5 lg:text-sm ${
                  preferences.units === "km" ? "bg-card text-primary shadow-sm hover:bg-card" : "text-muted-light"
                }`}
              >
                {t("kilometers")}
              </Button>
              <Button
                variant="ghost"
                onClick={() => updateNow({ units: "mi" })}
                className={`h-7 rounded-full px-3 text-xs font-semibold hover:bg-transparent lg:h-8 lg:px-3.5 lg:text-sm ${
                  preferences.units === "mi" ? "bg-card text-primary shadow-sm hover:bg-card" : "text-muted-light"
                }`}
              >
                {t("miles")}
              </Button>
            </div>
          </PreferenceRow>

          <PreferenceRow label={t("language")} subtitle={t("languageSubtitle")}>
            <Select items={{ en: t("english"), de: t("german") }} value={preferences.language} onValueChange={onLanguageChange}>
              <SelectTrigger className="h-8 w-auto rounded-xl border border-border bg-surface px-3.5 text-xs font-semibold text-primary lg:h-9 lg:px-4 lg:text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">{t("english")}</SelectItem>
                <SelectItem value="de">{t("german")}</SelectItem>
              </SelectContent>
            </Select>
          </PreferenceRow>

          <PreferenceRow label={t("notifications")} subtitle={t("notificationsSubtitle")}>
            <Button
              variant="ghost"
              onClick={() => updateNow({ notifications_enabled: !preferences.notifications_enabled })}
              aria-pressed={preferences.notifications_enabled}
              aria-label={t("notifications")}
              className="relative h-6 w-11 flex-none rounded-full p-0"
              style={{
                background: preferences.notifications_enabled ? "var(--color-accent)" : "var(--color-border)",
              }}
            >
              <span
                className={`absolute top-1/2 left-0.5 h-5 w-5 -translate-y-1/2 rounded-full bg-white shadow-md transition-transform ${
                  preferences.notifications_enabled ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </Button>
          </PreferenceRow>
        </div>
      </Card>

      <Card className="mt-3 gap-0 rounded-xl px-4 py-1 lg:mt-4 lg:px-6">
        <SectionLabel className="pt-3">{t("account")}</SectionLabel>
        <div className="flex items-center justify-between gap-3 py-3.5">
          <div>
            <div className="text-sm font-semibold text-primary lg:text-base">{t("signOut")}</div>
            <div className="text-xs text-muted-light">{t("signOutSubtitle")}</div>
          </div>
          <Button
            variant="ghost"
            onClick={() => logOut.mutate()}
            disabled={logOut.isPending}
            className="h-9 rounded-xl border border-danger-border bg-danger-bg px-4 text-xs font-semibold text-danger hover:bg-danger-bg disabled:opacity-60 lg:text-sm"
          >
            {t("logOut")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
