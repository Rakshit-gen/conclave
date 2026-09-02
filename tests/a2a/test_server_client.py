import httpx
import pytest

from conclave.a2a import AgentClient, AgentServer
from conclave.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    Message,
    Part,
    Role,
    TaskState,
)


def make_card(name: str = "Echo Agent") -> AgentCard:
    return AgentCard(
        name=name,
        description="Echoes back whatever text it receives, uppercased.",
        supported_interfaces=[AgentInterface(url="http://testserver")],
        capabilities=AgentCapabilities(streaming=True),
    )


async def uppercase_handler(message: Message) -> list[Part]:
    text = "".join(p.text or "" for p in message.parts)
    return [Part.of_text(text.upper())]


async def failing_handler(message: Message) -> list[Part]:
    raise ValueError("deliberately broken")


def client_for(server: AgentServer) -> AgentClient:
    transport = httpx.ASGITransport(app=server.app)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return AgentClient("http://testserver", http_client=http_client)


async def test_agent_card_is_served_at_the_well_known_path():
    server = AgentServer(make_card(), uppercase_handler)
    client = client_for(server)

    card = await client.discover()

    assert card.name == "Echo Agent"
    assert card.capabilities.streaming is True
    assert card.supported_interfaces[0].protocol_binding == "HTTP+JSON"


async def test_send_message_runs_the_handler_and_returns_a_completed_task():
    server = AgentServer(make_card(), uppercase_handler)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("hello")])
    task = await client.send_message(message)

    assert task.status.state == TaskState.COMPLETED
    assert task.artifacts[0].parts[0].text == "HELLO"


async def test_send_message_reports_handler_failure_as_a_failed_task():
    server = AgentServer(make_card(), failing_handler)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("hello")])
    task = await client.send_message(message)

    assert task.status.state == TaskState.FAILED
    assert "deliberately broken" in task.status.message.parts[0].text


async def test_get_task_returns_the_same_task_after_completion():
    server = AgentServer(make_card(), uppercase_handler)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("hi")])
    sent = await client.send_message(message)

    fetched = await client.get_task(sent.id)
    assert fetched.id == sent.id
    assert fetched.status.state == TaskState.COMPLETED


async def test_get_task_404s_for_an_unknown_id():
    server = AgentServer(make_card(), uppercase_handler)
    client = client_for(server)

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_task("does-not-exist")


async def test_stream_message_emits_submitted_working_artifact_completed():
    server = AgentServer(make_card(), uppercase_handler)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("stream me")])
    frames = [frame async for frame in client.stream_message(message)]

    assert frames[0].task is not None
    assert frames[0].task.status.state == TaskState.SUBMITTED
    assert frames[1].status_update.status.state == TaskState.WORKING
    assert frames[2].artifact_update.artifact.parts[0].text == "STREAM ME"
    assert frames[3].status_update.status.state == TaskState.COMPLETED
