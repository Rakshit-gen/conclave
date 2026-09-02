"""Exercises the gRPC binding over a real bound TCP port (not an in-process
mock), the same way tests/conftest.py's `run_agent_server` proves the REST
binding over a real socket — a stub-only test wouldn't catch codegen/wire
issues like the import bug this binding shipped with initially.
"""

from __future__ import annotations

import contextlib

import grpc
import httpx
import pytest

from conclave.a2a import AgentServer, ApiKeyAuthenticator, GrpcAgentClient, build_server
from conclave.a2a.models import (
    APIKeySecurityScheme,
    Message,
    Part,
    Role,
    TaskPushNotificationConfig,
)

from ..conftest import _free_port
from .test_server_client import make_card, uppercase_handler


@contextlib.asynccontextmanager
async def run_grpc_server(agent_server: AgentServer):
    port = _free_port()
    server = build_server(agent_server, address=f"127.0.0.1:{port}")
    await server.start()
    client = GrpcAgentClient(f"127.0.0.1:{port}")
    try:
        yield client
    finally:
        await client.close()
        await server.stop(grace=None)


async def test_send_message_over_grpc_runs_the_same_handler_as_rest():
    server = AgentServer(make_card(), uppercase_handler)
    async with run_grpc_server(server) as client:
        task = await client.send_message(Message(role=Role.USER, parts=[Part.of_text("hello")]))
        assert task.artifacts[0].parts[0].text == "HELLO"


async def test_grpc_and_rest_bindings_share_the_same_task_store():
    server = AgentServer(make_card(), uppercase_handler)
    rest_transport = httpx.ASGITransport(app=server.app)
    rest_client = httpx.AsyncClient(transport=rest_transport, base_url="http://testserver")

    async with run_grpc_server(server) as grpc_client:
        rest_response = await rest_client.post(
            "/message:send",
            json={"message": {"role": "ROLE_USER", "parts": [{"text": "shared"}]}},
        )
        task_id = rest_response.json()["id"]

        fetched = await grpc_client.get_task(task_id)
        assert fetched.artifacts[0].parts[0].text == "SHARED"


async def test_streaming_send_message_over_grpc_emits_full_lifecycle():
    server = AgentServer(make_card(), uppercase_handler)
    async with run_grpc_server(server) as client:
        message = Message(role=Role.USER, parts=[Part.of_text("go")])
        events = [event async for event in client.stream_message(message)]

        assert events[0].task.status.state.value == "TASK_STATE_SUBMITTED"
        assert events[-1].status_update.status.state.value == "TASK_STATE_COMPLETED"


async def test_push_notification_config_crud_over_grpc():
    server = AgentServer(make_card(), uppercase_handler)
    async with run_grpc_server(server) as client:
        task = await client.send_message(Message(role=Role.USER, parts=[Part.of_text("hi")]))
        config = TaskPushNotificationConfig(url="https://example.com/hook")
        created = await client.create_push_notification_config(task.id, config)

        listed = await client.list_push_notification_configs(task.id)
        assert [c.id for c in listed] == [created.id]

        await client.delete_push_notification_config(task.id, created.id)
        assert await client.list_push_notification_configs(task.id) == []


async def test_grpc_auth_is_enforced():
    scheme = APIKeySecurityScheme(location="header", name="x-api-key")
    authenticator = ApiKeyAuthenticator(scheme, valid_keys={"secret"})
    server = AgentServer(make_card(), uppercase_handler, authenticator=authenticator)

    async with run_grpc_server(server) as unauthenticated:
        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await unauthenticated.send_message(Message(role=Role.USER, parts=[Part.of_text("hi")]))
        assert excinfo.value.code() == grpc.StatusCode.UNAUTHENTICATED

    port = _free_port()
    grpc_server = build_server(server, address=f"127.0.0.1:{port}")
    await grpc_server.start()
    authenticated = GrpcAgentClient(f"127.0.0.1:{port}", auth_headers={"x-api-key": "secret"})
    try:
        task = await authenticated.send_message(Message(role=Role.USER, parts=[Part.of_text("hi")]))
        assert task.artifacts[0].parts[0].text == "HI"
    finally:
        await authenticated.close()
        await grpc_server.stop(grace=None)


async def test_get_task_for_unknown_id_returns_not_found():
    server = AgentServer(make_card(), uppercase_handler)
    async with run_grpc_server(server) as client:
        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await client.get_task("does-not-exist")
        assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND


async def test_subscribe_to_an_already_terminal_task_fails_precondition():
    server = AgentServer(make_card(), uppercase_handler)
    async with run_grpc_server(server) as client:
        task = await client.send_message(Message(role=Role.USER, parts=[Part.of_text("hi")]))
        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            async for _ in client.subscribe_task(task.id):
                pass
        assert excinfo.value.code() == grpc.StatusCode.FAILED_PRECONDITION
