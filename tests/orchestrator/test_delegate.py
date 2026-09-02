from conclave.a2a import AgentServer
from conclave.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Message,
    Part,
    Role,
)
from conclave.core import InMemoryEventStore, Runtime, step
from conclave.orchestrator import AgentRegistry, delegate

from ..conftest import run_agent_server


async def test_delegate_runs_inside_a_durable_workflow(make_echo_card):
    async def uppercase(message: Message) -> list[Part]:
        text = "".join(p.text or "" for p in message.parts)
        return [Part.of_text(text.upper())]

    server = AgentServer(make_echo_card(), uppercase)

    async with run_agent_server(server) as agent_url:

        async def wf(input_: dict) -> str:
            task = await delegate(
                agent_url, Message(role=Role.USER, parts=[Part.of_text(input_["text"])])
            )
            return task.artifacts[0].parts[0].text

        runtime = Runtime(InMemoryEventStore())
        runtime.register("wf", wf)
        result = await runtime.start("wf", "wf-delegate-1", {"text": "hello agent"})

        assert result.status == "completed"
        assert result.value == "HELLO AGENT"


async def test_delegate_is_not_re_sent_on_replay_of_a_completed_workflow(make_echo_card):
    call_count = 0

    async def counting_handler(message: Message) -> list[Part]:
        nonlocal call_count
        call_count += 1
        text = "".join(p.text or "" for p in message.parts)
        return [Part.of_text(text.upper())]

    server = AgentServer(make_echo_card(), counting_handler)

    async with run_agent_server(server) as agent_url:

        async def wf(input_: dict) -> str:
            task = await delegate(
                agent_url, Message(role=Role.USER, parts=[Part.of_text(input_["text"])])
            )
            # A second durable step downstream of the delegation, so a bug
            # that re-runs everything on replay (not just the delegation)
            # would also show up here.
            return await step(lambda: task.artifacts[0].parts[0].text, name="extract")

        store = InMemoryEventStore()
        runtime = Runtime(store)
        runtime.register("wf", wf)
        await runtime.start("wf", "wf-delegate-2", {"text": "once only"})
        assert call_count == 1

        runtime_after_restart = Runtime(store)
        runtime_after_restart.register("wf", wf)
        result = await runtime_after_restart.resume("wf-delegate-2")

    assert result.status == "completed"
    assert call_count == 1


async def test_registry_discovers_skills_from_a_real_running_agent():
    card = AgentCard(
        name="Researcher",
        description="Finds facts.",
        supported_interfaces=[AgentInterface(url="http://127.0.0.1")],
        capabilities=AgentCapabilities(),
        skills=[
            AgentSkill(
                id="research", name="Research", description="Digs up facts.", tags=["research"]
            )
        ],
    )

    async def handler(message: Message) -> list[Part]:
        return [Part.of_text("ok")]

    server = AgentServer(card, handler)
    async with run_agent_server(server) as agent_url:
        registry = AgentRegistry()
        await registry.register(agent_url)

        assert registry.find_by_skill("research") == [agent_url]
        assert registry.find_by_skill("writing") == []
