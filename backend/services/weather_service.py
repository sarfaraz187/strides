import logging

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

_WEATHER_CODES = {
    0: "clear",
    1: "partly cloudy",
    2: "partly cloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    80: "showers",
    95: "storm",
}


def _condition_from_code(code: int) -> str:
    return _WEATHER_CODES.get(code, "unknown")


async def get_forecast(lat: float, lon: float, date: str) -> dict | None:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,weathercode",
                "start_date": date,
                "end_date": date,
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        data = response.json()

    times = data["daily"]["time"]
    if date not in times:
        return None

    index = times.index(date)
    return {
        "temp": data["daily"]["temperature_2m_max"][index],
        "condition": _condition_from_code(data["daily"]["weathercode"][index]),
    }


async def get_current_conditions(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weathercode",
                "hourly": "temperature_2m",
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        data = response.json()

    current = data["current"]
    hourly = data["hourly"]
    start_index = next(
        (i for i, time in enumerate(hourly["time"]) if time >= current["time"]),
        0,
    )
    next_hours = [
        {"time": time, "temp": temp}
        for time, temp in zip(
            hourly["time"][start_index : start_index + 6],
            hourly["temperature_2m"][start_index : start_index + 6],
        )
    ]

    logging.info(f"Current weather data: {current}")
    return {
        "temp": current["temperature_2m"],
        "feels_like": current["apparent_temperature"],
        "humidity": current["relative_humidity_2m"],
        "wind": current["wind_speed_10m"],
        "condition": _condition_from_code(current["weathercode"]),
        "hourly": next_hours,
    }


async def get_air_quality(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            AIR_QUALITY_URL,
            params={"latitude": lat, "longitude": lon, "current": "us_aqi"},
        )
        response.raise_for_status()
        data = response.json()

    return {"aqi": data["current"]["us_aqi"]}
