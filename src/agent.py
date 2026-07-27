import asyncio

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
client = Anthropic()
model = "claude-haiku-4-5-20251001"

server_params = StdioServerParameters(
    command="uv", args=["run", "-m", "src.fit_server"]
)

SYSTEM_PROMPT = """You are Strides, a personal running coach. 

You have one tool: get_runs — always call it before answering any question about the user's training.

Data notes:
- Distance in meters → divide by 1000 for km
- Duration in milliseconds → divide by 60000 for minutes
- Pace = duration / distance in min/km

Be concise and encouraging. Only answer running-related questions."""


async def main():
    """Connect to the fit_server MCP server and start the chat loop."""
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await get_tool_schemas(session)

            print("\nConnected to server with tools:", [t["name"] for t in tools])

            await chat_loop(session, tools)


async def get_tool_schemas(session):
    """Fetch the server's tools and convert them to Anthropic's tool format."""
    tools_response = await session.list_tools()

    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        }
        for t in tools_response.tools
    ]


async def chat_loop(session, tools):
    """Read user input until 'quit', running each query through process_query."""
    messages = []
    while True:
        user_input = input("> ")

        if user_input == "quit":
            return

        messages.append({"role": "user", "content": user_input})

        await process_query(session, tools, messages)


async def process_query(session, tools, messages):
    """Call Claude, executing any requested tools, until it gives a final answer."""
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
            for block in response.content:
                if block.type == "text":
                    print(block.text)
            return

        messages.append(
            {"role": "user", "content": await call_tools(session, response.content)}
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


if __name__ == "__main__":
    asyncio.run(main())
