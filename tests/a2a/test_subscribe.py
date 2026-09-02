import asyncio

import httpx
import pytest

from conclave.a2a import AgentServer
from conclave.a2a.models import Message, Part, Role, SendMessageConfiguration, TaskState

from .test_server_client import client_for, make_card


async def test_return_immediately_gives_back_a_non_terminal_task_right_away():
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_handler(message: Message) -> list[Part]:
        started.set()
        await release.wait()
        return [Part.of_text("done")]

    server = AgentServer(make_card(), slow_handler)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("go")])
    task = await client.send_message(
        message, configuration=SendMessageConfiguration(return_immediately=True)
    )

    assert task.status.state in (TaskState.SUBMITTED, TaskState.WORKING)
    release.set()


async def test_subscribing_to_an_in_flight_task_receives_its_completion():
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_handler(message: Message) -> list[Part]:
        started.set()
        await release.wait()
        return [Part.of_text("finished late")]

    server = AgentServer(make_card(), slow_handler)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("go")])
    task = await client.send_message(
        message, configuration=SendMessageConfiguration(return_immediately=True)
    )
    await started.wait()

    async def subscriber():
        events = []
        async for event in client.subscribe_task(task.id):
            events.append(event)
        return events

    subscribe_task = asyncio.create_task(subscriber())
    await asyncio.sleep(0.02)  # let the subscription actually attach before it can complete
    release.set()

    events = await subscribe_task
    assert events[-1].status_update.status.state == TaskState.COMPLETED


async def test_subscribing_to_an_already_terminal_task_returns_409():
    async def instant_handler(message: Message) -> list[Part]:
        return [Part.of_text("already done")]

    server = AgentServer(make_card(), instant_handler)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("go")])
    task = await client.send_message(message)
    assert task.status.state == TaskState.COMPLETED

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        async for _ in client.subscribe_task(task.id):
            pass
    assert excinfo.value.response.status_code == 409


async def test_subscribing_to_an_unknown_task_returns_404():
    server = AgentServer(make_card(), lambda m: None)
    client = client_for(server)

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        async for _ in client.subscribe_task("does-not-exist"):
            pass
    assert excinfo.value.response.status_code == 404
