#!/usr/bin/env python3
"""
Live MCP server integration tests.
Disabled unless RUN_LIVE_MCP_SERVER_TESTS=1 is set because they start the HTTP server
and exercise it via the FastMCP client.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

import pytest
from fastmcp.client import Client

LIVE_FLAG = os.getenv("RUN_LIVE_MCP_SERVER_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE_FLAG,
    reason="Set RUN_LIVE_MCP_SERVER_TESTS=1 to run live MCP server tests",
)


def _get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _get_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_for_server(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            client = Client(url)
            async with client:
                await client.list_tools()
            return
        except Exception:
            if time.time() >= deadline:
                raise
            await asyncio.sleep(0.5)


def _extract_payload(result) -> Dict[str, Any]:
    if result.data is not None:
        if hasattr(result.data, "dict"):
            return result.data.dict()
        if isinstance(result.data, dict):
            return result.data
    if result.structured_content:
        return result.structured_content
    raise AssertionError("Tool result did not include structured content")


def _call_tool_sync(base_url: str, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    async def _call() -> Dict[str, Any]:
        client = Client(base_url)
        async with client:
            result = await client.call_tool(name, arguments)
        return _extract_payload(result)

    return asyncio.run(_call())


@pytest.fixture(scope="session")
def live_mcp_server(data_files: Dict[str, str]):
    host = "127.0.0.1"
    port = _get_free_port()
    base_url = f"http://{host}:{port}/mcp"
    root = _get_project_root()

    env = os.environ.copy()
    env["AIRPORTS_DB"] = data_files["airports_db"]
    env["RULES_JSON"] = data_files["rules_json"]
    env.setdefault("LOG_LEVEL", "ERROR")

    cmd = [
        sys.executable,
        "mcp_server/main.py",
        "--transport",
        "http",
        "--host",
        host,
        "--port",
        str(port),
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    try:
        asyncio.run(_wait_for_server(base_url))
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.live_mcp_server
def test_live_http_search_airports(live_mcp_server):
    payload = _call_tool_sync(
        live_mcp_server,
        "search_airports",
        {"query": "LFPG", "max_results": 5},
    )

    assert payload["count"] >= 1
    assert any(airport["ident"] == "LFPG" for airport in payload["airports"])


@pytest.mark.live_mcp_server
def test_live_http_find_airports_near_route(live_mcp_server):
    payload = _call_tool_sync(
        live_mcp_server,
        "find_airports_near_route",
        {"from_location": "EGLL", "to_location": "LFPG", "max_distance_nm": 40},
    )

    assert payload["count"] >= 1
    assert payload["airports"]

