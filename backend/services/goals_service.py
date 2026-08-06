from datetime import date, datetime, timedelta, timezone

from backend.services.mcp_client import open_mcp_session
from data.db import Goal, create_goal, list_goals

METRICS = {"distance_km", "pace_min_per_km", "run_count"}
PERIODS = {"week", "deadline"}


def _period_range(goal: Goal) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    if goal.period == "week":
        start = today - timedelta(days=today.weekday())
        end = today + timedelta(days=1)
    else:
        start = goal.created_at.date()
        end = (goal.deadline or today) + timedelta(days=1)
    return start, end


def _progress_pct(goal: Goal, stats: dict) -> int:
    if not goal.target_value:
        return 0

    if goal.metric == "pace_min_per_km":
        actual = stats.get("avg_pace_min_per_km")
        if not actual:
            return 0
        return min(100, round(goal.target_value / actual * 100))

    key = "total_distance_km" if goal.metric == "distance_km" else "run_count"
    actual = stats.get(key) or 0
    return min(100, round(actual / goal.target_value * 100))


def _serialize(goal: Goal, progress_pct: int) -> dict:
    return {
        "id": goal.id,
        "description": goal.description,
        "target_value": goal.target_value,
        "metric": goal.metric,
        "period": goal.period,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "progress_pct": progress_pct,
    }


async def get_goals_with_progress(user_id: str) -> list[dict]:
    """List the user's goals with progress computed against their actual run data."""
    goals = list_goals(user_id)
    if not goals:
        return []

    async with open_mcp_session(user_id) as session:
        results = []
        for goal in goals:
            progress_pct = 0
            if goal.metric and goal.period:
                start, end = _period_range(goal)
                stats_result = await session.call_tool(
                    "get_run_stats",
                    {"start_date": start.isoformat(), "end_date": end.isoformat()},
                )
                progress_pct = _progress_pct(goal, stats_result.structuredContent)
            results.append(_serialize(goal, progress_pct))
    return results


async def create_goal_tool(
    user_id: str,
    description: str,
    metric: str,
    target_value: float,
    period: str,
    deadline: str | None = None,
) -> dict:
    """Create a new goal for the user, e.g. from something they said in chat."""
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {METRICS}")
    if period not in PERIODS:
        raise ValueError(f"period must be one of {PERIODS}")

    parsed_deadline = date.fromisoformat(deadline) if deadline else None
    goal_id = create_goal(user_id, description, target_value, metric, period, parsed_deadline)

    return {
        "id": goal_id,
        "description": description,
        "target_value": target_value,
        "metric": metric,
        "period": period,
        "deadline": deadline,
    }
