import asyncio
from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters

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
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_response = await session.list_tools()

            print("------------------------------")
            print(tools_response)
            # print(tools_response.tools[0])
            print("------------------------------")

            tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema,
                }
                for t in tools_response.tools
            ]

            await strides_agent(session, tools)


async def strides_agent(session, tools):
    messages = []
    while True:
        user_input = input("> ")

        if user_input == "quit":
            return

        messages.append({"role": "user", "content": user_input})

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
                break

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await session.call_tool(block.name, block.input)
                    print(f"Tool result: {result}")
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        }
                    )

            messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    asyncio.run(main())
