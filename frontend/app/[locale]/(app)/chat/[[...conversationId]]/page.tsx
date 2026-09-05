"use client";

import { useParams, useRouter } from "next/navigation";

import { ChatScreen } from "@/components/chat-screen";

export default function ChatPage() {
  const { locale, conversationId } = useParams<{ locale: string; conversationId?: string[] }>();
  const router = useRouter();

  return (
    <ChatScreen
      locale={locale}
      conversationId={conversationId?.[0]}
      onConversationCreated={(newConversationId) => router.replace(`/${locale}/chat/${newConversationId}`)}
    />
  );
}
