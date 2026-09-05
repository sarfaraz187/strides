"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteConversation, listConversations, updateConversation } from "@/lib/conversations-api";

export const CONVERSATIONS_QUERY_KEY = ["conversations"];

export function useConversations(search: string) {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: [...CONVERSATIONS_QUERY_KEY, search],
    queryFn: () => listConversations(search || undefined),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY });
  }

  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => updateConversation(id, { title }),
    onSuccess: invalidate,
  });

  const pinMutation = useMutation({
    mutationFn: ({ id, pinned }: { id: string; pinned: boolean }) => updateConversation(id, { pinned }),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onSuccess: invalidate,
  });

  const conversations = data ?? [];

  return {
    conversations,
    pinned: conversations.filter((c) => c.pinned),
    recent: conversations.filter((c) => !c.pinned),
    rename: renameMutation.mutate,
    setPinned: (id: string, pinned: boolean) => pinMutation.mutate({ id, pinned }),
    remove: deleteMutation.mutate,
  };
}