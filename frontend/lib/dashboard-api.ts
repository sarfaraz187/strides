import { apiFetch } from "@/lib/api";

export type WeeklyStats = {
  run_count: number;
  total_distance_km: number;
  total_duration_min: number;
  avg_pace_min_per_km: number | null;
};

export type RecentRun = {
  date: string;
  distance_km: number;
  duration_min: number;
  pace_min_per_km: number | null;
  calories: number | null;
};

export type HealthError = {
  error: string;
  message: string;
  redirect_uri?: string;
};

export type Dashboard = {
  weekly_stats: WeeklyStats | null;
  recent_runs: RecentRun[];
  health_error?: HealthError | null;
};

export function getDashboard(): Promise<Dashboard> {
  return apiFetch<Dashboard>("/dashboard");
}
