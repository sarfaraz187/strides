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