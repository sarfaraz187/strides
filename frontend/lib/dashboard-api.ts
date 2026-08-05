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

export type Dashboard = {
  weekly_stats: WeeklyStats;
  recent_runs: RecentRun[];
};

export function getDashboard(): Promise<Dashboard> {
  return apiFetch<Dashboard>("/dashboard");
}
