from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.dependencies import require_user
from data.db import get_preferences, upsert_preferences

router = APIRouter(prefix="/preferences")


class PreferencesUpdate(BaseModel):
    weekly_goal_km: float | None = None
    units: str | None = None
    notifications_enabled: bool | None = None
    language: str | None = None
    location_lat: float | None = None
    location_lon: float | None = None


@router.get("")
def read_preferences(user_id: str = Depends(require_user)):
    return get_preferences(user_id)


@router.put("")
def write_preferences(body: PreferencesUpdate, user_id: str = Depends(require_user)):
    return upsert_preferences(
        user_id,
        weekly_goal_km=body.weekly_goal_km,
        units=body.units,
        notifications_enabled=body.notifications_enabled,
        language=body.language,
        location_lat=body.location_lat,
        location_lon=body.location_lon,
    )
