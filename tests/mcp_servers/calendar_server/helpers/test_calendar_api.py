import responses

from mcp_servers.calendar_server.helpers import calendar_api

CALENDAR_LIST_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
CALENDARS_URL = "https://www.googleapis.com/calendar/v3/calendars"
TIMEZONE_URL = "https://www.googleapis.com/calendar/v3/users/me/settings/timezone"


def test_returns_cached_calendar_id_without_any_http_calls(monkeypatch):
    monkeypatch.setattr(calendar_api, "get_calendar_id", lambda user_id: "cached-cal-1")

    calendar_id = calendar_api.ensure_calendar("fake-token", "user-1")

    assert calendar_id == "cached-cal-1"


@responses.activate
def test_reuses_existing_strides_calendar_when_cache_is_empty(monkeypatch):
    """Cache is empty (e.g. wiped by a reauth cycle), but a 'Strides'
    calendar already exists on the Google account — must reuse it, not
    create a duplicate."""
    monkeypatch.setattr(calendar_api, "get_calendar_id", lambda user_id: None)
    saved = {}
    monkeypatch.setattr(
        calendar_api, "save_calendar_id", lambda user_id, cal_id: saved.update(id=cal_id)
    )

    responses.add(
        responses.GET,
        CALENDAR_LIST_URL,
        json={
            "items": [
                {"id": "personal-cal", "summary": "mohammed sarfaraz"},
                {"id": "existing-strides-cal", "summary": "Strides"},
            ]
        },
        status=200,
    )

    calendar_id = calendar_api.ensure_calendar("fake-token", "user-1")

    assert calendar_id == "existing-strides-cal"
    assert saved == {"id": "existing-strides-cal"}
    # must not have created a new calendar
    assert not any(call.request.method == "POST" for call in responses.calls)


@responses.activate
def test_creates_new_calendar_when_none_exists(monkeypatch):
    monkeypatch.setattr(calendar_api, "get_calendar_id", lambda user_id: None)
    saved = {}
    monkeypatch.setattr(
        calendar_api, "save_calendar_id", lambda user_id, cal_id: saved.update(id=cal_id)
    )

    responses.add(
        responses.GET,
        CALENDAR_LIST_URL,
        json={"items": [{"id": "personal-cal", "summary": "mohammed sarfaraz"}]},
        status=200,
    )
    responses.add(
        responses.GET,
        TIMEZONE_URL,
        json={"value": "Europe/Berlin"},
        status=200,
    )
    responses.add(
        responses.POST,
        CALENDARS_URL,
        json={"id": "brand-new-cal"},
        status=200,
    )

    calendar_id = calendar_api.ensure_calendar("fake-token", "user-1")

    assert calendar_id == "brand-new-cal"
    assert saved == {"id": "brand-new-cal"}
