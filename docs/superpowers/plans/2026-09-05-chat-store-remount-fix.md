# Chat Store Remount Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the bug where a first message in a new chat never appears on screen (only shows up after a hard refresh), by moving live chat state out of the Next.js Page component (which always remounts when its own route segment changes) into a Zustand store that lives outside the React tree entirely.

**Architecture:** `ChatScreen` currently owns `messages`/`isSending`/`isThinking`/`sendError`/`budgetExceeded` as local `useState`, and calls `onConversationCreated()` — which triggers `router.replace("/chat/{id}")` — the instant the backend returns a `conversation_id`, mid-stream. Next.js's App Router remounts the Page (and everything under it, including `ChatScreen`) whenever its own dynamic segment value changes, regardless of routing-file structure or how params are read (both were tried and both failed — see investigation below). The remount wipes local state while the SSE stream is still writing into it, silently dropping the reply. The fix: move all of this state into a `useChatStore` (Zustand) keyed by conversation id (or a `"new"` placeholder key before the id is known), which is unaffected by any component unmounting. `ChatScreen` becomes a thin consumer that reads from the store instead of owning state.

**Tech Stack:** Next.js 16 App Router, React 19, Zustand (new dependency), TanStack React Query 5, Vitest + Testing Library.

**Spec:** No separate spec doc — this plan is scoped directly from the debugging conversation. Investigation trail (for context, not required reading to execute the plan): remounting was confirmed via `console.log`s in `ChatScreen`'s mount/unmount effects, showing the component unmounts and remounts the instant the URL changes from `/chat` to `/chat/{id}` — independent of (a) using two separate route files vs. one `[[...conversationId]]` catch-all, and (b) reading params via `use(params)` vs. the synchronous `useParams()` hook. Both were tried and both failed for the same reason: Next's Page component remounts on its own segment change, full stop.

## Global Constraints

- Never use `any` in TypeScript — use proper types, `unknown`, or generics (project-wide rule).
- Strict TypeScript config; explicit types for function params and return values.
- Prefer functional patterns (hooks), no class components.
- Default to no comments; only add one where the WHY is genuinely non-obvious.
- TDD: write the failing test first, run it to confirm red, then implement, then confirm green.
- Zustand is a **new dependency** — the user has already approved adding it in this conversation.

---

## File Structure

```
frontend/
  package.json                                    (MODIFY — add zustand)
  lib/
    query-provider.tsx                             (MODIFY — export the QueryClient as a module singleton)
    stores/
      chat-store.ts                                (NEW — the Zustand store)
  components/
    chat-screen.tsx                                (MODIFY — consume the store, remove local state + debug logs)
  tests/
    chat-store.test.ts                              (NEW — store-level regression tests)
    chat-screen.test.tsx                            (MODIFY — reset store between tests, add remount regression test)
```

No other files change. `chat-sidebar.tsx`, `use-conversations.ts`, `conversations-api.ts`, and the page files are untouched by this plan.

---

### Task 1: Add the Zustand dependency

**Files:**
- Modify: `frontend/package.json`

**Interfaces:**
- Produces: the `zustand` package available to import as `import { create } from "zustand"` in later tasks.

- [ ] **Step 1: Install the package**

Run from `frontend/`:
```bash
npm install zustand@5
```

This adds `"zustand": "^5.x.x"` to `dependencies` in `package.json` and updates the lockfile.

- [ ] **Step 2: Verify it installed cleanly**

Run: `npm run build 2>&1 | tail -20` (or `npx tsc --noEmit` if a full build is slow) from `frontend/`.
Expected: no errors related to the new dependency (there's nothing importing it yet, so this just confirms the install didn't break anything).

- [ ] **Step 3: Commit**

```bash
cd frontend
git add package.json package-lock.json
git commit -m "chore(frontend): add zustand dependency"
```

---

### Task 2: Export the QueryClient as a module singleton

**Files:**
- Modify: `frontend/lib/query-provider.tsx`

**Interfaces:**
- Produces: `queryClient` — a plain exported `QueryClient` instance, importable outside React (`import { queryClient } from "@/lib/query-provider"`), used by the chat store in Task 3 to invalidate the sidebar's conversations list the moment a new conversation is created.
- Consumes: nothing new. `QueryProvider` is mounted once at `frontend/app/[locale]/layout.tsx:33` and never remounts, so a module-level singleton is equivalent to today's `useState`-created client in practice, just also reachable from non-component code.

This task has no test of its own — it's a plumbing change with no new behavior yet (the client is still wired into `QueryClientProvider` exactly as before). Its correctness is verified by Task 3's tests, which depend on this export existing.

- [ ] **Step 1: Read the current file**

`frontend/lib/query-provider.tsx` currently is:
```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 60 * 1000,
          },
        },
      }),
  );
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
```

- [ ] **Step 2: Replace it with a module-level client**

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
    },
  },
});

export function QueryProvider({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
```

- [ ] **Step 3: Typecheck**

Run: `npx tsc --noEmit` from `frontend/`.
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd frontend
git add lib/query-provider.tsx
git commit -m "refactor(frontend): export the QueryClient as a module singleton"
```

---

### Task 3: Create the chat store, with tests for the bug and its error paths

**Files:**
- Create: `frontend/lib/stores/chat-store.ts`
- Test: `frontend/tests/chat-store.test.ts`

**Interfaces:**
- Consumes: `apiStream`, `ApiError` from `frontend/lib/api.ts` (existing, unchanged); `queryClient` from `frontend/lib/query-provider.tsx` (Task 2); `CONVERSATIONS_QUERY_KEY` from `frontend/hooks/use-conversations.ts` (existing, unchanged).
- Produces:
  - `type ChatMessage = { id: string; from: "user" | "coach"; text: string; createdAt: string }`
  - `EMPTY_SESSION: SessionState` — a stable, shared empty-session object for selector defaults.
  - `useChatStore` — the Zustand hook, with state shape `{ sessions: Record<string, SessionState>; budgetExceeded: boolean; sendMessage(args): Promise<void> }`, where `SessionState = { messages: ChatMessage[]; isSending: boolean; isThinking: boolean; sendError: boolean }`.
  - `sendMessage({ key, text, locale, conversationId, onConversationCreated, budgetExceededMessage })` — used by `ChatScreen` in Task 4.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/chat-store.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "../lib/query-provider";
import { CONVERSATIONS_QUERY_KEY } from "../hooks/use-conversations";
import { useChatStore } from "../lib/stores/chat-store";

function sseResponse(chunks: string[], conversationId: string) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(`data: ${JSON.stringify({ conversation_id: conversationId })}\n\n`));
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ text: chunk })}\n\n`));
      }
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
}

function errorResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status });
}

describe("useChatStore.sendMessage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useChatStore.setState({ sessions: {}, budgetExceeded: false }, true);
  });

  it("keeps the streamed reply intact under the real conversation id once it's created mid-stream", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(sseResponse(["Hey", " there!"], "conv-real"));
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const onConversationCreated = vi.fn();
    await useChatStore.getState().sendMessage({
      key: "new",
      text: "hello",
      locale: "en",
      conversationId: undefined,
      onConversationCreated,
      budgetExceededMessage: "budget exceeded",
    });

    expect(onConversationCreated).toHaveBeenCalledWith("conv-real");
    // The transient "new" key is gone — its state migrated to the real id.
    expect(useChatStore.getState().sessions["new"]).toBeUndefined();
    // This is what ChatScreen reads after the Page remounts under the real id.
    const session = useChatStore.getState().sessions["conv-real"];
    expect(session.messages.map((m) => `${m.from}:${m.text}`)).toEqual(["user:hello", "coach:Hey there!"]);
    expect(session.isSending).toBe(false);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: CONVERSATIONS_QUERY_KEY });
  });

  it("does not touch other keys' state", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(sseResponse(["reply"], "conv-b"));

    await useChatStore.getState().sendMessage({
      key: "conv-a",
      text: "hi",
      locale: "en",
      conversationId: "conv-a",
      onConversationCreated: vi.fn(),
      budgetExceededMessage: "budget exceeded",
    });

    expect(useChatStore.getState().sessions["conv-b"]).toBeUndefined();
  });

  it("ignores a send while one is already in flight for that key", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    let resolveFetch: (r: Response) => void = () => {};
    vi.spyOn(global, "fetch").mockReturnValue(new Promise((resolve) => (resolveFetch = resolve)));

    const first = useChatStore.getState().sendMessage({
      key: "conv-a",
      text: "first",
      locale: "en",
      conversationId: "conv-a",
      onConversationCreated: vi.fn(),
      budgetExceededMessage: "budget exceeded",
    });
    // Give the first call's synchronous `set()` a tick to land before the second call checks isSending.
    await Promise.resolve();

    await useChatStore.getState().sendMessage({
      key: "conv-a",
      text: "second",
      locale: "en",
      conversationId: "conv-a",
      onConversationCreated: vi.fn(),
      budgetExceededMessage: "budget exceeded",
    });

    resolveFetch(sseResponse(["reply"], "conv-a"));
    await first;

    const texts = useChatStore.getState().sessions["conv-a"].messages.map((m) => m.text);
    expect(texts).toEqual(["first", "reply"]);
  });

  it("shows the budget-exceeded message on the placeholder bubble and sets budgetExceeded", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(errorResponse(403, { detail: { error: "budget_exceeded" } }));

    await useChatStore.getState().sendMessage({
      key: "conv-a",
      text: "one more plan please",
      locale: "en",
      conversationId: "conv-a",
      onConversationCreated: vi.fn(),
      budgetExceededMessage: "You've hit your limit.",
    });

    const session = useChatStore.getState().sessions["conv-a"];
    expect(session.messages[session.messages.length - 1].text).toBe("You've hit your limit.");
    expect(useChatStore.getState().budgetExceeded).toBe(true);
  });

  it("removes the placeholder bubble and sets sendError on a generic failure", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(errorResponse(400, { detail: { error: "message_too_long" } }));

    await useChatStore.getState().sendMessage({
      key: "conv-a",
      text: "x".repeat(501),
      locale: "en",
      conversationId: "conv-a",
      onConversationCreated: vi.fn(),
      budgetExceededMessage: "budget exceeded",
    });

    const session = useChatStore.getState().sessions["conv-a"];
    expect(session.messages.map((m) => m.from)).toEqual(["user"]);
    expect(session.sendError).toBe(true);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run tests/chat-store.test.ts` from `frontend/`.
Expected: FAIL — `Cannot find module '../lib/stores/chat-store'` (the file doesn't exist yet).

- [ ] **Step 3: Write the store implementation**

Create `frontend/lib/stores/chat-store.ts`:

```ts
import { create } from "zustand";

import { ApiError, apiStream } from "@/lib/api";
import { CONVERSATIONS_QUERY_KEY } from "@/hooks/use-conversations";
import { queryClient } from "@/lib/query-provider";

export type ChatMessage = { id: string; from: "user" | "coach"; text: string; createdAt: string };

export type SessionState = {
  messages: ChatMessage[];
  isSending: boolean;
  isThinking: boolean;
  sendError: boolean;
};

export const EMPTY_SESSION: SessionState = { messages: [], isSending: false, isThinking: false, sendError: false };

const THINKING_TIMEOUT_MS = 600;

let nextLocalId = 0;
function newLocalId(): string {
  nextLocalId += 1;
  return `local-${nextLocalId}`;
}

type SendMessageArgs = {
  key: string;
  text: string;
  locale: string;
  conversationId?: string;
  onConversationCreated: (newConversationId: string) => void;
  budgetExceededMessage: string;
};

type ChatStore = {
  sessions: Record<string, SessionState>;
  budgetExceeded: boolean;
  sendMessage: (args: SendMessageArgs) => Promise<void>;
};

export const useChatStore = create<ChatStore>((set, get) => ({
  sessions: {},
  budgetExceeded: false,

  async sendMessage({ key, text, locale, conversationId, onConversationCreated, budgetExceededMessage }) {
    const trimmed = text.trim();
    const existing = get().sessions[key] ?? EMPTY_SESSION;
    if (!trimmed || existing.isSending) return;

    const coachMessageId = newLocalId();
    const sentAt = new Date().toISOString();

    function patch(activeKey: string, delta: Partial<SessionState> | ((s: SessionState) => Partial<SessionState>)) {
      set((state) => {
        const current = state.sessions[activeKey] ?? EMPTY_SESSION;
        const applied = typeof delta === "function" ? delta(current) : delta;
        return { sessions: { ...state.sessions, [activeKey]: { ...current, ...applied } } };
      });
    }

    patch(key, (s) => ({
      messages: [
        ...s.messages,
        { id: newLocalId(), from: "user", text: trimmed, createdAt: sentAt },
        { id: coachMessageId, from: "coach", text: "", createdAt: sentAt },
      ],
      isSending: true,
      sendError: false,
    }));

    let activeKey = key;
    let lastChunkAt = Date.now();
    const thinkingTimer = setInterval(() => {
      patch(activeKey, { isThinking: Date.now() - lastChunkAt > THINKING_TIMEOUT_MS });
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
            const newKey = event.conversation_id;
            set((state) => {
              const sessions = { ...state.sessions };
              sessions[newKey] = sessions[activeKey] ?? EMPTY_SESSION;
              delete sessions[activeKey];
              return { sessions };
            });
            activeKey = newKey;
            queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY });
            onConversationCreated(newKey);
          }
          if (event.text === undefined) return;
          lastChunkAt = Date.now();
          patch(activeKey, (s) => ({
            isThinking: false,
            messages: s.messages.map((m) => (m.id === coachMessageId ? { ...m, text: m.text + event.text } : m)),
          }));
        },
      );
    } catch (err) {
      const detail =
        err instanceof ApiError && err.body && typeof err.body === "object" && "detail" in err.body
          ? (err.body as { detail?: { error?: string } }).detail
          : null;
      const code = detail?.error ?? null;

      if (code === "budget_exceeded") {
        patch(activeKey, (s) => ({
          messages: s.messages.map((m) => (m.id === coachMessageId ? { ...m, text: budgetExceededMessage } : m)),
        }));
        set({ budgetExceeded: true });
      } else {
        patch(activeKey, (s) => ({
          sendError: true,
          messages: s.messages.filter((m) => m.id !== coachMessageId),
        }));
      }
    } finally {
      clearInterval(thinkingTimer);
      patch(activeKey, { isThinking: false, isSending: false });
    }
  },
}));
```

Design notes for the implementer:
- `key` is `"new"` while no conversation exists yet, or the real `conversationId` once one does — `ChatScreen` (Task 4) computes this as `conversationId ?? "new"`.
- Appending stream text keys off `m.id === coachMessageId` rather than "last item in the array" (which is what the old `next[next.length - 1] = ...` code did). This is strictly more robust — it can never silently write to a nonexistent array slot the way the original bug's failure mode did, even under some other future race.
- `budgetExceeded` is intentionally store-wide, not per-session: it reflects a user-account-wide token cap from the backend (`backend/routes/chat.py`'s `TOKEN_BUDGET_LIMIT`), not a per-conversation limit, so it should stay true across every conversation once hit, not reset when switching chats (the old per-component `useState` version reset it on every remount, including a same-conversation switch — a latent bug not exercised by today's issue, fixed for free here).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run tests/chat-store.test.ts` from `frontend/`.
Expected: PASS — all 5 tests green.

- [ ] **Step 5: Typecheck**

Run: `npx tsc --noEmit` from `frontend/`.
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd frontend
git add lib/stores/chat-store.ts tests/chat-store.test.ts
git commit -m "feat(frontend): add chat store to survive Page remounts across new-conversation navigation"
```

---

### Task 4: Wire ChatScreen to the store, remove local state and debug logs

**Files:**
- Modify: `frontend/components/chat-screen.tsx`
- Modify: `frontend/tests/chat-screen.test.tsx`

**Interfaces:**
- Consumes: `useChatStore`, `EMPTY_SESSION`, `ChatMessage` from `frontend/lib/stores/chat-store.ts` (Task 3).
- Produces: no new exports — `ChatScreen`'s public props (`locale`, `conversationId?`, `onConversationCreated`) are unchanged, so the two page files (`app/[locale]/(app)/chat/[[...conversationId]]/page.tsx`) need no changes.

- [ ] **Step 1: Write the failing regression test**

This test reproduces the original bug end-to-end at the component level, simulating exactly what `router.replace` does in production (Page remount via a changed `key`), and must fail against today's `chat-screen.tsx` before this task's implementation step.

In `frontend/tests/chat-screen.test.tsx`, first replace the `renderWithProviders` helper (used by every existing test — keep it backward compatible) with a version that also exposes a same-provider `rerender`:

```tsx
function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient();
  const wrap = (node: React.ReactNode) => (
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={en}>
        {node}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
  const utils = render(wrap(ui));
  return { ...utils, rerenderWithProviders: (nextUi: React.ReactNode) => utils.rerender(wrap(nextUi)) };
}
```

Then add, at the end of the `describe("ChatScreen", ...)` block, before the closing `});`:

```tsx
  it("keeps the coach reply visible after the parent remounts ChatScreen once the conversation id arrives (simulating router.replace's Page remount)", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = input.toString();
      if (url.includes("/conversations/conv-new/messages")) {
        return Promise.resolve(jsonResponse({ messages: [], has_more: false }));
      }
      return Promise.resolve(sseResponse(["Hey", " there!"], "conv-new"));
    });

    let createdId: string | undefined;
    const onConversationCreated = vi.fn((id: string) => {
      createdId = id;
    });

    const { rerenderWithProviders } = renderWithProviders(
      <ChatScreen key="new" locale="en" onConversationCreated={onConversationCreated} />
    );

    const input = screen.getByPlaceholderText(en.chat.placeholder);
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(onConversationCreated).toHaveBeenCalledWith("conv-new"));

    // Next.js remounts the Page (and everything under it) the instant the
    // URL's own dynamic segment changes — simulate that here with a
    // different `key`, which forces React to unmount the old ChatScreen
    // and mount a fresh instance, exactly like the real navigation does.
    rerenderWithProviders(
      <ChatScreen key={createdId} locale="en" conversationId={createdId} onConversationCreated={onConversationCreated} />
    );

    await waitFor(() => expect(screen.getByText("Hey there!")).toBeInTheDocument());
  });
```

Also add a `beforeEach`/`afterEach` reset for the store — the store is a module-level singleton shared across every test in this file (several reuse `CONVERSATION_ID = "conv-1"`), so without a reset, state leaks between tests. Add near the top of the `describe` block:

```tsx
import { useChatStore } from "../lib/stores/chat-store";
```

and change:
```tsx
describe("ChatScreen", () => {
  afterEach(() => vi.restoreAllMocks());
```
to:
```tsx
describe("ChatScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useChatStore.setState({ sessions: {}, budgetExceeded: false }, true);
  });
```

- [ ] **Step 2: Run the tests to verify the new test fails**

Run: `npx vitest run tests/chat-screen.test.tsx -t "keeps the coach reply visible after the parent remounts"` from `frontend/`.
Expected: FAIL — the reply text never appears in the remounted instance (this is today's actual bug, reproduced in a test).

- [ ] **Step 3: Rewire chat-screen.tsx**

Read the current file at `frontend/components/chat-screen.tsx` first (300 lines) to get exact surrounding context, then make these changes:

1. Add the import:
```tsx
import { EMPTY_SESSION, useChatStore } from "@/lib/stores/chat-store";
```

2. Delete these local state lines (currently around lines 36–41):
```tsx
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [sendError, setSendError] = useState(false);
  const [budgetExceeded, setBudgetExceeded] = useState(false);
```
Replace with:
```tsx
  const [draft, setDraft] = useState("");
  const sessionKey = conversationId ?? "new";
  const session = useChatStore((s) => s.sessions[sessionKey] ?? EMPTY_SESSION);
  const budgetExceeded = useChatStore((s) => s.budgetExceeded);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const messages = session.messages;
  const isSending = session.isSending;
  const isThinking = session.isThinking;
  const sendError = session.sendError;
```

3. Delete the now-unused local `Message` type re-declaration only if the store's `ChatMessage` type fully replaces it — check: `type Message = ...` at the top of the file can be deleted and replaced by importing `ChatMessage` from the store, OR left as a local type alias `type Message = ChatMessage` if `historyMessages`'s `useMemo<Message[]>` still needs the name. Simplest: keep the file's own `Message` type exactly as-is (it already matches `ChatMessage`'s shape field-for-field) — no change needed here, since TypeScript structural typing means the two types are interchangeable without any import. Leave the existing `type Message = { id: string; from: "user" | "coach"; text: string; createdAt: string };` untouched.

4. Delete the two debug-log-carrying effects entirely (currently around lines 47–55):
```tsx
  useEffect(() => {
    console.log("[debug] ChatScreen mounted, conversationId =", conversationId);
    return () => console.log("[debug] ChatScreen UNMOUNTED, conversationId was =", conversationId);
  }, []);

  useEffect(() => {
    console.log("[debug] conversationId changed -> clearing local messages, conversationId =", conversationId);
    setMessages([]);
  }, [conversationId]);
```
Delete both — no replacement. The store already scopes `messages` per `sessionKey`, so switching conversations naturally reads a different (correctly empty-until-sent-in) slice; there's nothing left to clear.

5. Delete the stray pre-existing debug line (currently around line 92, right after the `historyMessages` `useMemo`):
```tsx
  console.log("[debug] history query state:", history.data);
```

6. Delete the stray pre-existing debug line (currently around line 166, right before the scroll-into-view `useEffect`):
```tsx
  console.log(allMessages);
```

7. Replace the entire body of `handleSend` (currently lines ~94–151) with:
```tsx
  async function handleSend(overrideText?: string) {
    const trimmed = (overrideText ?? draft).trim();
    if (!trimmed || isSending) return;
    setDraft("");
    await sendMessage({
      key: sessionKey,
      text: trimmed,
      locale,
      conversationId,
      onConversationCreated,
      budgetExceededMessage: t("budgetExceeded"),
    });
  }
```

8. `handleSend`'s callers (the suggestion-chip `onClick={() => handleSend(suggestion)}` and the send button/Enter-key handlers) are unchanged — they already just call `handleSend()`.

- [ ] **Step 4: Run the full chat-screen test file**

Run: `npx vitest run tests/chat-screen.test.tsx` from `frontend/`.
Expected: PASS — all tests green, including the new remount regression test and every pre-existing test (they exercise the same DOM-visible behavior, now backed by the store instead of local state).

- [ ] **Step 5: Run the store tests again to make sure nothing regressed**

Run: `npx vitest run tests/chat-store.test.ts` from `frontend/`.
Expected: PASS.

- [ ] **Step 6: Typecheck the whole frontend**

Run: `npx tsc --noEmit` from `frontend/`.
Expected: no errors.

- [ ] **Step 7: Manual verification in the browser**

Start the dev server, go to `/chat` (a genuinely new chat, not one from the sidebar), send a message, and confirm the reply streams in and stays visible — no hard refresh needed. Then open the sidebar and confirm the new conversation appears in "Recent" without waiting (this is the `invalidateQueries` call from Task 3 taking effect).

- [ ] **Step 8: Commit**

```bash
cd frontend
git add components/chat-screen.tsx tests/chat-screen.test.tsx
git commit -m "fix(frontend): read chat state from a store instead of Page-local state

Fixes the bug where a first message's reply never appeared until a hard
refresh. Next.js remounts a Page's own component whenever its dynamic
route segment changes, which was wiping ChatScreen's local state mid-stream
the moment router.replace moved /chat to /chat/{id}. Chat state now lives
in a Zustand store outside the component tree, unaffected by the remount."
```

---

## Self-Review

**Spec coverage:** The only requirement (from the debugging conversation) is: fix the first-message-invisible-until-refresh bug via a Zustand store, without patch-fixes (deferred navigation, client-generated ids). Task 3 creates the store with the exact bug reproduced as a test; Task 4 wires the component to it and adds a component-level regression test simulating the real remount. The incidentally-discovered sidebar staleness bug is fixed for free via the `invalidateQueries` call in Task 3, called out explicitly rather than silently. Covered.

**Placeholder scan:** All test and implementation code above is complete and runnable, no "TODO"/"similar to Task N" placeholders.

**Type consistency:** `SessionState`, `ChatMessage`, `EMPTY_SESSION`, `useChatStore`, `sendMessage`'s argument shape (`SendMessageArgs`) are defined once in Task 3 and used identically in Task 4. `sessionKey` (`conversationId ?? "new"`) is computed the same way in both the store's test mocks and the component.
