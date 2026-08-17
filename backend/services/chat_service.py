import logging

from langfuse import get_client, propagate_attributes

import data.db as db
from backend.services.mcp_client import get_tool_schemas, open_mcp_session

logger = logging.getLogger(__name__)
langfuse_client = get_client()

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


def _to_input_block(block) -> dict:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return block.model_dump()


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


async def process_query(user_id: str, messages: list[dict]):
    """Call Claude, executing any requested tools, until it gives a final answer.

    Yields text chunks as they stream in. The final assistant text is the
    concatenation of every chunk yielded across the whole call.
    """
    from backend.agent import SYSTEM_PROMPT, client, model

    with propagate_attributes(user_id=user_id):
        logger.info(
            "------------- Starting new query for user %s -------------", user_id
        )
        system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)

        async with open_mcp_session(user_id) as session:
            tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

            with langfuse_client.start_as_current_observation(
                as_type="span",
                name="process_query",
                input=messages[-1]["content"],
            ) as process_span:  # <--- One Trace from langfuse
                while True:
                    with langfuse_client.start_as_current_observation(
                        as_type="generation",
                        name="claude-messages-create",
                        model=model,
                        input=messages,
                    ) as generation:  # <---- one observation from langfuse
                        async with client.messages.stream(
                            model=model,
                            max_tokens=1024,
                            system=system_prompt,
                            tools=tools,
                            tool_choice={
                                "type": "auto",
                                "disable_parallel_tool_use": True,
                            },
                            messages=messages,
                        ) as stream:
                            async for text in stream.text_stream:
                                yield text
                            response = await stream.get_final_message()

                        generation.update(
                            output=[block.model_dump() for block in response.content],
                            usage_details={
                                "input": response.usage.input_tokens,
                                "output": response.usage.output_tokens,
                            },
                        )

                    content_dicts = [
                        _to_input_block(block) for block in response.content
                    ]
                    messages.append({"role": "assistant", "content": content_dicts})

                    if response.stop_reason != "tool_use":
                        process_span.update(
                            output="".join(
                                block.text
                                for block in response.content
                                if block.type == "text"
                            )
                        )
                        return

                    db.save_message(user_id, "assistant", content_dicts)

                    tool_results = await call_tools(user_id, session, response.content)
                    messages.append({"role": "user", "content": tool_results})
                    db.save_message(user_id, "user", tool_results)


async def call_tools(user_id, session, content_blocks):
    """Execute every tool_use block and return their results as tool_result blocks."""
    tool_results = []
    for block in content_blocks:
        if block.type == "tool_use":
            with langfuse_client.start_as_current_observation(
                as_type="tool", name=block.name, input=block.input
            ) as tool_obs:
                try:
                    if block.name in LOCAL_TOOLS:
                        result = await LOCAL_TOOLS[block.name](user_id, **block.input)
                    else:
                        result = await session.call_tool(block.name, block.input)
                    content = str(result)
                    if len(content) > MAX_TOOL_RESULT_CHARS:
                        content = content[:MAX_TOOL_RESULT_CHARS] + "... [truncated]"
                except Exception as e:
                    logger.exception(
                        "Tool call failed: %s(%s)", block.name, block.input
                    )
                    content = f"Tool error: {e}"
                    tool_obs.update(level="ERROR", status_message=str(e))

                tool_obs.update(output=content)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                }
            )

    return tool_results
