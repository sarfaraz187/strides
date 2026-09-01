from unittest.mock import MagicMock

from mcp_servers.calendar_server.server import update_run_event


def test_update_run_event_forwards_fields_unwrapped(monkeypatch):
    """A tool call arrives as {"event_id": ..., "fields": {"start": ..., "end": ...}}.
    update_event() must receive start/end directly as PATCH body fields, not
    nested under a "fields" key (Google's API silently ignores unknown
    top-level keys and would report a fake success)."""
    import mcp_servers.calendar_server.server as server_module

    monkeypatch.setattr(server_module, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(
        server_module, "get_valid_access_token", lambda *a, **k: "fake-token"
    )
    monkeypatch.setattr(server_module, "ensure_calendar", lambda *a, **k: "cal-1")

    captured = {}

    def fake_update_event(access_token, calendar_id, event_id, **fields):
        captured.update(fields)
        return {"id": event_id, **fields}

    monkeypatch.setattr(server_module, "update_event", fake_update_event)

    fake_ctx = MagicMock()
    fake_ctx.request_context.request = None

    new_start = {"dateTime": "2026-09-02T19:30:00+02:00", "timeZone": "Europe/Berlin"}
    new_end = {"dateTime": "2026-09-02T20:03:00+02:00", "timeZone": "Europe/Berlin"}

    update_run_event(
        event_id="evt-1",
        fields={"start": new_start, "end": new_end},
        ctx=fake_ctx,
    )

    assert captured == {"start": new_start, "end": new_end}
