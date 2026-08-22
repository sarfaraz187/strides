"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch, apiStream } from "@/lib/api";

const THINKING_TIMEOUT_MS = 600;

type Message = { from: "user" | "coach"; text: string };

type ApiMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type ChatHistoryPage = { messages: ApiMessage[]; has_more: boolean };

const HISTORY_PAGE_SIZE = 20;
const SCROLL_TOP_THRESHOLD = 40;
const SCROLL_BOTTOM_THRESHOLD = 80;

const CHAT_HISTORY_QUERY_KEY = ["chat-history"];

export function ChatScreen({ locale }: { locale: string }) {
  const t = useTranslations("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);
  const lastChunkAtRef = useRef(Date.now());

  const history = useInfiniteQuery({
    queryKey: CHAT_HISTORY_QUERY_KEY,
    queryFn: ({ pageParam }: { pageParam: number | undefined }) => apiFetch<ChatHistoryPage>(`/chat/history?limit=${HISTORY_PAGE_SIZE}${pageParam ? `&before_id=${pageParam}` : ""}`),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.messages[lastPage.messages.length - 1]?.id : undefined),
  });

  const historyMessages = useMemo<Message[]>(() => {
    if (!history.data) return [];
    return history.data.pages
      .slice()
      .reverse()
      .flatMap((page) =>
        [...page.messages].reverse().map((m) => ({
          from: m.role === "assistant" ? ("coach" as const) : ("user" as const),
          text: m.content,
        })),
      );
  }, [history.data]);

  async function handleSend() {
    const trimmed = draft.trim();
    if (!trimmed || isSending) return;
    setDraft("");
    setIsSending(true);
    setMessages((prev) => [...prev, { from: "user", text: trimmed }, { from: "coach", text: "" }]);

    lastChunkAtRef.current = Date.now();
    const thinkingTimer = setInterval(() => {
      setIsThinking(Date.now() - lastChunkAtRef.current > THINKING_TIMEOUT_MS);
    }, 200);

    try {
      await apiStream(
        "/chat",
        { method: "POST", body: JSON.stringify({ message: trimmed, locale }) },
        (chunk) => {
          lastChunkAtRef.current = Date.now();
          setIsThinking(false);
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { from: "coach", text: next[next.length - 1].text + chunk };
            return next;
          });
        }
      );
    } finally {
      clearInterval(thinkingTimer);
      setIsThinking(false);
      setIsSending(false);
    }
  }

  function handleScroll(e: React.UIEvent<HTMLDivElement>) {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;

    if (scrollTop <= SCROLL_TOP_THRESHOLD && history.hasNextPage && !history.isFetchingNextPage) {
      history.fetchNextPage();
    }

    isNearBottomRef.current = scrollHeight - scrollTop - clientHeight <= SCROLL_BOTTOM_THRESHOLD;
  }

  const allMessages = [...historyMessages, ...messages];
  const lastMessage = allMessages[allMessages.length - 1];

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (container && isNearBottomRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [allMessages.length, lastMessage?.text]);

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:mx-auto lg:w-full lg:max-w-[780px]">
      <div className="flex items-center gap-2.5 border-b border-border px-[22px] py-4 lg:px-0 lg:pt-4 lg:pb-4">
        <div className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-primary lg:h-9 lg:w-9">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M4 17L9 10L13 14L20 5" stroke="#D8DED0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <div className="text-sm font-semibold text-primary lg:text-[15px]">{t("coachName")}</div>
          <div className="text-[11px] text-chat-sync lg:text-xs">{t("syncedStatus")}</div>
        </div>
      </div>

      <div ref={scrollContainerRef} data-testid="chat-scroll-container" onScroll={handleScroll} className="scrollbar-none flex-1 overflow-y-auto px-[18px] py-4 lg:px-0 lg:py-5">
        {history.isFetchingNextPage && (
          <div className="flex justify-center py-2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-primary" />
          </div>
        )}
        <AnimatePresence initial={false}>
          {allMessages.map((msg, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={`mb-2.5 flex lg:mb-3 ${msg.from === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[78%] rounded-[16px] px-[15px] py-[11px] text-sm leading-[1.45] lg:max-w-[65%] lg:px-4 lg:py-3 lg:text-[15px] lg:leading-[1.5] ${
                  msg.from === "user"
                    ? "rounded-br-[4px] bg-primary text-primary-foreground"
                    : "rounded-bl-[4px] border border-border bg-card text-primary [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:mb-2 [&_p:last-child]:mb-0 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5"
                }`}
              >
                {msg.from === "coach" ? (
                  <>
                    <ReactMarkdown>{msg.text}</ReactMarkdown>
                    {isThinking && i === allMessages.length - 1 && (
                      <span data-testid="thinking-indicator" className="inline-flex gap-1">
                        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-light [animation-delay:-0.2s]" />
                        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-light [animation-delay:-0.1s]" />
                        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-light" />
                      </span>
                    )}
                  </>
                ) : (
                  msg.text
                )}
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
        <Button aria-label="send" onClick={handleSend} className="h-11 w-11 rounded-full bg-primary p-0 lg:h-[46px] lg:w-[46px]">
          <ArrowRight size={17} color="#F6F4EF" strokeWidth={2} />
        </Button>
      </div>
    </div>
  );
}
