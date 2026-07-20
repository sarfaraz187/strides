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


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(tools)  # step 1: just confirm discovery works


if __name__ == "__main__":
    asyncio.run(main())
