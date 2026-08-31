import { apiFetch } from "@/lib/api";

export type Notification = {
  id: number;
  user_id: string;
  type: string;
  action_href: string | null;
  status: "unread" | "read";
  created_at: string;
};

export function getNotifications(): Promise<Notification[]> {
  return apiFetch<Notification[]>("/notifications");
}

export function markAllRead(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/notifications/read-all", { method: "PATCH" });
}