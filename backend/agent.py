from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession
from contextlib import asynccontextmanager
from fastapi import FastAPI
from mcp.client.streamable_http import streamable_http_client

load_dotenv()
client = Anthropic()
model = "claude-haiku-4-5-20251001"

SERVER_URL = "http://127.0.0.1:8000/mcp"

SYSTEM_PROMPT = """You are Strides, a personal running coach. Always call a tool
before answering any question about the user's training — never guess.

You have these tools:
- get_weekly_stats — aggregated stats (distance, duration, pace, run count) for
  the current week (Monday through today). Use for "how was my week" type questions.
- get_run_stats(start_date, end_date) — aggregated stats for a custom date range
  (YYYY-MM-DD, end_date exclusive). Use for specific date ranges.
- get_recent_runs(days) — individual runs from the last N days, already converted
  to km/minutes/pace. Use when the user wants per-run detail, not just totals.
- get_runs — raw, unconverted data. Avoid unless the other tools don't cover
  what's needed.

Be concise and encouraging. Only answer running-related questions."""

app_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to the fit_server MCP server for the lifetime of the app."""
    async with streamable_http_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            app_state["session"] = session
            app_state["tools"] = await get_tool_schemas(session)
            app_state["messages"] = []

            yield


app = FastAPI(lifespan=lifespan)


from backend.services.chat_service import get_tool_schemas  # noqa: E402
from backend.routes.chat import router  # noqa: E402
from backend.routes.auth import router as auth_router  # noqa: E402

app.include_router(router)
app.include_router(auth_router)
