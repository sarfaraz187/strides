import { apiFetch } from "@/lib/api";

export type Conversation = {
  id: string;
  title: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
};

export type ApiMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type ChatHistoryPage = { messages: ApiMessage[]; has_more: boolean };

export function listConversations(search?: string): Promise<Conversation[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  return apiFetch<Conversation[]>(`/conversations${query}`);
}

export function updateConversation(
  id: string,
  updates: { title?: string; pinned?: boolean }
): Promise<{ status: string }> {
  return apiFetch(`/conversations/${id}`, { method: "PATCH", body: JSON.stringify(updates) });
}

export function deleteConversation(id: string): Promise<{ status: string }> {
  return apiFetch(`/conversations/${id}`, { method: "DELETE" });
}

export function getConversationMessages(
  id: string,
  beforeId?: number,
  limit = 20
): Promise<ChatHistoryPage> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (beforeId !== undefined) params.set("before_id", String(beforeId));
  return apiFetch<ChatHistoryPage>(`/conversations/${id}/messages?${params.toString()}`);
}