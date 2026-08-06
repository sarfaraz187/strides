import asyncio
import base64
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from data.db import create_goal, find_or_create_user, get_connection, init_db


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    init_db()
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE email = %s", ("goals-service@example.com",))
        conn.commit()


def _user_id():
    return find_or_create_user("goals-service@example.com", "goals-service-sub", "Goals Service")


def _mock_session(stats: dict):
    session = AsyncMock()

    async def call_tool(name, args):
        result = AsyncMock()
        result.structuredContent = stats
        return result

    session.call_tool.side_effect = call_tool

    @asynccontextmanager
    async def open_mcp_session(user_id):
        yield session

    return open_mcp_session, session


def test_get_goals_with_progress_computes_distance_goal():
    from backend.services.goals_service import get_goals_with_progress

    user_id = _user_id()
    create_goal(
        user_id,
        description="Run 30km this week",
        target_value=30,
        metric="distance_km",
        period="week",
        deadline=None,
    )
    open_mcp_session, session = _mock_session({"total_distance_km": 21.9, "run_count": 4})

    with patch("backend.services.goals_service.open_mcp_session", open_mcp_session):
        goals = asyncio.run(get_goals_with_progress(user_id))

    assert len(goals) == 1
    assert goals[0]["description"] == "Run 30km this week"
    assert goals[0]["progress_pct"] == 73
    session.call_tool.assert_called_once()
    assert session.call_tool.call_args.args[0] == "get_run_stats"


def test_get_goals_with_progress_caps_at_100():
    from backend.services.goals_service import get_goals_with_progress

    user_id = _user_id()
    create_goal(
        user_id,
        description="Run 10km this week",
        target_value=10,
        metric="distance_km",
        period="week",
        deadline=None,
    )
    open_mcp_session, _ = _mock_session({"total_distance_km": 25.0, "run_count": 3})

    with patch("backend.services.goals_service.open_mcp_session", open_mcp_session):
        goals = asyncio.run(get_goals_with_progress(user_id))

    assert goals[0]["progress_pct"] == 100


def test_get_goals_with_progress_pace_goal_lower_is_better():
    from backend.services.goals_service import get_goals_with_progress

    user_id = _user_id()
    create_goal(
        user_id,
        description="Sub-25min 5K by Sept",
        target_value=5.0,
        metric="pace_min_per_km",
        period="deadline",
        deadline=date.today() + timedelta(days=30),
    )
    open_mcp_session, _ = _mock_session({"avg_pace_min_per_km": 6.25})

    with patch("backend.services.goals_service.open_mcp_session", open_mcp_session):
        goals = asyncio.run(get_goals_with_progress(user_id))

    assert goals[0]["progress_pct"] == 80


def test_get_goals_with_progress_returns_empty_for_no_goals():
    from backend.services.goals_service import get_goals_with_progress

    user_id = _user_id()
    goals = asyncio.run(get_goals_with_progress(user_id))
    assert goals == []


def test_create_goal_tool_persists_and_returns_goal():
    from backend.services.goals_service import create_goal_tool

    user_id = _user_id()
    result = asyncio.run(
        create_goal_tool(
            user_id,
            description="Run 30km this week",
            metric="distance_km",
            target_value=30,
            period="week",
            deadline=None,
        )
    )

    assert result["description"] == "Run 30km this week"
    assert result["metric"] == "distance_km"


def test_create_goal_tool_rejects_invalid_metric():
    from backend.services.goals_service import create_goal_tool

    user_id = _user_id()
    with pytest.raises(ValueError):
        asyncio.run(
            create_goal_tool(
                user_id,
                description="Bad goal",
                metric="not_a_real_metric",
                target_value=1,
                period="week",
                deadline=None,
            )
        )
