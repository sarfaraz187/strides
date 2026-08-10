import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _count_tokens_result(input_tokens: int):
    return SimpleNamespace(input_tokens=input_tokens)


def _text_response(text: str):
    block = MagicMock(type="text", text=text)
    return SimpleNamespace(content=[block])


def test_maybe_fold_returns_rows_unchanged_when_under_threshold():
    from backend.services.summarization_service import maybe_fold

    rows = [{"id": 1, "role": "user", "content": "hi"}]

    with patch("backend.services.summarization_service.client") as mock_client:
        mock_client.messages.count_tokens.return_value = _count_tokens_result(100)

        result = asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=[]))

    mock_client.messages.create.assert_not_called()
    assert result == rows


def test_maybe_fold_returns_rows_unchanged_when_at_or_below_recent_window():
    from backend.services.summarization_service import KEEP_RECENT_MESSAGES, maybe_fold

    rows = [
        {"id": i, "role": "user", "content": f"msg {i}"}
        for i in range(KEEP_RECENT_MESSAGES)
    ]

    with patch("backend.services.summarization_service.client") as mock_client:
        mock_client.messages.count_tokens.return_value = _count_tokens_result(50_000)

        result = asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=[]))

    mock_client.messages.create.assert_not_called()
    assert result == rows


def test_maybe_fold_folds_oldest_rows_and_returns_remainder():
    from backend.services.summarization_service import KEEP_RECENT_MESSAGES, maybe_fold

    total = KEEP_RECENT_MESSAGES + 3
    rows = [
        {"id": 100 + i, "role": "user", "content": f"msg {i}"} for i in range(total)
    ]

    with (
        patch("backend.services.summarization_service.client") as mock_client,
        patch("backend.services.summarization_service.db") as mock_db,
    ):
        mock_client.messages.count_tokens.return_value = _count_tokens_result(50_000)
        mock_client.messages.create.return_value = _text_response("Compressed summary.")
        mock_db.get_conversation_summary.return_value = None

        result = asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=[]))

    assert len(result) == KEEP_RECENT_MESSAGES
    assert result[0]["content"] == "msg 3"  # first 3 folded away
    assert result[0]["id"] == 103

    mock_db.upsert_conversation_summary.assert_called_once_with(
        "user-123",
        "Compressed summary.",
        102,  # id of the last folded row
    )


def test_maybe_fold_keeps_tool_use_and_tool_result_pair_together():
    from backend.services.summarization_service import KEEP_RECENT_MESSAGES, maybe_fold

    tool_use_row = {
        "id": 101,
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "call-1", "name": "get_weekly_stats", "input": {}}],
    }
    tool_result_row = {
        "id": 102,
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "call-1", "content": "42km"}],
    }
    # Naive cutoff (len(rows) - KEEP_RECENT_MESSAGES) lands exactly on tool_result_row,
    # which would orphan it from its paired tool_use_row.
    rows = (
        [{"id": 100, "role": "user", "content": "msg 0"}, tool_use_row, tool_result_row]
        + [
            {"id": 103 + i, "role": "user", "content": f"msg {i}"}
            for i in range(KEEP_RECENT_MESSAGES - 1)
        ]
    )
    assert len(rows) - KEEP_RECENT_MESSAGES == 2  # sanity check on the naive cutoff

    with (
        patch("backend.services.summarization_service.client") as mock_client,
        patch("backend.services.summarization_service.db") as mock_db,
    ):
        mock_client.messages.count_tokens.return_value = _count_tokens_result(50_000)
        mock_client.messages.create.return_value = _text_response("Compressed summary.")
        mock_db.get_conversation_summary.return_value = None

        result = asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=[]))

    assert result[0] == tool_use_row
    assert result[1] == tool_result_row
    mock_db.upsert_conversation_summary.assert_called_once_with(
        "user-123", "Compressed summary.", 100  # only msg 0 got folded away
    )


def test_maybe_fold_includes_existing_summary_in_the_fold_prompt():
    from backend.services.summarization_service import KEEP_RECENT_MESSAGES, maybe_fold

    total = KEEP_RECENT_MESSAGES + 1
    rows = [{"id": i, "role": "user", "content": f"msg {i}"} for i in range(total)]

    with (
        patch("backend.services.summarization_service.client") as mock_client,
        patch("backend.services.summarization_service.db") as mock_db,
    ):
        mock_client.messages.count_tokens.return_value = _count_tokens_result(50_000)
        mock_client.messages.create.return_value = _text_response("New summary.")
        mock_db.get_conversation_summary.return_value = {
            "summary_text": "Existing summary text.",
            "through_message_id": 0,
        }

        asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=[]))

    fold_call_kwargs = mock_client.messages.create.call_args.kwargs
    prompt_text = fold_call_kwargs["messages"][0]["content"]
    assert "Existing summary text." in prompt_text


def test_maybe_fold_passes_tools_to_count_tokens():
    from backend.services.summarization_service import maybe_fold

    rows = [{"id": 1, "role": "user", "content": "hi"}]
    fake_tools = [{"name": "get_weekly_stats", "description": "", "input_schema": {}}]

    with patch("backend.services.summarization_service.client") as mock_client:
        mock_client.messages.count_tokens.return_value = _count_tokens_result(100)

        asyncio.run(maybe_fold("user-123", "system prompt", rows, tools=fake_tools))

    call_kwargs = mock_client.messages.count_tokens.call_args.kwargs
    assert call_kwargs["tools"] == fake_tools


def test_content_to_text_handles_plain_string():
    from backend.services.summarization_service import _content_to_text

    assert _content_to_text("hello") == "hello"


def test_content_to_text_handles_text_block_dicts():
    from backend.services.summarization_service import _content_to_text

    content = [{"type": "text", "text": "hello"}]
    assert _content_to_text(content) == "hello"


def test_content_to_text_handles_tool_result_block_dicts():
    from backend.services.summarization_service import _content_to_text

    content = [
        {"type": "tool_result", "tool_use_id": "abc", "content": "42km this week"}
    ]
    assert "42km this week" in _content_to_text(content)


def test_content_to_text_handles_tool_use_block_dicts():
    from backend.services.summarization_service import _content_to_text

    content = [
        {"type": "tool_use", "id": "abc", "name": "get_weekly_stats", "input": {}}
    ]
    assert "get_weekly_stats" in _content_to_text(content)
