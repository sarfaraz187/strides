import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from anthropic import AsyncAnthropic

from data.db import init_db, pool
from logging_config import setup_logging

setup_logging()

client = AsyncAnthropic()
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
- list_upcoming_runs(days_ahead) — planned runs from the user's dedicated 'Strides'
  calendar for the next N days. Use when the user asks what's scheduled or
  wants to plan.
- create_run_event(title, start_time, duration_minutes, notes) — add a planned run
  to the user's dedicated 'Strides' calendar.
- update_run_event(event_id, ...) / delete_run_event(event_id) — reschedule or
  cancel a planned run.
- get_weather — current conditions (temperature, condition, humidity, wind) at the
  user's stored location. Use when reasoning about whether or how to plan a run.
- save_memory — call this when the user shares a durable training goal, an
  injury or physical constraint, or a standing preference. Do not call it for
  one-off statements about a single run or feelings about today's session.

When the user asks for a run plan, gather context first: check get_weather, any
planned list_upcoming_runs, and recent training data before proposing. Factor
forecast conditions (heat, rain, wind) into when and what type of run to suggest.
Only call create_run_event, update_run_event, or delete_run_event AFTER the user has
explicitly confirmed a specific proposed plan — never schedule or change the
calendar proactively.

Be concise and encouraging. Only answer running-related questions."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("--- Connected to Supabase (DB initialized) ----")
    yield
    pool.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.routes.auth import router as auth_router
from backend.routes.calendar import router as calendar_router
from backend.routes.chat import router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.preferences import router as preferences_router
from backend.routes.profile import router as profile_router
from backend.routes.well_known import router as well_known_router

app.include_router(router)
app.include_router(auth_router)
app.include_router(calendar_router)
app.include_router(dashboard_router)
app.include_router(preferences_router)
app.include_router(profile_router)
app.include_router(well_known_router)
