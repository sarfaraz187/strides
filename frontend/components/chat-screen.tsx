"use client";

import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";

type Message = { from: "user" | "coach"; text: string };

export function ChatScreen({ locale }: { locale: string }) {
  const t = useTranslations("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");

  const sendMessage = useMutation({
    mutationFn: (message: string) =>
      apiFetch<{ reply: string }>("/chat", {
        method: "POST",
        body: JSON.stringify({ message, locale }),
      }),
    onSuccess: (data) => {
      setMessages((prev) => [...prev, { from: "coach", text: data.reply }]);
    },
  });

  function handleSend() {
    const trimmed = draft.trim();
    if (!trimmed) return;
    setMessages((prev) => [...prev, { from: "user", text: trimmed }]);
    setDraft("");
    sendMessage.mutate(trimmed);
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex items-center gap-2.5 border-b border-border px-[22px] py-4">
        <div className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-primary">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path
              d="M4 17L9 10L13 14L20 5"
              stroke="#D8DED0"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div>
          <div className="text-sm font-semibold text-primary">{t("coachName")}</div>
          <div className="text-[11px] text-chat-sync">{t("syncedStatus")}</div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-[18px] py-4">
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`mb-2.5 flex ${msg.from === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[78%] rounded-[16px] px-[15px] py-[11px] text-sm leading-[1.45] ${
                  msg.from === "user"
                    ? "rounded-br-[4px] bg-primary text-primary-foreground"
                    : "rounded-bl-[4px] border border-border bg-card text-primary"
                }`}
              >
                {msg.text}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="flex items-center gap-2.5 border-t border-border px-4 py-3">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("placeholder")}
          className="h-11 rounded-full"
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
        />
        <Button
          aria-label="send"
          onClick={handleSend}
          className="h-11 w-11 rounded-full bg-primary p-0"
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
            <path
              d="M4 12h15m0 0l-6-6m6 6l-6 6"
              stroke="#F6F4EF"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </Button>
      </div>
    </div>
  );
}
