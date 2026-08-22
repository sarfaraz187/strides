import asyncio
from unittest.mock import AsyncMock, patch

from backend.services import weather_service


def test_get_current_conditions_returns_next_six_hourly_entries():
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "current": {
            "time": "2026-08-22T13:45",
            "temperature_2m": 27.0,
            "apparent_temperature": 30.0,
            "relative_humidity_2m": 74,
            "wind_speed_10m": 9.0,
            "weathercode": 1,
        },
        "hourly": {
            "time": [
                "2026-08-22T12:00",
                "2026-08-22T13:00",
                "2026-08-22T14:00",
                "2026-08-22T15:00",
                "2026-08-22T16:00",
                "2026-08-22T17:00",
                "2026-08-22T18:00",
                "2026-08-22T19:00",
                "2026-08-22T20:00",
            ],
            "temperature_2m": [29.0, 28.0, 27.0, 27.0, 26.0, 25.0, 24.0, 23.0, 22.0],
        },
    }

    with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_response)):
        result = asyncio.run(weather_service.get_current_conditions(17.38, 78.48))

    assert result["hourly"] == [
        {"time": "2026-08-22T14:00", "temp": 27.0},
        {"time": "2026-08-22T15:00", "temp": 27.0},
        {"time": "2026-08-22T16:00", "temp": 26.0},
        {"time": "2026-08-22T17:00", "temp": 25.0},
        {"time": "2026-08-22T18:00", "temp": 24.0},
        {"time": "2026-08-22T19:00", "temp": 23.0},
    ]
