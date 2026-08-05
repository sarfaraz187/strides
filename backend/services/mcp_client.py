from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from backend.jwt_issuer import mint_token

SERVER_URL = "http://127.0.0.1:8001/mcp"


@asynccontextmanager
async def open_mcp_session(user_id: str):
    """Open a fresh, per-caller MCP session authenticated as user_id.

    Short-lived by design, matching the 5-minute JWT it mints — a cached,
    long-lived session couldn't carry a fresh token per request anyway."""
    token = mint_token(user_id)
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http_client:
        try:
            async with streamable_http_client(SERVER_URL, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        except* httpx.ConnectError as eg:
            raise HTTPException(
                status_code=503,
                detail=f"Health data service unavailable — is the MCP fit_server running on {SERVER_URL}?",
            ) from eg


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
