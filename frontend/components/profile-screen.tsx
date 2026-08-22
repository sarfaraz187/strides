"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Avatar } from "@/components/avatar";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useLocationName } from "@/hooks/use-location-name";
import { usePreferences } from "@/hooks/use-preferences";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Preferences } from "@/lib/preferences-api";

const GOAL_STEP_KM = 5;
const MIN_GOAL_KM = 5;
const KM_TO_MI = 0.621;

type LocationFieldProps = {
  locationLat: number | null;
  locationLon: number | null;
  onUpdate: (lat: number, lon: number) => void;
};

function LocationField({ locationLat, locationLon, onUpdate }: LocationFieldProps) {
  const t = useTranslations("profile");
  const locationSet = locationLat !== null && locationLon !== null;
  const locationName = useLocationName(locationLat, locationLon);
  const [isEditing, setIsEditing] = useState(!locationSet);
  const [geoError, setGeoError] = useState<string | null>(null);

  useEffect(() => {
    setIsEditing(!locationSet);
  }, [locationSet]);

  function useMyLocation() {
    setGeoError(null);
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoError(t("locationDenied"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        onUpdate(position.coords.latitude, position.coords.longitude);
        setIsEditing(false);
      },
      () => setGeoError(t("locationDenied")),
    );
  }

  return (
    <Card className="flex flex-col gap-3 rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("location")}</div>
        {!isEditing && (
          <div className="flex items-center gap-3">
            <div className="text-[13px] text-muted-light">{locationSet ? (locationName ?? t("locationSet")) : t("locationNotSet")}</div>
            <button
              onClick={() => setIsEditing(true)}
              className="h-[30px] cursor-pointer rounded-full border border-border bg-surface px-3.5 text-xs font-semibold text-primary lg:h-[34px] lg:px-4 lg:text-[13px]"
            >
              {t("editLocation")}
            </button>
          </div>
        )}
      </div>
      {isEditing && (
        <>
          <button
            onClick={useMyLocation}
            className="h-[34px] w-fit cursor-pointer rounded-full border border-border bg-surface px-3.5 text-xs font-semibold text-primary lg:h-[36px] lg:px-4 lg:text-[13px]"
          >
            {t("useMyLocation")}
          </button>
          {geoError && <div className="text-xs text-danger">{geoError}</div>}
        </>
      )}
    </Card>
  );
}

export function ProfileScreen({ locale }: { locale: string }) {
  const t = useTranslations("profile");
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { preferences, isLoading, updateNow, updateDebounced, error } = usePreferences();
  const { user } = useAuth();
  const displayName = user?.name ?? user?.email ?? "";
  const memberSince = user?.created_at ? new Date(user.created_at).toLocaleDateString("en", { month: "short", year: "numeric" }) : "";

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

  if (isLoading || !preferences) {
    return (
      <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[560px] lg:px-0 lg:py-9">
        <div className="text-sm text-muted">{t("weeklyGoal")}</div>
      </div>
    );
  }

  const displayedGoalKm = pendingGoalKm ?? preferences.weekly_goal_km;
  const weeklyGoalText = preferences.units === "km" ? `${displayedGoalKm} km` : `${Math.round(displayedGoalKm * KM_TO_MI)} mi`;

  function adjustGoal(deltaKm: number) {
    const nextGoal = Math.max(MIN_GOAL_KM, displayedGoalKm + deltaKm);
    setPendingGoalKm(nextGoal);
    updateDebounced({ weekly_goal_km: nextGoal });
  }

  function onLanguageChange(newLanguage: Preferences["language"] | null) {
    if (newLanguage === null) return;
    updateNow({ language: newLanguage });
    const segments = pathname.split("/");
    segments[1] = newLanguage;
    router.replace(segments.join("/"));
  }

  return (
    <div className="flex-1 overflow-y-auto px-[22px] py-5 lg:mx-auto lg:w-full lg:max-w-[560px] lg:px-0 lg:py-9">
      <div className="mb-6 flex items-center gap-3.5 lg:mb-7 lg:gap-4">
        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploadAvatar.isPending} className="relative flex-none rounded-full disabled:cursor-not-allowed">
          <Avatar user={{ name: user?.name ?? null, avatar_url: user?.avatar_url ?? null }} size="lg" />
          {uploadAvatar.isPending && (
            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
            </div>
          )}
        </button>
        <input ref={fileInputRef} type="file" accept="image/jpeg,image/png" aria-label={t("changeAvatar")} className="hidden" onChange={onAvatarFileChosen} />
        <div>
          <div className="text-lg font-bold text-primary lg:text-[22px]">{displayName}</div>
          <div className="text-[13px] text-muted lg:text-sm">{user?.email ?? ""}</div>
        </div>
      </div>

      {uploadError && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">{uploadError}</div>}

      {error && <div className="mb-4 rounded-xl bg-danger/10 p-3 text-[13px] text-danger">{t("saveFailed")}</div>}

      <div className="flex flex-col gap-2.5 lg:gap-3">
        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("weeklyGoal")}</div>
          <div className="flex items-center gap-3 lg:gap-3.5">
            <button
              onClick={() => adjustGoal(-GOAL_STEP_KM)}
              aria-label={t("decreaseGoal")}
              className="h-7 w-7 cursor-pointer rounded-full border border-border bg-surface text-[15px] font-semibold text-primary lg:h-8 lg:w-8 lg:text-base"
            >
              –
            </button>
            <div className="min-w-[52px] text-center font-mono text-sm font-semibold text-primary lg:min-w-[60px] lg:text-[15px]">{weeklyGoalText}</div>
            <button
              onClick={() => adjustGoal(GOAL_STEP_KM)}
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
            onClick={() => updateNow({ units: preferences.units === "km" ? "mi" : "km" })}
            className="h-[30px] cursor-pointer rounded-full border border-border bg-surface px-3.5 text-xs font-semibold text-primary lg:h-[34px] lg:px-4 lg:text-[13px]"
          >
            {preferences.units === "km" ? t("kilometers") : t("miles")}
          </button>
        </Card>

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("notifications")}</div>
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
        </Card>

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("language")}</div>
          <Select items={{ en: t("english"), de: t("german") }} value={preferences.language} onValueChange={onLanguageChange}>
            <SelectTrigger className="h-[30px] w-auto rounded-full border border-border bg-surface px-3.5 text-xs font-semibold text-primary lg:h-[34px] lg:px-4 lg:text-[13px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="en">{t("english")}</SelectItem>
              <SelectItem value="de">{t("german")}</SelectItem>
            </SelectContent>
          </Select>
        </Card>

        <LocationField locationLat={preferences.location_lat} locationLon={preferences.location_lon} onUpdate={(lat, lon) => updateNow({ location_lat: lat, location_lon: lon })} />

        <Card className="flex-row items-center justify-between rounded-2xl px-4 py-3.5 lg:px-[22px] lg:py-[18px]">
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("memberSince")}</div>
          <div className="text-[13px] text-muted-light">{memberSince}</div>
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
