"use client";

import { Pencil, Plus, Search, Star, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Conversation } from "@/lib/conversations-api";
import { useConversations } from "@/hooks/use-conversations";
import { cn } from "@/lib/utils";

export function ChatSidebar({ locale, activeConversationId, className, compact = false }: { locale: string; activeConversationId?: string; className?: string; compact?: boolean }) {
  const t = useTranslations("chat");
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const { pinned, recent, rename, setPinned, remove } = useConversations(search);

  function startEditing(conversation: Conversation) {
    setEditingId(conversation.id);
    setEditingTitle(conversation.title);
  }

  function commitEditing() {
    if (editingId && editingTitle.trim()) {
      rename({ id: editingId, title: editingTitle.trim() });
    }
    setEditingId(null);
  }

  function handleDelete(conversationId: string) {
    // Spec: deleting the conversation currently open in the chat view
    // redirects to the empty "New chat" state — deleting any other
    // conversation just removes its row from this list.
    remove(conversationId);
    if (conversationId === activeConversationId) {
      router.replace(`/${locale}/chat`);
    }
  }

  function renderRow(conversation: Conversation) {
    const isActive = conversation.id === activeConversationId;
    return (
      <div key={conversation.id} className={cn("group flex items-center justify-between rounded-lg px-3 py-1.5", isActive ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/50")}>
        {editingId === conversation.id ? (
          <input
            autoFocus
            value={editingTitle}
            onChange={(e) => setEditingTitle(e.target.value)}
            onBlur={commitEditing}
            onKeyDown={(e) => e.key === "Enter" && commitEditing()}
            className="w-full rounded bg-transparent text-sm text-sidebar-foreground outline-none"
          />
        ) : (
          <Link href={`/${locale}/chat/${conversation.id}`} className="min-w-0 flex-1">
            <div className="truncate text-sm text-sidebar-foreground">{conversation.title}</div>
          </Link>
        )}
        <div className="ml-2 hidden shrink-0 items-center gap-1.5 group-hover:flex">
          <button aria-label="pin" onClick={() => setPinned(conversation.id, !conversation.pinned)}>
            <Star size={14} fill={conversation.pinned ? "currentColor" : "none"} />
          </button>
          <button aria-label="rename" onClick={() => startEditing(conversation)}>
            <Pencil size={14} />
          </button>
          <button aria-label="delete" onClick={() => handleDelete(conversation.id)}>
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex w-full flex-col gap-2 ml-2", compact ? "" : "bg-sidebar px-4 py-4", className)}>
      <Link href={`/${locale}/chat`} className="flex items-center gap-2 rounded-lg bg-sidebar-primary px-3 py-2 text-sm font-semibold text-sidebar-primary-foreground">
        <Plus size={16} /> {t("newChat")}
      </Link>

      <div className="flex items-center gap-2 rounded-lg bg-sidebar-accent/40 px-3 py-2">
        <Search size={14} className="text-sidebar-foreground/60" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("searchPlaceholder")}
          className="w-full bg-transparent text-sm text-sidebar-foreground placeholder:text-sidebar-foreground/50 outline-none"
        />
      </div>

      <div className="flex max-h-[420px] flex-col gap-3 overflow-y-auto border-l border-sidebar-border">
        {pinned.length > 0 && (
          <div className="pl-3">
            <div className="mb-1 px-3 text-xs font-semibold uppercase text-sidebar-foreground/50">{t("pinnedSection")}</div>
            {pinned.map(renderRow)}
          </div>
        )}

        <div className="pl-3">
          <div className="mb-1 px-3 text-xs font-semibold uppercase text-sidebar-foreground/50">{t("recentSection")}</div>
          {recent.map(renderRow)}
        </div>
      </div>
    </div>
  );
}
