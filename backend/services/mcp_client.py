import os
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from backend.jwt_issuer import mint_token
from observability.otel_setup import inject_traceparent

HEALTH_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")
CALENDAR_SERVER_URL = os.environ.get(
    "CALENDAR_MCP_SERVER_URL", "http://127.0.0.1:8002/mcp"
)


def _build_session_headers(token: str) -> dict[str, str]:
    return inject_traceparent({"Authorization": f"Bearer {token}"})


def refresh_traceparent(http_client: httpx.AsyncClient) -> None:
    """Re-stamp the client's traceparent header from whatever span is current
    right now. A session's headers are otherwise fixed at open time, but a
    session can be reused across multiple tool calls in a request's
    tool-use loop — call this immediately before each individual tool call
    so it's attributed to the right span, not whichever span was active
    back when the session was first opened."""
    http_client.headers.update(inject_traceparent({}))


@asynccontextmanager
async def open_mcp_session_with_client(user_id: str, server_url: str):
    """Same as open_mcp_session, but also yields the underlying
    httpx.AsyncClient so the caller can call refresh_traceparent() before
    each individual tool call — needed only where one session serves
    multiple tool calls over time (see backend/services/chat_service.py)."""
    token = mint_token(user_id)
    async with httpx.AsyncClient(
        headers=_build_session_headers(token)
    ) as http_client:
        try:
            async with streamable_http_client(server_url, http_client=http_client) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session, http_client
        except* httpx.ConnectError as eg:
            raise HTTPException(
                status_code=503,
                detail=f"A data service is unavailable — is the MCP server running on {server_url}?",
            ) from eg


@asynccontextmanager
async def open_mcp_session(user_id: str, server_url: str):
    """Open a fresh, per-caller MCP session authenticated as user_id.

    Short-lived by design, matching the 5-minute JWT it mints — a cached,
    long-lived session couldn't carry a fresh token per request anyway."""
    async with open_mcp_session_with_client(user_id, server_url) as (
        session,
        _http_client,
    ):
        yield session


async def get_tool_schemas(session: ClientSession) -> list[dict]:
    """Fetch the server's tools and convert them to Anthropic's tool format."""
    tools_response = await session.list_tools()

    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        }
        for t in tools_response.tools
    ]
