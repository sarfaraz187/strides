import asyncio

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


async def _fetch_health(user_id: str, health_connected: bool) -> dict:
    weekly_stats, recent_runs, health_error = None, [], None

    if health_connected:
        try:
            async with open_mcp_session(
                user_id, server_url=HEALTH_SERVER_URL
            ) as session:
                weekly_result = await session.call_tool("get_weekly_stats", {})
                recent_result = await session.call_tool("get_recent_runs", {"days": 7})

            weekly_content = weekly_result.structuredContent
            recent_content = recent_result.structuredContent

            if isinstance(weekly_content, dict) and "error" in weekly_content:
                health_error = weekly_content
            elif isinstance(recent_content, dict) and "error" in recent_content:
                health_error = recent_content
            else:
                weekly_stats = weekly_content
                recent_runs = recent_content["result"]
        except Exception:
            health_connected = False

    return {
        "weekly_stats": weekly_stats,
        "recent_runs": recent_runs,
        "health_connected": health_connected,
        "health_error": health_error,
    }


async def _fetch_calendar(user_id: str, calendar_connected: bool, prefs: Preferences) -> dict:
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
                {**event, "forecast": forecast} for event, forecast in zip(events, forecasts)
            ]
        except Exception:
            calendar_connected = False

    return {"calendar_connected": calendar_connected, "upcoming_runs": upcoming_runs}


async def _fetch_current_weather(prefs: Preferences) -> dict:
    if prefs.location_lat is None or prefs.location_lon is None:
        return {"current_weather": None}

    try:
        conditions, air_quality = await asyncio.gather(
            weather_service.get_current_conditions(prefs.location_lat, prefs.location_lon),
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
