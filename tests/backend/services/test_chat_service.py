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


@pytest.fixture(autouse=True)
def mock_langfuse(monkeypatch):
    fake = MagicMock()
    fake.start_as_current_observation.return_value.__enter__.return_value = MagicMock()
    monkeypatch.setattr("backend.services.chat_service.langfuse_client", fake)


def _mock_stream(final_response, text_chunks: list[str]):
    """Build a fake client.messages.stream(...) async context manager."""

    class FakeStreamCM:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def _gen(self):
            for chunk in text_chunks:
                yield chunk

        def __init__(self):
            self.text_stream = self._gen()

        async def get_final_message(self):
            return final_response

    return FakeStreamCM()


def _mock_session(tool_names: list[str]):
    session = AsyncMock()
    http_client = MagicMock()
    http_client.headers = {}

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
    async def open_mcp_session_with_client(user_id, **kwargs):
        yield session, http_client

    return open_mcp_session_with_client, session


def test_call_tools_still_routes_unknown_tool_names_to_mcp_session():
    from backend.services.chat_service import call_tools

    open_mcp_session_with_client, mock_session = _mock_session([])

    block = MagicMock(type="tool_use", id="call-2")
    block.name = "get_weekly_stats"
    block.input = {}

    asyncio.run(call_tools("user-123", mock_session, [block]))

    mock_session.call_tool.assert_called_once_with("get_weekly_stats", {})


def test_call_tools_routes_to_calendar_session_for_calendar_tool_names():
    from backend.services.chat_service import call_tools

    health_session = AsyncMock()
    calendar_session = AsyncMock()
    calendar_session.call_tool.return_value = AsyncMock(__str__=lambda self: "ok")

    block = MagicMock(type="tool_use", id="tool-1")
    block.name = "create_run_event"
    block.input = {"title": "Easy 5K"}

    sessions_by_tool = {"create_run_event": calendar_session}

    results = asyncio.run(
        call_tools(
            "user-1", health_session, [block], sessions_by_tool=sessions_by_tool
        )
    )

    calendar_session.call_tool.assert_called_once_with(
        "create_run_event", {"title": "Easy 5K"}
    )
    health_session.call_tool.assert_not_called()
    assert results[0]["tool_use_id"] == "tool-1"


def test_call_tools_falls_back_to_default_session_for_unmapped_tools():
    from backend.services.chat_service import call_tools

    health_session = AsyncMock()
    health_session.call_tool.return_value = AsyncMock(__str__=lambda self: "ok")
    calendar_session = AsyncMock()

    block = MagicMock(type="tool_use", id="tool-2")
    block.name = "get_weekly_stats"
    block.input = {}

    asyncio.run(
        call_tools(
            "user-1",
            health_session,
            [block],
            sessions_by_tool={"create_run_event": calendar_session},
        )
    )

    health_session.call_tool.assert_called_once_with("get_weekly_stats", {})
    calendar_session.call_tool.assert_not_called()


def test_get_weather_tool_uses_stored_location():
    from backend.services.chat_service import _get_weather

    with (
        patch("backend.services.chat_service.db.get_preferences") as mock_prefs,
        patch(
            "backend.services.chat_service.weather_service.get_current_conditions"
        ) as mock_weather,
    ):
        mock_prefs.return_value.location_lat = 17.385
        mock_prefs.return_value.location_lon = 78.4867
        mock_weather.return_value = {
            "temp": 27,
            "condition": "clear",
            "feels_like": 30,
            "humidity": 74,
            "wind": 9,
        }

        result = asyncio.run(_get_weather("user-1"))

    mock_weather.assert_called_once_with(17.385, 78.4867)
    assert "27" in result and "clear" in result


def test_get_weather_tool_prompts_for_location_when_unset():
    from backend.services.chat_service import _get_weather

    with (
        patch("backend.services.chat_service.db.get_preferences") as mock_prefs,
        patch(
            "backend.services.chat_service.weather_service.get_current_conditions"
        ) as mock_weather,
    ):
        mock_prefs.return_value.location_lat = None
        mock_prefs.return_value.location_lon = None

        result = asyncio.run(_get_weather("user-1"))

    mock_weather.assert_not_called()
    assert "No location set" in result


def test_get_weather_tool_is_registered_locally():
    from backend.services.chat_service import LOCAL_TOOL_SCHEMAS, LOCAL_TOOLS

    schema_names = {t["name"] for t in LOCAL_TOOL_SCHEMAS}
    assert "get_weather" in schema_names
    assert "get_weather" in LOCAL_TOOLS


def test_process_query_merges_local_tool_schemas_with_mcp_tools():
    from backend.services.chat_service import LOCAL_TOOL_SCHEMAS, process_query

    open_mcp_session_with_client, mock_session = _mock_session(["get_weekly_stats"])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    with (
        patch("backend.services.chat_service.open_mcp_session_with_client", open_mcp_session_with_client),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = MagicMock(
            return_value=_mock_stream(fake_response, ["done"])
        )

        async def drain():
            chunks = []
            async for chunk in process_query(
                "user-123", "conv-123", [{"role": "user", "content": "hi"}]
            ):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(drain())

        assert "".join(chunks) == "done"
        called_tools = mock_client.messages.stream.call_args.kwargs["tools"]
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

    open_mcp_session_with_client, mock_session = _mock_session([])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    fake_memories = [{"fact": "Left knee sore, avoid speed work", "category": "injury"}]

    with (
        patch("backend.services.chat_service.open_mcp_session_with_client", open_mcp_session_with_client),
        patch(
            "backend.services.chat_service.db.get_memories", return_value=fake_memories
        ),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = MagicMock(
            return_value=_mock_stream(fake_response, ["done"])
        )

        async def drain():
            async for _ in process_query(
                "user-123", "conv-123", [{"role": "user", "content": "hi"}]
            ):
                pass

        asyncio.run(drain())

        system_blocks = mock_client.messages.stream.call_args.kwargs["system"]
        assert "Left knee sore, avoid speed work" in system_blocks[1]["text"]


def test_process_query_sets_cache_control_on_system_and_tools():
    from backend.agent import SYSTEM_PROMPT
    from backend.services.chat_service import process_query

    open_mcp_session_with_client, mock_session = _mock_session(["get_weekly_stats"])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    with (
        patch("backend.services.chat_service.open_mcp_session_with_client", open_mcp_session_with_client),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = MagicMock(
            return_value=_mock_stream(fake_response, ["done"])
        )

        async def drain():
            async for _ in process_query(
                "user-123", "conv-123", [{"role": "user", "content": "hi"}]
            ):
                pass

        asyncio.run(drain())

        call_kwargs = mock_client.messages.stream.call_args.kwargs

        system_blocks = call_kwargs["system"]
        assert isinstance(system_blocks, list)
        assert system_blocks[0]["text"] == SYSTEM_PROMPT
        assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in system_blocks[1]

        tools = call_kwargs["tools"]
        assert tools[-1]["cache_control"] == {"type": "ephemeral"}
        for tool in tools[:-1]:
            assert "cache_control" not in tool


def test_process_query_reports_cache_usage_to_langfuse():
    from backend.services.chat_service import process_query

    open_mcp_session_with_client, mock_session = _mock_session([])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]
    fake_response.usage.input_tokens = 10
    fake_response.usage.output_tokens = 5
    fake_response.usage.cache_creation_input_tokens = 100
    fake_response.usage.cache_read_input_tokens = 200

    mock_span_cm = MagicMock()
    mock_span_cm.__enter__.return_value = MagicMock()
    mock_span_cm.__exit__.return_value = False

    mock_generation = MagicMock()
    mock_generation_cm = MagicMock()
    mock_generation_cm.__enter__.return_value = mock_generation
    mock_generation_cm.__exit__.return_value = False

    mock_langfuse = MagicMock()
    mock_langfuse.start_as_current_observation.side_effect = [
        mock_span_cm,
        mock_generation_cm,
    ]

    with (
        patch("backend.services.chat_service.open_mcp_session_with_client", open_mcp_session_with_client),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.services.chat_service.langfuse_client", mock_langfuse),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = MagicMock(
            return_value=_mock_stream(fake_response, ["done"])
        )

        async def drain():
            async for _ in process_query(
                "user-123", "conv-123", [{"role": "user", "content": "hi"}]
            ):
                pass

        asyncio.run(drain())

    usage_details = mock_generation.update.call_args.kwargs["usage_details"]
    assert usage_details["cache_creation_input_tokens"] == 100
    assert usage_details["cache_read_input_tokens"] == 200


def test_call_tools_truncates_large_tool_results():
    from backend.services.chat_service import MAX_TOOL_RESULT_CHARS, call_tools

    open_mcp_session_with_client, mock_session = _mock_session([])
    mock_session.call_tool.side_effect = lambda name, args: "x" * 10_000

    block = MagicMock(type="tool_use", id="call-1")
    block.name = "get_recent_runs"
    block.input = {"days": 90}

    results = asyncio.run(call_tools("user-123", mock_session, [block]))

    assert results[0]["content"] == ("x" * MAX_TOOL_RESULT_CHARS) + "... [truncated]"


def test_call_tools_leaves_small_tool_results_untouched():
    from backend.services.chat_service import call_tools

    open_mcp_session_with_client, mock_session = _mock_session([])
    mock_session.call_tool.side_effect = lambda name, args: "short result"

    block = MagicMock(type="tool_use", id="call-1")
    block.name = "get_weekly_stats"
    block.input = {}

    results = asyncio.run(call_tools("user-123", mock_session, [block]))

    assert results[0]["content"] == "short result"


def test_process_query_persists_intermediate_tool_turns():
    from backend.services.chat_service import process_query

    open_mcp_session_with_client, mock_session = _mock_session(["get_weekly_stats"])
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
        patch("backend.services.chat_service.open_mcp_session_with_client", open_mcp_session_with_client),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.services.chat_service.db.save_message") as mock_save_message,
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = MagicMock(
            side_effect=[
                _mock_stream(tool_call_response, []),
                _mock_stream(final_response, ["done"]),
            ]
        )

        async def drain():
            chunks = []
            async for chunk in process_query(
                "user-123", "conv-123", [{"role": "user", "content": "hi"}]
            ):
                chunks.append(chunk)
            return "".join(chunks)

        reply = asyncio.run(drain())

    assert reply == "done"
    assert mock_save_message.call_count == 2
    mock_save_message.assert_any_call(
        "conv-123",
        "assistant",
        [{"type": "tool_use", "id": "call-1", "name": "get_weekly_stats", "input": {}}],
    )
    mock_save_message.assert_any_call(
        "conv-123",
        "user",
        [{"type": "tool_result", "tool_use_id": "call-1", "content": "42km this week"}],
    )


def test_process_query_injects_conversation_summary_into_system_prompt():
    from backend.services.chat_service import process_query

    open_mcp_session_with_client, mock_session = _mock_session([])

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
        patch("backend.services.chat_service.open_mcp_session_with_client", open_mcp_session_with_client),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=fake_summary,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = MagicMock(
            return_value=_mock_stream(fake_response, ["done"])
        )

        async def drain():
            async for _ in process_query(
                "user-123", "conv-123", [{"role": "user", "content": "hi"}]
            ):
                pass

        asyncio.run(drain())

        system_blocks = mock_client.messages.stream.call_args.kwargs["system"]
        assert "User is training for a fall marathon." in system_blocks[1]["text"]


def test_process_query_accumulates_usage_across_tool_loop():
    from backend.services.chat_service import process_query

    open_mcp_session_with_client, mock_session = _mock_session(["get_weekly_stats"])
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
    tool_call_response.usage.input_tokens = 100
    tool_call_response.usage.output_tokens = 20

    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    final_response = MagicMock(stop_reason="end_turn", content=[text_block])
    final_response.usage.input_tokens = 150
    final_response.usage.output_tokens = 40

    with (
        patch("backend.services.chat_service.open_mcp_session_with_client", open_mcp_session_with_client),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.services.chat_service.db.save_message"),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = MagicMock(
            side_effect=[
                _mock_stream(tool_call_response, []),
                _mock_stream(final_response, ["done"]),
            ]
        )

        usage = {}

        async def drain():
            async for _ in process_query(
                "user-123", "conv-123", [{"role": "user", "content": "hi"}], usage=usage
            ):
                pass

        asyncio.run(drain())

    assert usage["input_tokens"] == 250
    assert usage["output_tokens"] == 60


def test_process_query_omits_summary_section_when_none_exists():
    from backend.services.chat_service import process_query

    open_mcp_session_with_client, mock_session = _mock_session([])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    with (
        patch("backend.services.chat_service.open_mcp_session_with_client", open_mcp_session_with_client),
        patch("backend.services.chat_service.db.get_memories", return_value=[]),
        patch(
            "backend.services.chat_service.db.get_conversation_summary",
            return_value=None,
        ),
        patch("backend.agent.client") as mock_client,
    ):
        mock_client.messages.stream = MagicMock(
            return_value=_mock_stream(fake_response, ["done"])
        )

        async def drain():
            async for _ in process_query(
                "user-123", "conv-123", [{"role": "user", "content": "hi"}]
            ):
                pass

        asyncio.run(drain())

        system_blocks = mock_client.messages.stream.call_args.kwargs["system"]
        assert "Summary of earlier conversation" not in system_blocks[1]["text"]
