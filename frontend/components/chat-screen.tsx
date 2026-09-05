"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Menu, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { Avatar } from "@/components/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { ApiError, apiFetch, apiStream } from "@/lib/api";
import { getConversationMessages } from "@/lib/conversations-api";
import { formatMessageTime } from "@/lib/format-time";

const THINKING_TIMEOUT_MS = 600;
const COACH_AVATAR = { name: "Coach", avatar_url: "/coach-avatar.png" };

type Message = { id: string; from: "user" | "coach"; text: string; createdAt: string };

const HISTORY_PAGE_SIZE = 20;
const SCROLL_TOP_THRESHOLD = 40;
const SCROLL_BOTTOM_THRESHOLD = 80;

function conversationMessagesQueryKey(conversationId: string | undefined) {
  return ["conversation", conversationId, "messages"];
}

export function ChatScreen({ locale, conversationId, onConversationCreated }: { locale: string; conversationId?: string; onConversationCreated: (conversationId: string) => void }) {
  const t = useTranslations("chat");
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [sendError, setSendError] = useState(false);
  const [budgetExceeded, setBudgetExceeded] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);
  const lastChunkAtRef = useRef(Date.now());
  const nextLocalIdRef = useRef(0);

  useEffect(() => {
    console.log("[debug] ChatScreen mounted, conversationId =", conversationId);
    return () => console.log("[debug] ChatScreen UNMOUNTED, conversationId was =", conversationId);
  }, []);

  useEffect(() => {
    console.log("[debug] conversationId changed -> clearing local messages, conversationId =", conversationId);
    setMessages([]);
  }, [conversationId]);

  function nextLocalId(): string {
    nextLocalIdRef.current += 1;
    return `local-${nextLocalIdRef.current}`;
  }

  const history = useInfiniteQuery({
    queryKey: conversationMessagesQueryKey(conversationId),
    queryFn: ({ pageParam }: { pageParam: number | undefined }) => getConversationMessages(conversationId as string, pageParam, HISTORY_PAGE_SIZE),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.messages[lastPage.messages.length - 1]?.id : undefined),
    enabled: !!conversationId,
    // Messages sent this session live only in local `messages` state (below),
    // not in this query's cache. A background refetch (e.g. on window focus)
    // would pull those same, now-persisted messages back in as `historyMessages`
    // and render them twice alongside the untouched local copies. History only
    // changes via `fetchNextPage`, so there's no reason for it to refetch itself.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  const historyMessages = useMemo<Message[]>(() => {
    if (!history.data) return [];
    return history.data.pages
      .slice()
      .reverse()
      .flatMap((page) =>
        [...page.messages].reverse().map((m) => ({
          id: `history-${m.id}`,
          from: m.role === "assistant" ? ("coach" as const) : ("user" as const),
          text: m.content,
          createdAt: m.created_at,
        })),
      );
  }, [history.data]);

  console.log("[debug] history query state:", history.data);

  async function handleSend(overrideText?: string) {
    const trimmed = (overrideText ?? draft).trim();
    if (!trimmed || isSending) return;
    setDraft("");
    setIsSending(true);
    setSendError(false);
    const coachMessageId = nextLocalId();
    const sentAt = new Date().toISOString();
    setMessages((prev) => [...prev, { id: nextLocalId(), from: "user", text: trimmed, createdAt: sentAt }, { id: coachMessageId, from: "coach", text: "", createdAt: sentAt }]);

    lastChunkAtRef.current = Date.now();
    const thinkingTimer = setInterval(() => {
      setIsThinking(Date.now() - lastChunkAtRef.current > THINKING_TIMEOUT_MS);
    }, 200);

    try {
      await apiStream(
        "/chat",
        {
          method: "POST",
          body: JSON.stringify({ message: trimmed, locale, conversation_id: conversationId ?? null }),
        },
        (event) => {
          if (event.conversation_id && !conversationId) {
            onConversationCreated(event.conversation_id);
          }
          if (event.text === undefined) return;
          lastChunkAtRef.current = Date.now();
          setIsThinking(false);
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, text: last.text + event.text };
            return next;
          });
        },
      );
    } catch (err) {
      const detail = err instanceof ApiError && err.body && typeof err.body === "object" && "detail" in err.body ? (err.body as { detail?: { error?: string } }).detail : null;
      const code = detail?.error ?? null;

      if (code === "budget_exceeded") {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], text: t("budgetExceeded") };
          return next;
        });
        setBudgetExceeded(true);
      } else {
        setSendError(true);
        setMessages((prev) => prev.filter((m) => m.id !== coachMessageId));
      }
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

  console.log(allMessages);
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (container && isNearBottomRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [allMessages.length, lastMessage?.text]);

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:mx-auto lg:w-full lg:max-w-200">
      <div className="flex items-center justify-between border-b border-border px-6 py-4 lg:px-0 lg:py-4">
        <div className="flex items-center gap-2.5">
          <Link href={`/${locale}/chat/list`} aria-label="chats" className="lg:hidden">
            <Menu size={20} />
          </Link>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl">
            <Image src="/icon-512.png" alt="Strides" width={40} height={40} className="h-full w-full object-cover" />
          </div>
          <div>
            <div className="text-sm font-semibold text-primary lg:text-base">{t("coachName")}</div>
            <div className="text-xs text-chat-sync">{t("syncedStatus")}</div>
          </div>
        </div>
        <Button render={<Link href={`/${locale}/chat`} />} className="rounded-full text-[14px]">
          {t("newChat")}
        </Button>
      </div>

      <div ref={scrollContainerRef} data-testid="chat-scroll-container" onScroll={handleScroll} className="scrollbar-none flex-1 overflow-y-auto px-2 py-2 lg:px-0 lg:py-2">
        {!conversationId && allMessages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
            <span className="text-5xl opacity-60" aria-hidden="true">
              👟
            </span>
            <div>
              <div className="text-lg font-bold text-primary">{t("emptyTitle")}</div>
              <div className="mt-1 text-sm text-muted-light">{t("emptySubtitle")}</div>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {t.raw("suggestions").map((suggestion: string) => (
                <button key={suggestion} onClick={() => handleSend(suggestion)} className="rounded-full border border-border bg-card px-4 py-2 text-sm text-primary cursor-pointer">
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {history.isFetchingNextPage && (
              <div className="flex justify-center py-2">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-primary" />
              </div>
            )}
            <AnimatePresence initial={false}>
              {allMessages.map((msg, i) => (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`mb-2.5 flex items-end gap-2 lg:mb-3 ${msg.from === "user" ? "flex-row-reverse" : "flex-row"}`}
                >
                  <Avatar user={msg.from === "user" ? user : COACH_AVATAR} size="md" />
                  <div
                    className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-normal lg:max-w-[65%] ${
                      msg.from === "user"
                        ? "rounded-br bg-primary text-primary-foreground"
                        : "rounded-bl border border-border bg-card text-primary [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:mb-2 [&_p:last-child]:mb-0 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5"
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
                        {msg.text && <div className="text-right text-xs text-muted-light">{formatMessageTime(msg.createdAt)}</div>}
                      </>
                    ) : (
                      <>
                        {msg.text && <span className="float-right ml-2 mt-1 text-xs text-primary-foreground/70">{formatMessageTime(msg.createdAt)}</span>}
                        <span>{msg.text}</span>
                      </>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </>
        )}
      </div>

      {sendError && <div className="px-4 pt-2 text-xs text-danger lg:px-0">{t("sendFailed")}</div>}
      <div className="flex items-center gap-2.5 border-t border-border px-2 py-2 lg:px-0 lg:py-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("placeholder")}
          maxLength={500}
          disabled={budgetExceeded}
          className="h-11 rounded-2xl border-border bg-card px-5 text-primary placeholder:text-muted-light lg:h-12"
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
        />
        <Button aria-label="send" onClick={() => handleSend()} disabled={isSending || budgetExceeded} className="h-11 w-11 rounded-full bg-primary p-0 lg:h-12 lg:w-12">
          <ArrowRight size={17} color="#F6F4EF" strokeWidth={2} />
        </Button>
      </div>
    </div>
  );
}
