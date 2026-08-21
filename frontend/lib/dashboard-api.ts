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

export type UpcomingRun = {
  id: string;
  summary: string;
  start: { dateTime: string };
  forecast: { temp: number; condition: string } | null;
};

export type CurrentWeather = {
  temp: number;
  feels_like: number;
  humidity: number;
  wind: number;
  condition: string;
  aqi: number;
  hourly: { time: string[]; temperature_2m: number[] };
};

export type Dashboard = {
  weekly_stats: WeeklyStats | null;
  recent_runs: RecentRun[];
  health_error?: HealthError | null;
  calendar_connected: boolean;
  upcoming_runs: UpcomingRun[];
  current_weather: CurrentWeather | null;
};

export function getDashboard(): Promise<Dashboard> {
  return apiFetch<Dashboard>("/dashboard");
}
