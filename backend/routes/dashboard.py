import logging

from fastapi import APIRouter, Depends

from backend.dependencies import require_user
from backend.services import weather_service
from backend.services.mcp_client import (
    CALENDAR_SERVER_URL,
    HEALTH_SERVER_URL,
    open_mcp_session,
)
from data.db import get_oauth_token, get_preferences

router = APIRouter()


@router.get("/dashboard")
async def dashboard(user_id: str = Depends(require_user)):
    health_connected = get_oauth_token(user_id, "health") is not None
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

    calendar_connected = get_oauth_token(user_id, "calendar") is not None
    upcoming_runs = []
    current_weather = None
    prefs = get_preferences(user_id)

    logging.info("----------------------------")
    logging.info(f"User preferences: {prefs}")
    logging.info("----------------------------")

    if calendar_connected:
        try:
            async with open_mcp_session(
                user_id, server_url=CALENDAR_SERVER_URL
            ) as session:
                result = await session.call_tool(
                    "list_upcoming_runs", {"days_ahead": 7}
                )
            events = (result.structuredContent or {}).get("result", [])

            for event in events:
                forecast = None
                if prefs.location_lat is not None and prefs.location_lon is not None:
                    start = event.get("start", {}).get("dateTime", "")
                    date = start[:10] if start else None
                    if date:
                        forecast = await weather_service.get_forecast(
                            prefs.location_lat, prefs.location_lon, date
                        )
                upcoming_runs.append({**event, "forecast": forecast})
        except Exception:
            calendar_connected = False

    if prefs.location_lat is not None and prefs.location_lon is not None:
        try:
            logging.info(
                f"Fetching current conditions for lat: {prefs.location_lat}, lon: {prefs.location_lon}"
            )
            conditions = await weather_service.get_current_conditions(
                prefs.location_lat, prefs.location_lon
            )
            air_quality = await weather_service.get_air_quality(
                prefs.location_lat, prefs.location_lon
            )

            logging.info(f"Current conditions: {conditions}")
            logging.info(f"Air quality: {air_quality}")
            current_weather = {**conditions, **air_quality}
        except Exception:
            current_weather = None

    logging.info("----------------------------")
    print(
        {
            "weekly_stats": weekly_stats,
            "recent_runs": recent_runs,
            "health_connected": health_connected,
            "health_error": health_error,
            "calendar_connected": calendar_connected,
            "upcoming_runs": upcoming_runs,
            "current_weather": current_weather,
        }
    )
    return {
        "weekly_stats": weekly_stats,
        "recent_runs": recent_runs,
        "health_connected": health_connected,
        "health_error": health_error,
        "calendar_connected": calendar_connected,
        "upcoming_runs": upcoming_runs,
        "current_weather": current_weather,
    }
