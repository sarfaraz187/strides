import asyncio
import base64
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "TOKEN_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )


def _mock_session(tool_names: list[str]):
    session = AsyncMock()

    async def call_tool(name, args):
        result = AsyncMock()
        result.structuredContent = {"result": "mcp-tool-result"}
        return result

    session.call_tool.side_effect = call_tool

    def _tool_mock(name: str) -> MagicMock:
        tool = MagicMock(description="", inputSchema={})
        tool.name = name
        return tool

    tools_response = MagicMock()
    tools_response.tools = [_tool_mock(name) for name in tool_names]
    session.list_tools = AsyncMock(return_value=tools_response)

    @asynccontextmanager
    async def open_mcp_session(user_id):
        yield session

    return open_mcp_session, session


def test_call_tools_routes_local_goal_tool_without_hitting_mcp_session():
    from backend.services.chat_service import call_tools

    session, mock_session = _mock_session([])[0], _mock_session([])[1]

    with patch(
        "backend.services.chat_service.create_goal_tool",
        new=AsyncMock(return_value={"id": "goal-1", "description": "Run 30km this week"}),
    ) as mock_create_goal:
        block = MagicMock(type="tool_use", id="call-1")
        block.name = "create_goal"
        block.input = {
            "description": "Run 30km this week",
            "metric": "distance_km",
            "target_value": 30,
            "period": "week",
            "deadline": None,
        }

        results = asyncio.run(call_tools("user-123", mock_session, [block]))

    mock_create_goal.assert_called_once_with("user-123", **block.input)
    mock_session.call_tool.assert_not_called()
    assert results[0]["tool_use_id"] == "call-1"
    assert "Run 30km this week" in results[0]["content"]


def test_call_tools_still_routes_unknown_tool_names_to_mcp_session():
    from backend.services.chat_service import call_tools

    open_mcp_session, mock_session = _mock_session([])

    block = MagicMock(type="tool_use", id="call-2")
    block.name = "get_weekly_stats"
    block.input = {}

    asyncio.run(call_tools("user-123", mock_session, [block]))

    mock_session.call_tool.assert_called_once_with("get_weekly_stats", {})


def test_process_query_merges_local_tool_schemas_with_mcp_tools():
    from backend.services.chat_service import LOCAL_TOOL_SCHEMAS, process_query

    open_mcp_session, mock_session = _mock_session(["get_weekly_stats"])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    fake_response.content = [MagicMock(type="text", text="done")]

    with patch("backend.services.chat_service.open_mcp_session", open_mcp_session), patch(
        "backend.agent.client"
    ) as mock_client:
        mock_client.messages.create.return_value = fake_response

        asyncio.run(process_query("user-123", [{"role": "user", "content": "hi"}]))

        called_tools = mock_client.messages.create.call_args.kwargs["tools"]
        local_names = {t["name"] for t in LOCAL_TOOL_SCHEMAS}
        called_names = {t["name"] for t in called_tools}
        assert local_names.issubset(called_names)
        assert "get_weekly_stats" in called_names
