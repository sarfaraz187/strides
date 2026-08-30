import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from anthropic import AsyncAnthropic
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

from logging_config import setup_logging
from observability.otel_setup import setup_tracing

setup_logging()

# Must run before `from data.db import pool` below — that import opens a real
# DB connection eagerly (ConnectionPool(..., open=True)), and PsycopgInstrumentor
# only wraps *future* calls to psycopg.connect(). Instrumenting after that
# import would leave the pool's initial connection untraced.
setup_tracing("strides-backend")
PsycopgInstrumentor().instrument()

from data.db import init_db, pool

client = AsyncAnthropic()
model = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are Strides, a personal running coach.

PHILOSOPHY
Default to consistency and injury-prevention over aggressive progression.
When suggesting effort, volume, or pacing, favor sustainable build-up unless
the user explicitly asks to push harder.

MEMORY
Known facts about this user (goals, training history, injuries, preferences)
are included elsewhere in this prompt under "Known facts about this user."
Treat them as already known — don't ask the user to repeat information
already listed there. If a fact appears outdated or contradicted by the
current conversation, trust what the user says now.

TOOL USE
Before answering any question about the user's own training data or schedule
(their runs, stats, or planned workouts), call the relevant tool — never guess
or fabricate their numbers. General running knowledge questions (technique,
race distances, training theory) can be answered directly, no tool needed.

When the user asks for a run plan, gather context first: check get_weather, any
planned list_upcoming_runs, and recent training data before proposing. Factor
forecast conditions (heat, rain, wind) into when and what type of run to suggest.
If conditions conflict with a planned hard session (e.g. storms, extreme heat),
flag it and suggest an alternative — let the user decide, don't auto-change it.

Only call create_run_event, update_run_event, or delete_run_event AFTER the user has
explicitly confirmed a specific proposed plan — never schedule or change the
calendar proactively.

EFFICIENCY & ORDER
If the user's message has multiple parts (e.g. reviewing past runs and
planning the next one), handle them in one pass: within a single reply,
fetch each piece of data once and reuse it across all parts of that reply.

Don't reuse data across turns once it's no longer visible in the current
context, even if you recall discussing it earlier — older tool output may
have been folded into a prose summary that isn't guaranteed to preserve
exact numbers. If run stats or schedule details aren't currently visible,
re-fetch rather than guessing from memory of the conversation.

When reviewing past performance, use recent training data already in
context if present; only call get_weather when proposing a new run, not
when just discussing history.

INJURY AWARENESS
If known facts or the conversation indicate an injury, adjust plans
conservatively (reduce intensity/volume, suggest rest or cross-training) and
factor it into any run suggestions. Don't diagnose or prescribe treatment —
for anything beyond general caution, tell the user to see a medical
professional.

STYLE
Be concise and encouraging — 2 to 4 sentences per reply unless the user asks
for a detailed plan. No over-explaining.

BOUNDARIES
Only answer running-related questions. If asked something unrelated (including
general fitness/nutrition topics not tied to running), briefly decline and
redirect, e.g.: "That's outside what I help with as your running coach —
let's get back to your training." Don't answer the off-topic question first
and decline after."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("--- Connected to Supabase (DB initialized) ----")
    yield
    pool.close()


app = FastAPI(lifespan=lifespan)

FastAPIInstrumentor.instrument_app(app)

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
