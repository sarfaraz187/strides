import logging

import data.db as db
from backend.services.mcp_client import get_tool_schemas, open_mcp_session

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_CHARS = 4000

LOCAL_TOOL_SCHEMAS: list = [
    {
        "name": "save_memory",
        "description": (
            "Save a durable fact about the user that should persist across future "
            "conversations — training goals, injuries/physical constraints, or "
            "standing preferences. Do NOT call this for one-off statements about a "
            "single run or how the user feels today."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact to remember."},
                "category": {
                    "type": "string",
                    "enum": ["goal", "injury", "preference"],
                },
            },
            "required": ["fact", "category"],
        },
    }
]


async def _save_memory(user_id: str, fact: str, category: str) -> str:
    db.save_memory(user_id, fact, category)
    return "Saved."


LOCAL_TOOLS: dict = {"save_memory": _save_memory}


def _build_system_prompt(base_prompt: str, user_id: str) -> str:
    prompt = base_prompt

    memories = db.get_memories(user_id)
    if memories:
        facts = "\n".join(f"- {m['fact']}" for m in memories)
        prompt = f"{prompt}\n\nKnown facts about this user:\n{facts}"

    summary = db.get_conversation_summary(user_id)
    if summary:
        prompt = (
            f"{prompt}\n\nSummary of earlier conversation:\n{summary['summary_text']}"
        )

    return prompt


async def process_query(user_id: str, messages: list[dict]) -> str:
    """Call Claude, executing any requested tools, until it gives a final answer."""
    from backend.agent import SYSTEM_PROMPT, client, model

    system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)

    async with open_mcp_session(user_id) as session:
        tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

        while True:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_prompt,
                tools=tools,
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                messages=messages,
            )

            content_dicts = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": content_dicts})

            if response.stop_reason != "tool_use":
                reply = "\n".join(
                    block["text"] for block in content_dicts if block["type"] == "text"
                )
                return reply

            db.save_message(user_id, "assistant", content_dicts)

            tool_results = await call_tools(user_id, session, response.content)
            messages.append({"role": "user", "content": tool_results})
            db.save_message(user_id, "user", tool_results)


async def call_tools(user_id, session, content_blocks):
    """Execute every tool_use block and return their results as tool_result blocks."""
    tool_results = []
    for block in content_blocks:
        if block.type == "tool_use":
            try:
                if block.name in LOCAL_TOOLS:
                    result = await LOCAL_TOOLS[block.name](user_id, **block.input)
                else:
                    result = await session.call_tool(block.name, block.input)
                content = str(result)
                if len(content) > MAX_TOOL_RESULT_CHARS:
                    content = content[:MAX_TOOL_RESULT_CHARS] + "... [truncated]"
            except Exception as e:
                logger.exception("Tool call failed: %s(%s)", block.name, block.input)
                content = f"Tool error: {e}"

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                }
            )

    return tool_results
