import logging
import data.db as db

logger = logging.getLogger(__name__)

FOLD_TOKEN_THRESHOLD = 40_000
KEEP_RECENT_MESSAGES = 15

FOLD_SYSTEM_PROMPT = (
    "You compress running-coach conversation history into a compact summary."
)

FOLD_USER_PROMPT_TEMPLATE = """Existing summary (may be empty on first fold):
{existing_summary}

New messages to fold in:
{chunk_text}

Write an updated summary under 300 words. Focus on conversational context and \
in-progress topics — do not restate durable facts (goals, injuries, preferences) \
that would already be captured separately via long-term memory. Preserve concrete \
plans discussed and decisions made over conversational flavor. Do not restate \
what's already covered — merge and compress."""


def _content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    parts = []
    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            parts.append(block.get("text", ""))
        elif block_type == "tool_result":
            parts.append(f"[tool result: {block.get('content')}]")
        elif block_type == "tool_use":
            parts.append(f"[used tool: {block.get('name', '?')}]")
        else:
            parts.append(f"[{block_type}]")
    return " ".join(parts)


def _render_chunk(chunk: list[dict]) -> str:
    lines = [f"{row['role']}: {_content_to_text(row['content'])}" for row in chunk]
    return "\n".join(lines)


def _is_orphaned_tool_result(row: dict) -> bool:
    content = row["content"]
    return isinstance(content, list) and any(
        b.get("type") == "tool_result" for b in content
    )


async def maybe_fold(
    conversation_id: str, system_prompt: str, rows: list[dict], tools: list[dict]
) -> list[dict]:
    from backend.agent import client, model

    messages_for_count = [{"role": r["role"], "content": r["content"]} for r in rows]
    count = await client.messages.count_tokens(
        model=model, system=system_prompt, tools=tools, messages=messages_for_count
    )

    if count.input_tokens <= FOLD_TOKEN_THRESHOLD:
        return rows
    if len(rows) <= KEEP_RECENT_MESSAGES:
        return rows

    cutoff = len(rows) - KEEP_RECENT_MESSAGES
    while cutoff > 0 and _is_orphaned_tool_result(rows[cutoff]):
        cutoff -= 1
    chunk = rows[:cutoff]

    existing = db.get_conversation_summary(conversation_id)
    existing_summary = existing["summary_text"] if existing else "(none yet)"

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=FOLD_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": FOLD_USER_PROMPT_TEMPLATE.format(
                    existing_summary=existing_summary,
                    chunk_text=_render_chunk(chunk),
                ),
            }
        ],
    )
    new_summary = next(block.text for block in response.content if block.type == "text")

    db.upsert_conversation_summary(conversation_id, new_summary, chunk[-1]["id"])

    return rows[cutoff:]
