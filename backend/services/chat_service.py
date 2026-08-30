import logging
from datetime import datetime, timezone

from langfuse import get_client, propagate_attributes
from opentelemetry import trace

import data.db as db
from backend.services import weather_service
from backend.services.mcp_client import (
    CALENDAR_SERVER_URL,
    HEALTH_SERVER_URL,
    get_tool_schemas,
    open_mcp_session_with_client,
    refresh_traceparent,
)

logger = logging.getLogger(__name__)
langfuse_client = get_client()
tracer = trace.get_tracer("strides-backend")

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
    },
    {
        "name": "get_weather",
        "description": (
            "Get the current weather conditions (temperature, condition, "
            "humidity, wind) at the user's stored location. Use this when "
            "reasoning about whether/how to plan an upcoming run."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


async def _save_memory(user_id: str, fact: str, category: str) -> str:
    db.save_memory(user_id, fact, category)
    return "Saved."


async def _get_weather(user_id: str) -> str:
    prefs = db.get_preferences(user_id)
    if prefs.location_lat is None or prefs.location_lon is None:
        return "No location set for this user — ask them to set one in their profile."
    conditions = await weather_service.get_current_conditions(
        prefs.location_lat, prefs.location_lon
    )
    return (
        f"{conditions['temp']}°C, {conditions['condition']}, "
        f"feels like {conditions['feels_like']}°C, humidity {conditions['humidity']}%, "
        f"wind {conditions['wind']} km/h"
    )


LOCAL_TOOLS: dict = {"save_memory": _save_memory, "get_weather": _get_weather}


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


def _build_system_prompt(base_prompt: str, user_id: str) -> list[dict]:
    """Build the system prompt as cache-friendly blocks: the static base_prompt
    (identical for every user/request, so it's marked cacheable) followed by a
    dynamic suffix (date/memories/summary, which changes per request and is
    left uncached)."""
    today = datetime.now(timezone.utc).strftime("%A, %Y-%m-%d")
    suffix = f"Today's date is {today} (UTC)."

    memories = db.get_memories(user_id)
    if memories:
        facts = "\n".join(f"- {m['fact']}" for m in memories)
        suffix = f"{suffix}\n\nKnown facts about this user:\n{facts}"

    summary = db.get_conversation_summary(user_id)
    if summary:
        suffix = (
            f"{suffix}\n\nSummary of earlier conversation:\n{summary['summary_text']}"
        )

    return [
        {
            "type": "text",
            "text": base_prompt,
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": suffix},
    ]


async def process_query(user_id: str, messages: list[dict], usage: dict | None = None):
    """Call Claude, executing any requested tools, until it gives a final answer.

    Yields text chunks as they stream in. The final assistant text is the
    concatenation of every chunk yielded across the whole call.

    When `usage` is provided, it is mutated in place, accumulating
    `input_tokens` and `output_tokens` across every API call made during the
    tool-use loop.
    """
    from backend.agent import SYSTEM_PROMPT, client, model

    with tracer.start_as_current_span("chat.process_query") as otel_span:
        otel_span.set_attribute("user_id", user_id)

        with propagate_attributes(user_id=user_id):
            logger.info(
                "------------- Starting new query for user %s -------------", user_id
            )
            system_prompt = _build_system_prompt(SYSTEM_PROMPT, user_id)

            async with (
                open_mcp_session_with_client(
                    user_id, server_url=HEALTH_SERVER_URL
                ) as (health_session, health_http_client),
                open_mcp_session_with_client(
                    user_id, server_url=CALENDAR_SERVER_URL
                ) as (calendar_session, calendar_http_client),
            ):
                health_tools = await get_tool_schemas(health_session)
                calendar_tools = await get_tool_schemas(calendar_session)
                tools = health_tools + calendar_tools + LOCAL_TOOL_SCHEMAS
                tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
                sessions_by_tool = {
                    t["name"]: calendar_session for t in calendar_tools
                }
                http_clients_by_tool = {
                    t["name"]: calendar_http_client for t in calendar_tools
                }

                with (
                    langfuse_client.start_as_current_observation(
                        as_type="span",
                        name="process_query",
                        input=messages[-1][
                            "content"
                        ],  # The entire build messages including system prompt is being sent. For tracing pursponse we are just tracing with last user message
                    ) as process_span
                ):  # <--- One Trace from langfuse
                    while True:
                        with langfuse_client.start_as_current_observation(
                            as_type="generation",
                            name="claude-messages-create",
                            model=model,
                            input=messages,
                        ) as generation:  # <---- One observation from langfuse
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
                                output=[
                                    block.model_dump() for block in response.content
                                ],
                                usage_details={
                                    "input": response.usage.input_tokens,
                                    "output": response.usage.output_tokens,
                                    "cache_creation_input_tokens": (
                                        response.usage.cache_creation_input_tokens
                                    ),
                                    "cache_read_input_tokens": (
                                        response.usage.cache_read_input_tokens
                                    ),
                                },
                            )

                        if usage is not None:
                            usage["input_tokens"] = (
                                usage.get("input_tokens", 0)
                                + response.usage.input_tokens
                            )
                            usage["output_tokens"] = (
                                usage.get("output_tokens", 0)
                                + response.usage.output_tokens
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

                        tool_results = await call_tools(
                            user_id,
                            health_session,
                            response.content,
                            sessions_by_tool=sessions_by_tool,
                            http_client=health_http_client,
                            http_clients_by_tool=http_clients_by_tool,
                        )
                        messages.append({"role": "user", "content": tool_results})

                        db.save_message(user_id, "assistant", content_dicts)
                        db.save_message(user_id, "user", tool_results)


async def call_tools(
    user_id,
    session,
    content_blocks,
    sessions_by_tool: dict | None = None,
    http_client=None,
    http_clients_by_tool: dict | None = None,
):
    """Execute every tool_use block and return their results as tool_result blocks."""
    sessions_by_tool = sessions_by_tool or {}
    http_clients_by_tool = http_clients_by_tool or {}
    tool_results = []
    for block in content_blocks:
        if block.type == "tool_use":
            with tracer.start_as_current_span(f"chat.tool_call.{block.name}") as span:
                span.set_attribute("tool_name", block.name)

                with langfuse_client.start_as_current_observation(
                    as_type="tool", name=block.name, input=block.input
                ) as tool_obs:  # <--- Observation for tool call
                    try:
                        if block.name in LOCAL_TOOLS:
                            result = await LOCAL_TOOLS[block.name](
                                user_id, **block.input
                            )
                        else:
                            target_session = sessions_by_tool.get(block.name, session)
                            target_http_client = http_clients_by_tool.get(
                                block.name, http_client
                            )
                            if target_http_client is not None:
                                refresh_traceparent(target_http_client)
                            result = await target_session.call_tool(
                                block.name, block.input
                            )
                        content = str(result)
                        if len(content) > MAX_TOOL_RESULT_CHARS:
                            content = (
                                content[:MAX_TOOL_RESULT_CHARS] + "... [truncated]"
                            )
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
