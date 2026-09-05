"use client";

import { motion } from "framer-motion";
import { ArrowLeft, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { use } from "react";

import { ChatSidebar } from "@/components/chat-sidebar";

export default function ChatListPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  const t = useTranslations("chat");

  return (
    <motion.div initial={{ x: "100%" }} animate={{ x: 0 }} transition={{ duration: 0.25, ease: "easeOut" }} className="flex min-h-0 flex-1 flex-col lg:hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-4">
        <div className="flex items-center gap-3">
          <Link href={`/${locale}/chat`} aria-label="back">
            <ArrowLeft size={20} />
          </Link>
          <span className="text-lg font-bold text-primary">{t("chatsTitle")}</span>
        </div>
        <Link href={`/${locale}/chat`} aria-label="new chat">
          <Plus size={20} />
        </Link>
      </div>
      <ChatSidebar locale={locale} className="flex flex-1" />
    </motion.div>
  );
}
