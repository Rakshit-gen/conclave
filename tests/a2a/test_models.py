import pytest

from conclave.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
)


def test_part_requires_exactly_one_content_field():
    Part(text="hello")
    Part(url="https://example.com/f.pdf")
    Part(data={"a": 1})

    with pytest.raises(ValueError, match="exactly one"):
        Part()
    with pytest.raises(ValueError, match="exactly one"):
        Part(text="hello", url="https://example.com")


def test_message_round_trips_through_camelcase_wire_json():
    msg = Message(
        context_id="ctx-1",
        task_id="task-1",
        role=Role.USER,
        parts=[Part.of_text("hi there")],
    )
    wire = msg.model_dump(by_alias=True)
    assert wire["contextId"] == "ctx-1"
    assert wire["taskId"] == "task-1"
    assert "context_id" not in wire

    restored = Message.model_validate(wire)
    assert restored.context_id == "ctx-1"
    assert restored.task_id == "task-1"
    assert restored.parts[0].text == "hi there"


def test_task_state_terminal_and_interrupted_classification():
    assert TaskState.COMPLETED.is_terminal
    assert TaskState.FAILED.is_terminal
    assert not TaskState.WORKING.is_terminal
    assert TaskState.INPUT_REQUIRED.is_interrupted
    assert not TaskState.COMPLETED.is_interrupted


def test_task_wire_shape_matches_spec_field_names():
    task = Task(context_id="ctx-1", status=TaskStatus(state=TaskState.SUBMITTED))
    wire = task.model_dump(by_alias=True, exclude_none=True)
    assert wire["contextId"] == "ctx-1"
    assert wire["status"]["state"] == "TASK_STATE_SUBMITTED"
    assert "timestamp" in wire["status"]


def test_agent_card_accepts_both_python_and_wire_field_names():
    card = AgentCard(
        name="Researcher",
        description="Finds things out.",
        supported_interfaces=[AgentInterface(url="http://localhost:9001")],
        capabilities=AgentCapabilities(streaming=True),
    )
    wire = card.model_dump(by_alias=True)
    assert wire["supportedInterfaces"][0]["protocolBinding"] == "HTTP+JSON"

    restored = AgentCard.model_validate(wire)
    assert restored.supported_interfaces[0].protocol_version == "1.0"
