import httpx
from fastapi import FastAPI

from conclave.a2a import AgentServer, HttpPushNotifier
from conclave.a2a.models import (
    Message,
    Part,
    Role,
    SendMessageConfiguration,
    TaskPushNotificationConfig,
    TaskState,
)

from .test_server_client import client_for, make_card, uppercase_handler


def make_receiver():
    received = []
    app = FastAPI()

    @app.post("/webhook")
    async def webhook(payload: dict) -> dict:
        received.append(payload)
        return {}

    return app, received


async def test_push_notifications_deliver_every_status_transition_to_the_webhook():
    receiver_app, received = make_receiver()
    receiver_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=receiver_app), base_url="http://receiver"
    )
    notifier = HttpPushNotifier(client=receiver_client)

    server = AgentServer(make_card(), uppercase_handler, notifier=notifier)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("notify me")])
    config = TaskPushNotificationConfig(url="http://receiver/webhook")
    task = await client.send_message(
        message, configuration=SendMessageConfiguration(task_push_notification_config=config)
    )
    await receiver_client.aclose()

    assert task.status.state == TaskState.COMPLETED
    states = [event["status"]["state"] for event in received]
    assert "TASK_STATE_WORKING" in states
    assert states[-1] == "TASK_STATE_COMPLETED"
    assert all(event["taskId"] == task.id for event in received)


async def test_push_notification_config_crud_round_trips_through_the_client():
    server = AgentServer(make_card(), uppercase_handler)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("hi")])
    task = await client.send_message(message)

    config = TaskPushNotificationConfig(url="https://example.com/webhook", token="secret")
    created = await client.create_push_notification_config(task.id, config)
    assert created.url == "https://example.com/webhook"
    assert created.task_id == task.id

    listed = await client.list_push_notification_configs(task.id)
    assert [c.id for c in listed] == [created.id]

    await client.delete_push_notification_config(task.id, created.id)
    assert await client.list_push_notification_configs(task.id) == []


async def test_a_dead_webhook_does_not_break_task_completion():
    dead_notifier = HttpPushNotifier(
        client=httpx.AsyncClient(transport=httpx.ASGITransport(app=FastAPI()), base_url="http://dead")
    )
    server = AgentServer(make_card(), uppercase_handler, notifier=dead_notifier)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("still works")])
    config = TaskPushNotificationConfig(url="http://dead/nowhere")
    task = await client.send_message(
        message, configuration=SendMessageConfiguration(task_push_notification_config=config)
    )

    assert task.status.state == TaskState.COMPLETED
    assert task.artifacts[0].parts[0].text == "STILL WORKS"
