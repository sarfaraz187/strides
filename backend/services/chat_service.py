from backend.agent import SYSTEM_PROMPT, client, model
from backend.services.mcp_client import get_tool_schemas, open_mcp_session


async def process_query(user_id: str, messages: list[dict]) -> str:
    """Call Claude, executing any requested tools, until it gives a final answer."""
    async with open_mcp_session(user_id) as session:
        tools = await get_tool_schemas(session)

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
                    "content": await call_tools(session, response.content),
                }
            )


async def call_tools(session, content_blocks):
    """Execute every tool_use block and return their results as tool_result blocks."""
    tool_results = []
    for block in content_blocks:
        if block.type == "tool_use":
            try:
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
