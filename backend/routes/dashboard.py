import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from backend.dependencies import require_user
from backend.services import weather_service
from backend.services.mcp_client import (
    CALENDAR_SERVER_URL,
    HEALTH_SERVER_URL,
    open_mcp_session,
)
from data.db import Preferences, get_oauth_token, get_preferences

router = APIRouter()


def _compute_weekly_stats(recent_runs: list[dict]) -> dict:
    """Derive this week's (Monday-through-today) stats from a 7-day run list.

    A 7-day lookback always covers Monday-of-this-week (weekday offset is at
    most 6), so this avoids a second Google Health API round trip that
    get_weekly_stats would otherwise make for largely the same data."""
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%dT00:00:00")
    week_runs = [run for run in recent_runs if run["date"] >= monday]

    total_distance_km = sum(run["distance_km"] or 0 for run in week_runs)
    total_duration_min = sum(run["duration_min"] or 0 for run in week_runs)

    return {
        "run_count": len(week_runs),
        "total_distance_km": round(total_distance_km, 2),
        "total_duration_min": round(total_duration_min, 1),
        "avg_pace_min_per_km": round(total_duration_min / total_distance_km, 2)
        if total_distance_km
        else None,
    }


async def _fetch_health(user_id: str, health_connected: bool) -> dict:
    weekly_stats, recent_runs, health_error = None, [], None

    if health_connected:
        try:
            async with open_mcp_session(
                user_id, server_url=HEALTH_SERVER_URL
            ) as session:
                recent_result = await session.call_tool(
                    "get_recent_runs", {"days": 7}
                )

            recent_content = recent_result.structuredContent

            if isinstance(recent_content, dict) and "error" in recent_content:
                health_error = recent_content
            else:
                recent_runs = recent_content["result"]
                weekly_stats = _compute_weekly_stats(recent_runs)
        except Exception:
            health_connected = False

    return {
        "weekly_stats": weekly_stats,
        "recent_runs": recent_runs,
        "health_connected": health_connected,
        "health_error": health_error,
    }


async def _fetch_calendar(
    user_id: str, calendar_connected: bool, prefs: Preferences
) -> dict:
    upcoming_runs = []

    if calendar_connected:
        try:
            async with open_mcp_session(
                user_id, server_url=CALENDAR_SERVER_URL
            ) as session:
                result = await session.call_tool(
                    "list_upcoming_runs", {"days_ahead": 7}
                )
            events = (result.structuredContent or {}).get("result", [])

            async def forecast_for(event: dict):
                if prefs.location_lat is None or prefs.location_lon is None:
                    return None
                start = event.get("start", {}).get("dateTime", "")
                date = start[:10] if start else None
                if not date:
                    return None
                return await weather_service.get_forecast(
                    prefs.location_lat, prefs.location_lon, date
                )

            forecasts = await asyncio.gather(*(forecast_for(event) for event in events))
            upcoming_runs = [
                {**event, "forecast": forecast}
                for event, forecast in zip(events, forecasts)
            ]
        except Exception:
            calendar_connected = False

    return {"calendar_connected": calendar_connected, "upcoming_runs": upcoming_runs}


async def _fetch_current_weather(prefs: Preferences) -> dict:
    if prefs.location_lat is None or prefs.location_lon is None:
        return {"current_weather": None}

    try:
        conditions, air_quality = await asyncio.gather(
            weather_service.get_current_conditions(
                prefs.location_lat, prefs.location_lon
            ),
            weather_service.get_air_quality(prefs.location_lat, prefs.location_lon),
        )
        return {"current_weather": {**conditions, **air_quality}}
    except Exception:
        return {"current_weather": None}


@router.get("/dashboard")
async def dashboard(user_id: str = Depends(require_user)):
    health_connected = get_oauth_token(user_id, "health") is not None
    calendar_connected = get_oauth_token(user_id, "calendar") is not None
    prefs = get_preferences(user_id)

    health_result, calendar_result, weather_result = await asyncio.gather(
        _fetch_health(user_id, health_connected),
        _fetch_calendar(user_id, calendar_connected, prefs),
        _fetch_current_weather(prefs),
    )

    return {**health_result, **calendar_result, **weather_result}
