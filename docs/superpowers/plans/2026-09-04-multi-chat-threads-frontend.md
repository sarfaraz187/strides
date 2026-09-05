# Multi-Chat Threads — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the frontend chat UI to the new `/conversations` backend (from `docs/superpowers/plans/2026-09-04-multi-chat-threads-backend.md`) — a sidebar of persistent threads (create, list, rename, pin, delete, search) and a per-conversation chat view, replacing the single flat chat history.

**Architecture:** `ChatScreen` becomes conversation-scoped (`conversationId` prop, history fetched from `/conversations/{id}/messages`, first-message creation returns a new id via the first SSE event). Route structure changes to `/chat` (empty "new chat" state) and `/chat/[conversationId]` (an existing thread). A new `ChatSidebar` component (backed by a `useConversations` hook) renders as a persistent desktop column via `chat/layout.tsx`, and as a full mobile screen at `/chat/list` reached via a hamburger icon.

**Tech Stack:** Next.js App Router (client components, React 19 `use()` for async `params`), React Query (`@tanstack/react-query`), next-intl, Vitest + Testing Library (existing conventions in `frontend/tests/`).

**Spec:** `docs/superpowers/specs/2026-09-04-multi-chat-threads-design.md`

## Global Constraints

- No global state library — conversation list and messages are React Query state; "which conversation is active" is owned by the route (spec: "Decisions").
- Search is title-only.
- Rename rejects empty/whitespace titles.
- Deleting the active conversation redirects to the empty "New chat" state (`/chat`).
- No real-time cross-device sync — rely on React Query's default refetch-on-focus/remount.
- Backend contract (already implemented): `GET /conversations?search=`, `PATCH /conversations/{id}` (body `{title?, pinned?}`), `DELETE /conversations/{id}`, `GET /conversations/{id}/messages?before_id=&limit=`, `POST /chat` body `{message, conversation_id?}` whose SSE stream's first event is always `{"conversation_id": "..."}`.

---

### Task 1: Conversations API client + `useConversations` hook

**Files:**
- Create: `frontend/lib/conversations-api.ts`
- Create: `frontend/hooks/use-conversations.ts`
- Create: `frontend/tests/conversations-api.test.ts`
- Create: `frontend/tests/use-conversations.test.tsx`

**Interfaces:**
- Consumes: `apiFetch` (`frontend/lib/api.ts`, unchanged).
- Produces: `type Conversation = { id: string; title: string; pinned: boolean; created_at: string; updated_at: string }`, `type ApiMessage = { id: number; role: "user" | "assistant"; content: string; created_at: string }`, `type ChatHistoryPage = { messages: ApiMessage[]; has_more: boolean }`, `listConversations(search?: string): Promise<Conversation[]>`, `updateConversation(id: string, updates: { title?: string; pinned?: boolean }): Promise<{ status: string }>`, `deleteConversation(id: string): Promise<{ status: string }>`, `getConversationMessages(id: string, beforeId?: number, limit?: number): Promise<ChatHistoryPage>`, `useConversations(search: string) -> { conversations, pinned, recent, rename, setPinned, remove }`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/conversations-api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  deleteConversation,
  getConversationMessages,
  listConversations,
  updateConversation,
} from "../lib/conversations-api";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}

describe("conversations-api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("listConversations calls /conversations without a search param when omitted", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse([]));

    await listConversations();

    expect(mockFetch).toHaveBeenCalledWith("https://api.example.com/conversations", expect.anything());
  });

  it("listConversations includes an encoded search param when given", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse([]));

    await listConversations("shin pain");

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/conversations?search=shin%20pain",
      expect.anything()
    );
  });

  it("updateConversation PATCHes the given fields", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ status: "ok" }));

    await updateConversation("conv-1", { title: "Renamed" });

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/conversations/conv-1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ title: "Renamed" }) })
    );
  });

  it("deleteConversation DELETEs the conversation", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ status: "ok" }));

    await deleteConversation("conv-1");

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/conversations/conv-1",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("getConversationMessages includes limit and before_id", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ messages: [], has_more: false }));

    await getConversationMessages("conv-1", 5, 20);

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/conversations/conv-1/messages?limit=20&before_id=5",
      expect.anything()
    );
  });
});
```

Create `frontend/tests/use-conversations.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useConversations } from "../hooks/use-conversations";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useConversations", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("splits conversations into pinned and recent", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([
        { id: "1", title: "Pinned chat", pinned: true, created_at: "t", updated_at: "t" },
        { id: "2", title: "Recent chat", pinned: false, created_at: "t", updated_at: "t" },
      ])
    );

    const { result } = renderHook(() => useConversations(""), { wrapper });

    await waitFor(() => expect(result.current.conversations).toHaveLength(2));
    expect(result.current.pinned.map((c) => c.id)).toEqual(["1"]);
    expect(result.current.recent.map((c) => c.id)).toEqual(["2"]);
  });

  it("rename calls the mutation and refetches the list", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse([]));

    const { result } = renderHook(() => useConversations(""), { wrapper });
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());

    result.current.rename({ id: "1", title: "New title" });

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "https://api.example.com/conversations/1",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ title: "New title" }) })
      )
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run tests/conversations-api.test.ts tests/use-conversations.test.tsx`
Expected: FAIL — `frontend/lib/conversations-api.ts` and `frontend/hooks/use-conversations.ts` don't exist yet.

- [ ] **Step 3: Implement the API client**

Create `frontend/lib/conversations-api.ts`:

```ts
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
```

- [ ] **Step 4: Implement the hook**

Create `frontend/hooks/use-conversations.ts`:

```ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteConversation, listConversations, updateConversation } from "@/lib/conversations-api";

export const CONVERSATIONS_QUERY_KEY = ["conversations"];

export function useConversations(search: string) {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: [...CONVERSATIONS_QUERY_KEY, search],
    queryFn: () => listConversations(search || undefined),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY });
  }

  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => updateConversation(id, { title }),
    onSuccess: invalidate,
  });

  const pinMutation = useMutation({
    mutationFn: ({ id, pinned }: { id: string; pinned: boolean }) => updateConversation(id, { pinned }),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onSuccess: invalidate,
  });

  const conversations = data ?? [];

  return {
    conversations,
    pinned: conversations.filter((c) => c.pinned),
    recent: conversations.filter((c) => !c.pinned),
    rename: renameMutation.mutate,
    setPinned: (id: string, pinned: boolean) => pinMutation.mutate({ id, pinned }),
    remove: deleteMutation.mutate,
  };
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run tests/conversations-api.test.ts tests/use-conversations.test.tsx`
Expected: PASS

---

### Task 2: Make `ChatScreen` conversation-scoped

**Files:**
- Modify: `frontend/lib/api.ts` (`apiStream` event shape)
- Modify: `frontend/components/chat-screen.tsx`
- Modify: `frontend/messages/en.json`, `frontend/messages/de.json` (add `chat.emptyTitle`, `chat.emptySubtitle`, `chat.suggestions`)
- Modify: `frontend/tests/chat-screen.test.tsx` (full rewrite)

**Interfaces:**
- Consumes: `getConversationMessages`, `type ChatHistoryPage` (Task 1).
- Produces: `ChatScreen({ locale, conversationId?, onConversationCreated }) `— `onConversationCreated: (conversationId: string) => void` is called once, the first time a brand-new chat's first SSE event carries a `conversation_id` (i.e. only when the `conversationId` prop was not already set).

- [ ] **Step 1: Update `apiStream`'s callback to expose the full parsed event**

In `frontend/lib/api.ts`, replace:

```ts
export async function apiStream(
  path: string,
  options: RequestInit,
  onChunk: (text: string) => void
): Promise<void> {
```
...
```ts
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const { text } = JSON.parse(line.slice("data: ".length));
      onChunk(text);
    }
```

with:

```ts
export type ChatStreamEvent = { text?: string; conversation_id?: string };

export async function apiStream(
  path: string,
  options: RequestInit,
  onEvent: (event: ChatStreamEvent) => void
): Promise<void> {
```
...
```ts
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      onEvent(JSON.parse(line.slice("data: ".length)));
    }
```

(Only the parameter name/type and the loop body change — everything else in the function is unchanged.)

- [ ] **Step 2: Write the failing tests (full replacement of `frontend/tests/chat-screen.test.tsx`)**

Replace the entire contents of `frontend/tests/chat-screen.test.tsx` with:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import en from "../messages/en.json";
import { ChatScreen } from "../components/chat-screen";

const CONVERSATION_ID = "conv-1";

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={en}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}

function errorResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status });
}

function sseResponse(chunks: string[], conversationId: string = CONVERSATION_ID) {
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

describe("ChatScreen", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the typed message with the current locale and conversation id, and shows the reply", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    const mockFetch = vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = input.toString();
      if (url.includes(`/conversations/${CONVERSATION_ID}/messages`)) {
        return Promise.resolve(jsonResponse({ messages: [], has_more: false }));
      }
      return Promise.resolve(sseResponse(["8km easy ", "Saturday."]));
    });

    renderWithProviders(
      <ChatScreen locale="en" conversationId={CONVERSATION_ID} onConversationCreated={vi.fn()} />
    );

    const input = screen.getByPlaceholderText(en.chat.placeholder);
    fireEvent.change(input, { target: { value: "what should I do saturday?" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByText("8km easy Saturday.")).toBeInTheDocument());

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/chat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          message: "what should I do saturday?",
          locale: "en",
          conversation_id: CONVERSATION_ID,
        }),
      })
    );
  });

  it("loads history for the given conversation on mount and renders it oldest-to-newest", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = input.toString();
      if (url.includes(`/conversations/${CONVERSATION_ID}/messages`)) {
        return Promise.resolve(
          jsonResponse({
            messages: [
              { id: 2, role: "assistant", content: "Second reply", created_at: "2026-08-14T12:11:00Z" },
              { id: 1, role: "user", content: "First message", created_at: "2026-08-14T12:11:00Z" },
            ],
            has_more: false,
          })
        );
      }
      return Promise.resolve(sseResponse(["unused"]));
    });

    renderWithProviders(
      <ChatScreen locale="en" conversationId={CONVERSATION_ID} onConversationCreated={vi.fn()} />
    );

    await waitFor(() => expect(screen.getByText("Second reply")).toBeInTheDocument());

    const rendered = screen.getAllByText(/^First message$|^Second reply$/).map((el) => el.textContent);
    expect(rendered).toEqual(["First message", "Second reply"]);
  });

  it("fetches an older page with before_id when scrolled to the top", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    const mockFetch = vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = input.toString();
      if (url.includes("before_id=5")) {
        return Promise.resolve(
          jsonResponse({
            messages: [{ id: 4, role: "user", content: "Older message", created_at: "2026-08-14T12:11:00Z" }],
            has_more: false,
          })
        );
      }
      if (url.includes(`/conversations/${CONVERSATION_ID}/messages`)) {
        return Promise.resolve(
          jsonResponse({
            messages: [{ id: 5, role: "user", content: "Newest message", created_at: "2026-08-14T12:11:00Z" }],
            has_more: true,
          })
        );
      }
      return Promise.resolve(sseResponse(["unused"]));
    });

    renderWithProviders(
      <ChatScreen locale="en" conversationId={CONVERSATION_ID} onConversationCreated={vi.fn()} />
    );

    await waitFor(() => expect(screen.getByText("Newest message")).toBeInTheDocument());

    const scrollContainer = screen.getByTestId("chat-scroll-container");
    Object.defineProperty(scrollContainer, "scrollTop", { value: 0, configurable: true, writable: true });
    fireEvent.scroll(scrollContainer);

    await waitFor(() => expect(screen.getByText("Older message")).toBeInTheDocument());
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining("before_id=5"), expect.anything());
  });

  it("does not duplicate a sent message while it streams in", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = input.toString();
      if (url.includes(`/conversations/${CONVERSATION_ID}/messages`)) {
        return Promise.resolve(jsonResponse({ messages: [], has_more: false }));
      }
      return Promise.resolve(sseResponse(["8km easy Saturday."]));
    });

    renderWithProviders(
      <ChatScreen locale="en" conversationId={CONVERSATION_ID} onConversationCreated={vi.fn()} />
    );

    const input = screen.getByPlaceholderText(en.chat.placeholder);
    fireEvent.change(input, { target: { value: "what should I do saturday?" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getAllByText("8km easy Saturday.")).toHaveLength(1);
      expect(screen.getAllByText("what should I do saturday?")).toHaveLength(1);
    });
  });

  it("shows a thinking indicator during a gap between chunks, then hides it when text resumes", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.useFakeTimers({ shouldAdvanceTime: true });

    let releaseSecondChunk: () => void = () => {};
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ conversation_id: CONVERSATION_ID })}\n\n`));
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ text: "Checking" })}\n\n`));
        releaseSecondChunk = () => {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ text: " your runs" })}\n\n`));
          controller.close();
        };
      },
    });

    vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = input.toString();
      if (url.includes(`/conversations/${CONVERSATION_ID}/messages`)) {
        return Promise.resolve(jsonResponse({ messages: [], has_more: false }));
      }
      return Promise.resolve(new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } }));
    });

    renderWithProviders(
      <ChatScreen locale="en" conversationId={CONVERSATION_ID} onConversationCreated={vi.fn()} />
    );

    const input = screen.getByPlaceholderText(en.chat.placeholder);
    fireEvent.change(input, { target: { value: "how was my week?" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByText("Checking")).toBeInTheDocument());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    expect(screen.getByTestId("thinking-indicator")).toBeInTheDocument();

    await act(async () => {
      releaseSecondChunk();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.queryByTestId("thinking-indicator")).not.toBeInTheDocument();

    vi.useRealTimers();
  });

  it("renders the budget-exceeded message as a normal coach bubble and disables input", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = input.toString();
      if (url.includes(`/conversations/${CONVERSATION_ID}/messages`)) {
        return Promise.resolve(jsonResponse({ messages: [], has_more: false }));
      }
      return Promise.resolve(errorResponse(403, { detail: { error: "budget_exceeded" } }));
    });

    renderWithProviders(
      <ChatScreen locale="en" conversationId={CONVERSATION_ID} onConversationCreated={vi.fn()} />
    );

    const input = screen.getByPlaceholderText(en.chat.placeholder);
    fireEvent.change(input, { target: { value: "another training plan please" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByText(en.chat.budgetExceeded)).toBeInTheDocument());

    expect(screen.getByPlaceholderText(en.chat.placeholder)).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("shows the existing send-failed error line when the message is too long, input stays enabled", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = input.toString();
      if (url.includes(`/conversations/${CONVERSATION_ID}/messages`)) {
        return Promise.resolve(jsonResponse({ messages: [], has_more: false }));
      }
      return Promise.resolve(errorResponse(400, { detail: { error: "message_too_long" } }));
    });

    renderWithProviders(
      <ChatScreen locale="en" conversationId={CONVERSATION_ID} onConversationCreated={vi.fn()} />
    );

    const input = screen.getByPlaceholderText(en.chat.placeholder);
    fireEvent.change(input, { target: { value: "x".repeat(501) } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByText(en.chat.sendFailed)).toBeInTheDocument());

    expect(screen.getByPlaceholderText(en.chat.placeholder)).not.toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).not.toBeDisabled();
  });

  it("caps the input field at 500 characters", () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockImplementation((input) => {
      const url = input.toString();
      if (url.includes(`/conversations/${CONVERSATION_ID}/messages`)) {
        return Promise.resolve(jsonResponse({ messages: [], has_more: false }));
      }
      return Promise.resolve(sseResponse(["unused"]));
    });

    renderWithProviders(
      <ChatScreen locale="en" conversationId={CONVERSATION_ID} onConversationCreated={vi.fn()} />
    );

    const input = screen.getByPlaceholderText(en.chat.placeholder) as HTMLInputElement;
    expect(input.maxLength).toBe(500);
  });

  it("shows suggestion chips in the empty new-chat state and creates a conversation on click", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    const onConversationCreated = vi.fn();
    const mockFetch = vi
      .spyOn(global, "fetch")
      .mockImplementation(() => Promise.resolve(sseResponse(["Sounds good."], "conv-new")));

    renderWithProviders(<ChatScreen locale="en" onConversationCreated={onConversationCreated} />);

    expect(screen.getByText(en.chat.emptyTitle)).toBeInTheDocument();
    fireEvent.click(screen.getByText(en.chat.suggestions[0]));

    await waitFor(() => expect(onConversationCreated).toHaveBeenCalledWith("conv-new"));
    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/chat",
      expect.objectContaining({
        body: JSON.stringify({ message: en.chat.suggestions[0], locale: "en", conversation_id: null }),
      })
    );
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx vitest run tests/chat-screen.test.tsx`
Expected: FAIL — `ChatScreen` doesn't accept `conversationId`/`onConversationCreated` yet, history still hits `/chat/history`, no empty-state suggestions.

- [ ] **Step 4: Add the new i18n keys**

In `frontend/messages/en.json`, inside the `"chat"` object, add (alongside the existing keys):

```json
"emptyTitle": "New chat with Coach",
"emptySubtitle": "Ask about training plans, recovery, or your recent runs to get started.",
"suggestions": [
  "What's the weather like now",
  "What was my last run",
  "Plan today's run",
  "How's my training going"
]
```

In `frontend/messages/de.json`, inside the `"chat"` object, add:

```json
"emptyTitle": "Neuer Chat mit Coach",
"emptySubtitle": "Frag nach Trainingsplänen, Erholung oder deinen letzten Läufen, um loszulegen.",
"suggestions": [
  "Wie ist das Wetter gerade",
  "Wie war mein letzter Lauf",
  "Plane das heutige Training",
  "Wie läuft mein Training"
]
```

- [ ] **Step 5: Rewrite `chat-screen.tsx`**

In `frontend/components/chat-screen.tsx`:

Replace the type definitions and query-key constant:
```tsx
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
```
with:
```tsx
const HISTORY_PAGE_SIZE = 20;
const SCROLL_TOP_THRESHOLD = 40;
const SCROLL_BOTTOM_THRESHOLD = 80;

function conversationMessagesQueryKey(conversationId: string | undefined) {
  return ["conversation", conversationId, "messages"];
}
```

Add the import (alongside the existing `@/lib/api` import):
```tsx
import { getConversationMessages } from "@/lib/conversations-api";
```

Replace the component signature:
```tsx
export function ChatScreen({ locale }: { locale: string }) {
```
with:
```tsx
export function ChatScreen({
  locale,
  conversationId,
  onConversationCreated,
}: {
  locale: string;
  conversationId?: string;
  onConversationCreated: (conversationId: string) => void;
}) {
```

Add a reset effect directly after the existing `useState`/`useRef` declarations (before `const history = ...`):
```tsx
  useEffect(() => {
    setMessages([]);
  }, [conversationId]);
```

Replace the `history` query:
```tsx
  const history = useInfiniteQuery({
    queryKey: CHAT_HISTORY_QUERY_KEY,
    queryFn: ({ pageParam }: { pageParam: number | undefined }) => apiFetch<ChatHistoryPage>(`/chat/history?limit=${HISTORY_PAGE_SIZE}${pageParam ? `&before_id=${pageParam}` : ""}`),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.messages[lastPage.messages.length - 1]?.id : undefined),
    // Messages sent this session live only in local `messages` state (below),
    // not in this query's cache. A background refetch (e.g. on window focus)
    // would pull those same, now-persisted messages back in as `historyMessages`
    // and render them twice alongside the untouched local copies. History only
    // changes via `fetchNextPage`, so there's no reason for it to refetch itself.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
```
with:
```tsx
  const history = useInfiniteQuery({
    queryKey: conversationMessagesQueryKey(conversationId),
    queryFn: ({ pageParam }: { pageParam: number | undefined }) =>
      getConversationMessages(conversationId as string, pageParam, HISTORY_PAGE_SIZE),
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
```

Replace `handleSend`'s signature and body:
```tsx
  async function handleSend() {
    const trimmed = draft.trim();
    if (!trimmed || isSending) return;
```
with:
```tsx
  async function handleSend(overrideText?: string) {
    const trimmed = (overrideText ?? draft).trim();
    if (!trimmed || isSending) return;
```

Replace the `apiStream` call inside `handleSend`:
```tsx
    try {
      await apiStream("/chat", { method: "POST", body: JSON.stringify({ message: trimmed, locale }) }, (chunk) => {
        lastChunkAtRef.current = Date.now();
        setIsThinking(false);
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, text: last.text + chunk };
          return next;
        });
      });
    } catch (err) {
```
with:
```tsx
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
        }
      );
    } catch (err) {
```

Update the send button and Enter-key handlers to call `handleSend()` with no args (they already do — `onClick={handleSend}` becomes `onClick={() => handleSend()}` since `handleSend` is no longer zero-arg-safe as an event handler):
```tsx
        <Button aria-label="send" onClick={handleSend} disabled={isSending || budgetExceeded} className="h-11 w-11 rounded-full bg-primary p-0 lg:h-12 lg:w-12">
```
with:
```tsx
        <Button aria-label="send" onClick={() => handleSend()} disabled={isSending || budgetExceeded} className="h-11 w-11 rounded-full bg-primary p-0 lg:h-12 lg:w-12">
```
and:
```tsx
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
```
stays as-is (already calls with no args).

Finally, add the empty-state branch. Replace:
```tsx
      <div ref={scrollContainerRef} data-testid="chat-scroll-container" onScroll={handleScroll} className="scrollbar-none flex-1 overflow-y-auto px-2 py-2 lg:px-0 lg:py-2">
        {history.isFetchingNextPage && (
          <div className="flex justify-center py-2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-primary" />
          </div>
        )}
        <AnimatePresence initial={false}>
```
with:
```tsx
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
                <button
                  key={suggestion}
                  onClick={() => handleSend(suggestion)}
                  className="rounded-full border border-border bg-card px-4 py-2 text-sm text-primary"
                >
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
```
and replace the closing of that `AnimatePresence` block:
```tsx
        </AnimatePresence>
      </div>
```
with:
```tsx
        </AnimatePresence>
        </>
        )}
      </div>
```

(`allMessages` is already computed above the `return` statement, unchanged — this branch only adds a conditional around the existing rendering.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run tests/chat-screen.test.tsx tests/api.test.ts`
Expected: PASS

---

### Task 3: Chat routes

**Files:**
- Modify: `frontend/app/[locale]/(app)/chat/page.tsx`
- Create: `frontend/app/[locale]/(app)/chat/[conversationId]/page.tsx`

**Interfaces:**
- Consumes: `ChatScreen` (Task 2).
- Produces: `/​{locale}/chat` (empty new-chat state) and `/{locale}/chat/{conversationId}` (existing thread) routes; both redirect to the latter via `router.replace` once `ChatScreen` reports a newly created conversation.

- [ ] **Step 1: Rewrite the existing chat page**

Replace the full contents of `frontend/app/[locale]/(app)/chat/page.tsx`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { use } from "react";

import { ChatScreen } from "@/components/chat-screen";

export default function ChatPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  const router = useRouter();

  return (
    <ChatScreen
      locale={locale}
      onConversationCreated={(conversationId) => router.replace(`/${locale}/chat/${conversationId}`)}
    />
  );
}
```

- [ ] **Step 2: Create the conversation-specific page**

Create `frontend/app/[locale]/(app)/chat/[conversationId]/page.tsx`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { use } from "react";

import { ChatScreen } from "@/components/chat-screen";

export default function ChatConversationPage({
  params,
}: {
  params: Promise<{ locale: string; conversationId: string }>;
}) {
  const { locale, conversationId } = use(params);
  const router = useRouter();

  return (
    <ChatScreen
      locale={locale}
      conversationId={conversationId}
      onConversationCreated={(newConversationId) => router.replace(`/${locale}/chat/${newConversationId}`)}
    />
  );
}
```

- [ ] **Step 3: Manual check**

Run: `cd frontend && npm run dev`, sign in, open `/en/chat` (should show the empty state with suggestion chips), send a message, confirm the URL updates to `/en/chat/<uuid>`, refresh the page, confirm history reloads for that conversation.

---

### Task 4: `ChatSidebar` — desktop column and mobile list screen

**Files:**
- Create: `frontend/components/chat-sidebar.tsx`
- Create: `frontend/app/[locale]/(app)/chat/layout.tsx`
- Create: `frontend/app/[locale]/(app)/chat/list/page.tsx`
- Modify: `frontend/components/chat-screen.tsx` (header: mobile-only hamburger to the chats list, plus a "+" new-chat icon shown at every breakpoint, matching the mockup's desktop header)
- Modify: `frontend/messages/en.json`, `frontend/messages/de.json` (add `chat.chatsTitle`, `chat.newChat`, `chat.searchPlaceholder`, `chat.pinnedSection`, `chat.recentSection`)
- Create: `frontend/tests/chat-sidebar.test.tsx`

**Interfaces:**
- Consumes: `useConversations` (Task 1).
- Produces: `ChatSidebar({ locale, activeConversationId?, className? })`, rendered persistently in `chat/layout.tsx` on desktop (`hidden lg:flex`) and full-screen in `chat/list/page.tsx` on mobile.

- [ ] **Step 1: Add the new i18n keys**

In `frontend/messages/en.json`, inside `"chat"`, add:
```json
"chatsTitle": "Chats",
"newChat": "New chat",
"searchPlaceholder": "Search chats",
"pinnedSection": "Pinned",
"recentSection": "Recent"
```

In `frontend/messages/de.json`, inside `"chat"`, add:
```json
"chatsTitle": "Chats",
"newChat": "Neuer Chat",
"searchPlaceholder": "Chats durchsuchen",
"pinnedSection": "Angeheftet",
"recentSection": "Kürzlich"
```

- [ ] **Step 2: Write the failing test**

Create `frontend/tests/chat-sidebar.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import en from "../messages/en.json";
import { ChatSidebar } from "../components/chat-sidebar";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={en}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}

describe("ChatSidebar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    replaceMock.mockClear();
  });

  it("renders pinned and recent sections separately", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([
        { id: "1", title: "Weather & last run", pinned: true, created_at: "t", updated_at: "2026-09-01T13:04:00Z" },
        { id: "2", title: "Shin pain advice", pinned: false, created_at: "t", updated_at: "2026-08-20T18:45:00Z" },
      ])
    );

    renderWithProviders(<ChatSidebar locale="en" />);

    await waitFor(() => expect(screen.getByText("Weather & last run")).toBeInTheDocument());
    expect(screen.getByText(en.chat.pinnedSection)).toBeInTheDocument();
    expect(screen.getByText("Shin pain advice")).toBeInTheDocument();
    expect(screen.getByText(en.chat.recentSection)).toBeInTheDocument();
  });

  it("filters the list as the user types in search", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse([]));

    renderWithProviders(<ChatSidebar locale="en" />);

    const search = screen.getByPlaceholderText(en.chat.searchPlaceholder);
    fireEvent.change(search, { target: { value: "shin" } });

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/conversations?search=shin"),
        expect.anything()
      )
    );
  });

  it("deleting a conversation calls the DELETE endpoint", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    const mockFetch = vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([{ id: "1", title: "Old chat", pinned: false, created_at: "t", updated_at: "t" }])
    );

    renderWithProviders(<ChatSidebar locale="en" />);

    await waitFor(() => expect(screen.getByText("Old chat")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("delete"));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "https://api.example.com/conversations/1",
        expect.objectContaining({ method: "DELETE" })
      )
    );
  });

  it("deleting the active conversation redirects to the empty new-chat state", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([{ id: "1", title: "Active chat", pinned: false, created_at: "t", updated_at: "t" }])
    );

    renderWithProviders(<ChatSidebar locale="en" activeConversationId="1" />);

    await waitFor(() => expect(screen.getByText("Active chat")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("delete"));

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/en/chat"));
  });

  it("deleting a non-active conversation does not redirect", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse([{ id: "1", title: "Other chat", pinned: false, created_at: "t", updated_at: "t" }])
    );

    renderWithProviders(<ChatSidebar locale="en" activeConversationId="2" />);

    await waitFor(() => expect(screen.getByText("Other chat")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("delete"));

    await waitFor(() => expect(replaceMock).not.toHaveBeenCalled());
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx vitest run tests/chat-sidebar.test.tsx`
Expected: FAIL — `frontend/components/chat-sidebar.tsx` doesn't exist yet.

- [ ] **Step 4: Implement `ChatSidebar`**

Create `frontend/components/chat-sidebar.tsx`:

```tsx
"use client";

import { Pencil, Plus, Search, Star, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Conversation } from "@/lib/conversations-api";
import { useConversations } from "@/hooks/use-conversations";
import { formatMessageTime } from "@/lib/format-time";
import { cn } from "@/lib/utils";

export function ChatSidebar({
  locale,
  activeConversationId,
  className,
}: {
  locale: string;
  activeConversationId?: string;
  className?: string;
}) {
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
      <div
        key={conversation.id}
        className={cn(
          "group flex items-center justify-between rounded-lg px-3 py-2",
          isActive ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/50"
        )}
      >
        {editingId === conversation.id ? (
          <input
            autoFocus
            value={editingTitle}
            onChange={(e) => setEditingTitle(e.target.value)}
            onBlur={commitEditing}
            onKeyDown={(e) => e.key === "Enter" && commitEditing()}
            className="w-full rounded bg-transparent text-sm font-semibold text-sidebar-foreground outline-none"
          />
        ) : (
          <Link href={`/${locale}/chat/${conversation.id}`} className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-sidebar-foreground">{conversation.title}</div>
            <div className="text-xs text-sidebar-foreground/60">{formatMessageTime(conversation.updated_at)}</div>
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
    <div className={cn("flex w-full flex-col gap-3 bg-sidebar px-4 py-4", className)}>
      <Link
        href={`/${locale}/chat`}
        className="flex items-center gap-2 rounded-lg bg-sidebar-primary px-3 py-2 text-sm font-semibold text-sidebar-primary-foreground"
      >
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

      {pinned.length > 0 && (
        <div>
          <div className="mb-1 px-3 text-xs font-semibold uppercase text-sidebar-foreground/50">
            {t("pinnedSection")}
          </div>
          {pinned.map(renderRow)}
        </div>
      )}

      <div>
        <div className="mb-1 px-3 text-xs font-semibold uppercase text-sidebar-foreground/50">
          {t("recentSection")}
        </div>
        {recent.map(renderRow)}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run tests/chat-sidebar.test.tsx`
Expected: PASS

- [ ] **Step 6: Wire the desktop persistent column**

Create `frontend/app/[locale]/(app)/chat/layout.tsx`:

```tsx
"use client";

import { usePathname } from "next/navigation";
import { use } from "react";

import { ChatSidebar } from "@/components/chat-sidebar";

export default function ChatLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = use(params);
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  const activeConversationId = segments[2] === "list" ? undefined : segments[2];

  return (
    <div className="flex h-full min-h-0 flex-1">
      <ChatSidebar
        locale={locale}
        activeConversationId={activeConversationId}
        className="hidden w-72 shrink-0 border-r border-sidebar-border lg:flex"
      />
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
```

(`segments` is `[locale, "chat", conversationId?]` for a pathname like `/en/chat/abc-123`; the `list` guard keeps the mobile list route from being treated as an "active conversation".)

- [ ] **Step 7: Wire the mobile list screen**

Create `frontend/app/[locale]/(app)/chat/list/page.tsx`:

```tsx
"use client";

import { ArrowLeft, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { use } from "react";

import { ChatSidebar } from "@/components/chat-sidebar";

export default function ChatListPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  const t = useTranslations("chat");

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:hidden">
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
    </div>
  );
}
```

- [ ] **Step 8: Add the mobile hamburger and the always-visible new-chat icon to `ChatScreen`'s header**

In `frontend/components/chat-screen.tsx`, add to the existing imports:
```tsx
import { ArrowRight, Menu, Plus } from "lucide-react";
import Link from "next/link";
```
(merge `Menu`/`Plus` into the existing `lucide-react` import line; add the `next/link` import alongside the other `next/*` imports.)

Replace the header block:
```tsx
      <div className="flex items-center gap-2.5 border-b border-border px-6 py-4 lg:px-0 lg:py-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl">
          <Image src="/icon-512.png" alt="Strides" width={40} height={40} className="h-full w-full object-cover" />
        </div>
        <div>
          <div className="text-sm font-semibold text-primary lg:text-base">{t("coachName")}</div>
          <div className="text-xs text-chat-sync">{t("syncedStatus")}</div>
        </div>
      </div>
```
with:
```tsx
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
        <Link href={`/${locale}/chat`} aria-label="new chat">
          <Plus size={20} />
        </Link>
      </div>
```

- [ ] **Step 9: Run the full frontend test suite and manual check**

Run: `cd frontend && npx vitest run`
Expected: PASS across every test file (chat-screen, chat-sidebar, conversations-api, use-conversations, and the pre-existing suite with no regressions).

Manual check: `npm run dev` — confirm the desktop `/en/chat` view shows the persistent sidebar with pin/rename/delete controls on hover, and that on a narrow viewport the hamburger icon navigates to `/en/chat/list` showing the same list full-screen with a back arrow.

---

## Finishing: verify and commit everything

- [ ] **Step 1: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS — every test added or modified across all four tasks, plus the full pre-existing suite with no regressions.

- [ ] **Step 2: Commit everything in one commit**

```bash
git add frontend/lib/conversations-api.ts frontend/hooks/use-conversations.ts frontend/lib/api.ts \
    frontend/components/chat-screen.tsx frontend/components/chat-sidebar.tsx \
    frontend/app/\[locale\]/\(app\)/chat/page.tsx frontend/app/\[locale\]/\(app\)/chat/\[conversationId\]/page.tsx \
    frontend/app/\[locale\]/\(app\)/chat/layout.tsx frontend/app/\[locale\]/\(app\)/chat/list/page.tsx \
    frontend/messages/en.json frontend/messages/de.json \
    frontend/tests/conversations-api.test.ts frontend/tests/use-conversations.test.tsx \
    frontend/tests/chat-screen.test.tsx frontend/tests/chat-sidebar.test.tsx frontend/tests/api.test.ts
git commit -m "feat: multi-chat threads frontend (sidebar, per-conversation routing, new-chat empty state)"
```
