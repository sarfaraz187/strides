import { apiFetch } from "@/lib/api";

export type Preferences = {
  weekly_goal_km: number;
  units: "km" | "mi";
  notifications_enabled: boolean;
  language: "en" | "de";
};

export function getPreferences(): Promise<Preferences> {
  return apiFetch<Preferences>("/preferences");
}

export function updatePreferences(partial: Partial<Preferences>): Promise<Preferences> {
  return apiFetch<Preferences>("/preferences", {
    method: "PUT",
    body: JSON.stringify(partial),
  });
}
