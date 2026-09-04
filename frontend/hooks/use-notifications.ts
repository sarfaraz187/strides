"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getNotifications, markAllRead as markAllReadRequest } from "@/lib/notifications-api";

const POLL_INTERVAL_MS = 5 * 60 * 1000;

export function useNotifications() {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: getNotifications,
    refetchInterval: POLL_INTERVAL_MS,
  });

  const mutation = useMutation({
    mutationFn: markAllReadRequest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const notifications = data ?? [];
  const unreadCount = notifications.filter((n) => n.status === "unread").length;

  return { notifications, unreadCount, markAllRead: mutation.mutate };
}
