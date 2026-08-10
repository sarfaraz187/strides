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
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    with (
        patch("backend.services.chat_service.open_mcp_session", open_mcp_session),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.create.return_value = fake_response

        asyncio.run(process_query("user-123", [{"role": "user", "content": "hi"}]))

        called_tools = mock_client.messages.create.call_args.kwargs["tools"]
        local_names = {t["name"] for t in LOCAL_TOOL_SCHEMAS}
        called_names = {t["name"] for t in called_tools}
        assert local_names.issubset(called_names)
        assert "get_weekly_stats" in called_names


def test_save_memory_tool_is_registered_locally():
    from backend.services.chat_service import LOCAL_TOOL_SCHEMAS, LOCAL_TOOLS

    schema_names = {t["name"] for t in LOCAL_TOOL_SCHEMAS}
    assert "save_memory" in schema_names
    assert "save_memory" in LOCAL_TOOLS


def test_save_memory_tool_writes_to_db():
    from backend.services.chat_service import LOCAL_TOOLS

    with patch("backend.services.chat_service.db.save_memory") as mock_save_memory:
        asyncio.run(
            LOCAL_TOOLS["save_memory"](
                "user-123", fact="Training for a half marathon", category="goal"
            )
        )

    mock_save_memory.assert_called_once_with(
        "user-123", "Training for a half marathon", "goal"
    )


def test_process_query_injects_memories_into_system_prompt():
    from backend.services.chat_service import process_query

    open_mcp_session, mock_session = _mock_session([])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    fake_memories = [{"fact": "Left knee sore, avoid speed work", "category": "injury"}]

    with (
        patch("backend.services.chat_service.open_mcp_session", open_mcp_session),
        patch(
            "backend.services.chat_service.db.get_memories", return_value=fake_memories
        ),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.create.return_value = fake_response

        asyncio.run(process_query("user-123", [{"role": "user", "content": "hi"}]))

        system_prompt = mock_client.messages.create.call_args.kwargs["system"]
        assert "Left knee sore, avoid speed work" in system_prompt


def test_call_tools_truncates_large_tool_results():
    from backend.services.chat_service import MAX_TOOL_RESULT_CHARS, call_tools

    open_mcp_session, mock_session = _mock_session([])
    mock_session.call_tool.side_effect = lambda name, args: "x" * 10_000

    block = MagicMock(type="tool_use", id="call-1")
    block.name = "get_recent_runs"
    block.input = {"days": 90}

    results = asyncio.run(call_tools("user-123", mock_session, [block]))

    assert results[0]["content"] == ("x" * MAX_TOOL_RESULT_CHARS) + "... [truncated]"


def test_call_tools_leaves_small_tool_results_untouched():
    from backend.services.chat_service import call_tools

    open_mcp_session, mock_session = _mock_session([])
    mock_session.call_tool.side_effect = lambda name, args: "short result"

    block = MagicMock(type="tool_use", id="call-1")
    block.name = "get_weekly_stats"
    block.input = {}

    results = asyncio.run(call_tools("user-123", mock_session, [block]))

    assert results[0]["content"] == "short result"


def test_process_query_persists_intermediate_tool_turns():
    from backend.services.chat_service import process_query

    open_mcp_session, mock_session = _mock_session(["get_weekly_stats"])
    mock_session.call_tool.side_effect = lambda name, args: "42km this week"

    tool_use_block = MagicMock(type="tool_use", id="call-1")
    tool_use_block.name = "get_weekly_stats"
    tool_use_block.input = {}
    tool_use_block.model_dump.return_value = {
        "type": "tool_use",
        "id": "call-1",
        "name": "get_weekly_stats",
        "input": {},
    }
    tool_call_response = MagicMock(stop_reason="tool_use", content=[tool_use_block])

    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    final_response = MagicMock(stop_reason="end_turn", content=[text_block])

    with (
        patch("backend.services.chat_service.open_mcp_session", open_mcp_session),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.services.chat_service.db.save_message") as mock_save_message,
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.create.side_effect = [tool_call_response, final_response]

        reply = asyncio.run(
            process_query("user-123", [{"role": "user", "content": "hi"}])
        )

    assert reply == "done"
    assert mock_save_message.call_count == 2
    mock_save_message.assert_any_call(
        "user-123",
        "assistant",
        [{"type": "tool_use", "id": "call-1", "name": "get_weekly_stats", "input": {}}],
    )
    mock_save_message.assert_any_call(
        "user-123",
        "user",
        [{"type": "tool_result", "tool_use_id": "call-1", "content": "42km this week"}],
    )


def test_process_query_injects_conversation_summary_into_system_prompt():
    from backend.services.chat_service import process_query

    open_mcp_session, mock_session = _mock_session([])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    fake_summary = {
        "summary_text": "User is training for a fall marathon.",
        "through_message_id": 5,
    }

    with (
        patch("backend.services.chat_service.open_mcp_session", open_mcp_session),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=fake_summary,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.create.return_value = fake_response

        asyncio.run(process_query("user-123", [{"role": "user", "content": "hi"}]))

        system_prompt = mock_client.messages.create.call_args.kwargs["system"]
        assert "User is training for a fall marathon." in system_prompt


def test_process_query_omits_summary_section_when_none_exists():
    from backend.services.chat_service import process_query

    open_mcp_session, mock_session = _mock_session([])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    with (
        patch("backend.services.chat_service.open_mcp_session", open_mcp_session),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.create.return_value = fake_response

        asyncio.run(process_query("user-123", [{"role": "user", "content": "hi"}]))

        system_prompt = mock_client.messages.create.call_args.kwargs["system"]
        assert "Summary of earlier conversation" not in system_prompt
