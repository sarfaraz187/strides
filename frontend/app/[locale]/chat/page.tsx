import { BottomNav } from "@/components/bottom-nav";
import { ChatScreen } from "@/components/chat-screen";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return (
    <div className="flex h-screen flex-col">
      <ChatScreen locale={locale} />
      <BottomNav active="coach" locale={locale} />
    </div>
  );
}
