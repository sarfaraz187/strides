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

export type GoalProgress = {
  id: string;
  description: string;
  target_value: number | null;
  metric: "distance_km" | "pace_min_per_km" | "run_count" | null;
  period: "week" | "deadline" | null;
  deadline: string | null;
  progress_pct: number;
};

export type Dashboard = {
  weekly_stats: WeeklyStats;
  recent_runs: RecentRun[];
  goals: GoalProgress[];
};

export function getDashboard(): Promise<Dashboard> {
  return apiFetch<Dashboard>("/dashboard");
}
