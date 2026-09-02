"""Runs a real AgentServer on a real localhost TCP port for the duration of
a test — `delegate()` talks plain httpx over the network, so this is the
only way to test it without changing its shape just to accommodate a mock.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket

import httpx
import pytest
import uvicorn

from conclave.a2a import AgentServer
from conclave.a2a.models import AgentCapabilities, AgentCard, AgentInterface


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def run_agent_server(server: AgentServer):
    port = _free_port()
    config = uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning")
    uv_server = uvicorn.Server(config)
    task = asyncio.create_task(uv_server.serve())
    base_url = f"http://127.0.0.1:{port}"

    async with httpx.AsyncClient() as probe:
        for _ in range(50):
            if uv_server.started:
                try:
                    resp = await probe.get(f"{base_url}/.well-known/agent-card.json")
                    if resp.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
            await asyncio.sleep(0.02)
        else:
            raise RuntimeError("agent server did not become ready in time")

    try:
        yield base_url
    finally:
        uv_server.should_exit = True
        await task


@pytest.fixture
def make_echo_card():
    def _make(name: str = "Echo Agent") -> AgentCard:
        return AgentCard(
            name=name,
            description="Echoes text back, uppercased.",
            supported_interfaces=[AgentInterface(url="http://127.0.0.1")],
            capabilities=AgentCapabilities(streaming=True),
        )

    return _make
