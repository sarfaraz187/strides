"use client";

import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useTranslations } from "next-intl";
import { useState } from "react";
import ReactMarkdown from "react-markdown";

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
    <div className="flex flex-1 flex-col lg:mx-auto lg:w-full lg:max-w-[720px]">
      <div className="flex items-center gap-2.5 border-b border-border px-[22px] py-4 lg:px-0 lg:pt-7 lg:pb-4">
        <div className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-primary lg:h-9 lg:w-9">
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
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("coachName")}</div>
          <div className="text-[11px] text-chat-sync lg:text-xs">{t("syncedStatus")}</div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-[18px] py-4 lg:px-0 lg:py-5">
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`mb-2.5 flex lg:mb-3 ${msg.from === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[78%] rounded-[16px] px-[15px] py-[11px] text-sm leading-[1.45] lg:max-w-[65%] lg:px-4 lg:py-3 lg:text-[15px] lg:leading-[1.5] ${
                  msg.from === "user"
                    ? "rounded-br-[4px] bg-primary text-primary-foreground"
                    : "rounded-bl-[4px] border border-border bg-card text-primary [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:mb-2 [&_p:last-child]:mb-0 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5"
                }`}
              >
                {msg.from === "coach" ? <ReactMarkdown>{msg.text}</ReactMarkdown> : msg.text}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="flex items-center gap-2.5 border-t border-border px-4 py-3 lg:px-0 lg:pt-4 lg:pb-7">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("placeholder")}
          className="h-11 rounded-full border-border bg-card px-[18px] text-primary placeholder:text-muted-light lg:h-[46px]"
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
        />
        <Button
          aria-label="send"
          onClick={handleSend}
          className="h-11 w-11 rounded-full bg-primary p-0 lg:h-[46px] lg:w-[46px]"
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
