import { apiFetch } from "@/lib/api";

export type PlanRunInput = {
  title: string;
  start_time: string;
  duration_minutes: number;
  notes?: string;
};

export type PlannedRun = {
  id: string;
  summary: string;
  start: { dateTime: string };
};

export function planRun(input: PlanRunInput): Promise<PlannedRun> {
  return apiFetch<PlannedRun>("/calendar/events", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
