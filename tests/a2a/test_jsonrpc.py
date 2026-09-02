import httpx
import pytest

from conclave.a2a import (
    AgentServer,
    ApiKeyAuthenticator,
    JsonRpcAgentClient,
    JsonRpcError,
    api_key_headers,
)
from conclave.a2a.models import (
    APIKeySecurityScheme,
    Message,
    Part,
    Role,
    TaskPushNotificationConfig,
)

from .test_server_client import make_card, uppercase_handler


def jsonrpc_client_for(
    server: AgentServer, auth_headers: dict[str, str] | None = None
) -> JsonRpcAgentClient:
    transport = httpx.ASGITransport(app=server.app)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return JsonRpcAgentClient(
        "http://testserver", http_client=http_client, auth_headers=auth_headers
    )


async def test_send_message_over_jsonrpc_runs_the_same_handler_as_rest():
    server = AgentServer(make_card(), uppercase_handler)
    client = jsonrpc_client_for(server)

    task = await client.send_message(Message(role=Role.USER, parts=[Part.of_text("hello")]))

    assert task.artifacts[0].parts[0].text == "HELLO"


async def test_get_task_and_list_tasks_over_jsonrpc():
    server = AgentServer(make_card(), uppercase_handler)
    client = jsonrpc_client_for(server)

    sent = await client.send_message(Message(role=Role.USER, parts=[Part.of_text("hi")]))
    fetched = await client.get_task(sent.id)
    assert fetched.id == sent.id

    listed = await client.list_tasks()
    assert sent.id in [t.id for t in listed]


async def test_unknown_method_returns_a_jsonrpc_error_not_an_http_error():
    server = AgentServer(make_card(), uppercase_handler)
    client = jsonrpc_client_for(server)

    with pytest.raises(JsonRpcError) as excinfo:
        await client._call("NotARealMethod", {})
    assert excinfo.value.code == -32601


async def test_get_task_for_unknown_id_returns_a_jsonrpc_error():
    server = AgentServer(make_card(), uppercase_handler)
    client = jsonrpc_client_for(server)

    with pytest.raises(JsonRpcError) as excinfo:
        await client.get_task("does-not-exist")
    assert excinfo.value.code == -32002


async def test_streaming_send_message_over_jsonrpc_emits_full_lifecycle():
    server = AgentServer(make_card(), uppercase_handler)
    client = jsonrpc_client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("go")])
    events = [event async for event in client.stream_message(message)]

    assert events[0]["task"]["status"]["state"] == "TASK_STATE_SUBMITTED"
    assert events[-1]["statusUpdate"]["status"]["state"] == "TASK_STATE_COMPLETED"


async def test_push_notification_config_crud_over_jsonrpc():
    server = AgentServer(make_card(), uppercase_handler)
    client = jsonrpc_client_for(server)

    task = await client.send_message(Message(role=Role.USER, parts=[Part.of_text("hi")]))
    config = TaskPushNotificationConfig(url="https://example.com/hook")
    created = await client.create_push_notification_config(task.id, config)

    listed = await client.list_push_notification_configs(task.id)
    assert [c.id for c in listed] == [created.id]

    await client.delete_push_notification_config(task.id, created.id)
    assert await client.list_push_notification_configs(task.id) == []


async def test_jsonrpc_auth_is_enforced_the_same_way_as_rest():
    scheme = APIKeySecurityScheme(location="header", name="X-API-Key")
    authenticator = ApiKeyAuthenticator(scheme, valid_keys={"secret"})
    server = AgentServer(make_card(), uppercase_handler, authenticator=authenticator)

    unauthenticated = jsonrpc_client_for(server)
    with pytest.raises(JsonRpcError) as excinfo:
        await unauthenticated.send_message(Message(role=Role.USER, parts=[Part.of_text("hi")]))
    assert excinfo.value.code == -32001

    authenticated = jsonrpc_client_for(server, auth_headers=api_key_headers("X-API-Key", "secret"))
    task = await authenticated.send_message(Message(role=Role.USER, parts=[Part.of_text("hi")]))
    assert task.artifacts[0].parts[0].text == "HI"


async def test_rest_and_jsonrpc_bindings_share_the_same_task_store():
    from conclave.a2a import AgentClient

    server = AgentServer(make_card(), uppercase_handler)
    rest_client = AgentClient(
        "http://testserver",
        http_client=httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app), base_url="http://testserver"
        ),
    )
    rpc_client = jsonrpc_client_for(server)

    task = await rest_client.send_message(Message(role=Role.USER, parts=[Part.of_text("shared")]))
    fetched_via_rpc = await rpc_client.get_task(task.id)

    assert fetched_via_rpc.artifacts[0].parts[0].text == "SHARED"
