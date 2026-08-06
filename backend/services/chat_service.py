from backend.services.goals_service import create_goal_tool, get_goals_with_progress
from backend.services.mcp_client import get_tool_schemas, open_mcp_session

LOCAL_TOOLS = {
    "get_goals": lambda user_id, **_: get_goals_with_progress(user_id),
    "create_goal": lambda user_id, **kwargs: create_goal_tool(user_id, **kwargs),
}

LOCAL_TOOL_SCHEMAS = [
    {
        "name": "get_goals",
        "description": (
            "List the user's running goals along with real-time progress percentage "
            "computed from their actual run data. Use this whenever the user asks "
            "about their goals or progress toward them."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_goal",
        "description": (
            "Create a new running goal when the user states one in conversation "
            "(e.g. 'I want to run 30km this week' or "
            "'I want a sub-25min 5K by September')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Human-readable goal, e.g. 'Run 30km this week'",
                },
                "metric": {
                    "type": "string",
                    "enum": ["distance_km", "pace_min_per_km", "run_count"],
                    "description": (
                        "distance_km/run_count for volume goals; pace_min_per_km for "
                        "speed goals (lower is better, e.g. a 25-minute 5K is pace 5.0)"
                    ),
                },
                "target_value": {
                    "type": "number",
                    "description": "Target value for the metric, e.g. 30 for 30km",
                },
                "period": {
                    "type": "string",
                    "enum": ["week", "deadline"],
                    "description": (
                        "'week' for a recurring goal measured Monday-through-today; "
                        "'deadline' for a goal measured from now until a specific date"
                    ),
                },
                "deadline": {
                    "type": "string",
                    "description": "YYYY-MM-DD, required when period is 'deadline'",
                },
            },
            "required": ["description", "metric", "target_value", "period"],
        },
    },
]


async def process_query(user_id: str, messages: list[dict]) -> str:
    """Call Claude, executing any requested tools, until it gives a final answer."""
    from backend.agent import SYSTEM_PROMPT, client, model

    async with open_mcp_session(user_id) as session:
        tools = await get_tool_schemas(session) + LOCAL_TOOL_SCHEMAS

        while True:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                reply = "\n".join(
                    block.text for block in response.content if block.type == "text"
                )
                return reply

            messages.append(
                {
                    "role": "user",
                    "content": await call_tools(user_id, session, response.content),
                }
            )


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
            except Exception as e:
                content = f"Tool error: {e}"

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                }
            )

    return tool_results
