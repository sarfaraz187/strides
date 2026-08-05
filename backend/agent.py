import os

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
client = Anthropic()
model = "claude-haiku-4-5-20251001"

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

conversations: dict[str, list] = {}  # per-user message history, keyed by user_id

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from backend.routes.auth import router as auth_router
from backend.routes.chat import router
from backend.routes.preferences import router as preferences_router
from backend.routes.profile import router as profile_router
from backend.routes.well_known import router as well_known_router

app.include_router(router)
app.include_router(auth_router)
app.include_router(preferences_router)
app.include_router(profile_router)
app.include_router(well_known_router)
