import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from backend.services import chat_service


def _mock_session_with_client(tool_names: list[str]):
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


def _mock_stream(final_response, text_chunks: list[str]):
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


def test_process_query_emits_a_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    chat_service.tracer = provider.get_tracer("strides-backend")

    open_mcp_session_with_client, _mock_session = _mock_session_with_client([])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    text_block = MagicMock(type="text", text="done")
    text_block.model_dump.return_value = {"type": "text", "text": "done"}
    fake_response.content = [text_block]

    with (
        patch(
            "backend.services.chat_service.open_mcp_session_with_client",
            open_mcp_session_with_client,
        ),
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
            async for _ in chat_service.process_query(
                "test-user", "conv-1", [{"role": "user", "content": "hello"}]
            ):
                pass

        asyncio.run(drain())

    spans = exporter.get_finished_spans()
    assert any(s.name == "chat.process_query" for s in spans)
