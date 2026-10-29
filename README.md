# conclave

A multi-agent orchestrator that survives crashes. You write a workflow as a plain async Python function that hands work to other agents and can pause for a human's approval. Kill the process halfway, start a new one on the same event log, and it carries on from where it stopped without asking any agent to redo work it already did.

Everything is built from scratch: no LangGraph, no Temporal SDK, no A2A SDK underneath. The repo has two parts:

1. **A durable execution core** (`conclave/core`). Event-sourced workflow state, deterministic replay, crash recovery and approval gates that survive restarts.
2. **An A2A (Agent2Agent) protocol implementation** (`conclave/a2a`). Agent Card discovery, the task lifecycle, and all three wire bindings from [the spec](https://github.com/a2aproject/A2A): REST, JSON-RPC 2.0 and gRPC. `docs/a2a-spec-notes.md` maps it field by field.

`conclave/orchestrator` joins them: a workflow can hand a task to a remote agent it has never talked to, wait for approval across a crash and a restart, and keep going.

## Quickstart

Python 3.11+.

```bash
git clone https://github.com/Rakshit-gen/conclave.git
cd conclave
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Run the demo

`examples/pipeline/` runs Researcher, then Writer, then a **human approval gate**, then Reviewer. Each agent is its own OS process serving A2A on a localhost port.

```bash
python -m examples.pipeline.run start "distributed consensus"
python -m examples.pipeline.run status    # suspended, waiting on approve_draft
python -m examples.pipeline.run approve   # completed, prints the final draft
python -m examples.pipeline.run stop      # stops the three agent processes
```

### Watch it recover from a crash

```bash
python -m examples.pipeline.run start "distributed consensus" --crash-after write
# exits with os._exit(137) right after "write" is saved, the same exit code as kill -9
echo $?    # 137

python -m examples.pipeline.run resume
# suspended, waiting on approve_draft.
# "research" and "write" came from the event log; neither agent was called again.

python -m examples.pipeline.run approve
# completed
```

`tests/examples/test_pipeline_demo.py` runs this exact sequence as a subprocess test, so the demo cannot quietly break.

The demo agents transform strings instead of calling a model. The demo is there to prove the orchestration layer, and a real LLM would only add cost and flaky tests. Swap the handler in `examples/pipeline/agents.py` for a model call and nothing else changes.

## Writing a workflow

```python
from conclave.core import Runtime, SQLiteEventStore, step, wait_for_signal

async def fetch_report(topic: str) -> dict:
    ...  # any side effect: an HTTP call, an LLM call, an A2A delegation

async def my_workflow(input_: dict) -> dict:
    report = await step(fetch_report, input_["topic"], name="fetch")
    await wait_for_signal("approve")
    return {"report": report}

runtime = Runtime(SQLiteEventStore("conclave.db"))
runtime.register("my_workflow", my_workflow)

result = await runtime.start("my_workflow", "run-1", {"topic": "raft"})
# result.status == "suspended", result.waiting_on == "approve"
result = await runtime.signal("run-1", "approve")
# result.status == "completed"
```

To hand work to another agent, use `conclave.orchestrator.delegate(agent_url, message)`. It is a `step()` around an A2A `send_message`, so it is recorded and never re-sent on replay. `AgentRegistry` fetches Agent Cards and finds agents by skill tag.

## How replay works

There is no sandboxed workflow language. A workflow is a normal async function, and **the whole function runs again from the top every time it is driven**. Every side effect goes through `step()` or `wait_for_signal()`, which first look at a cursor into the event log:

- If the step is already recorded, its stored result comes back straight away. The real call never happens twice.
- The first step with nothing recorded is the live edge. It runs for real, and its result is written to the log before the function may continue.

So workflow code must be deterministic: the same inputs must produce the same sequence of `step()` calls. Temporal has the same rule for the same reason. A mismatch raises `NonDeterminismError`. `get_version()` is the way to change a workflow's steps across a deploy without breaking runs already in flight.

The docstrings in `conclave/core/execution.py` and `conclave/core/runtime.py` go deeper. They were written as design notes while building it.

## Inspecting workflows

```bash
conclave list --db examples/pipeline/.run/conclave.db
conclave status  <workflow-id> --db examples/pipeline/.run/conclave.db
conclave history <workflow-id> --db examples/pipeline/.run/conclave.db
conclave agent-card http://127.0.0.1:9001
```

`history` prints every event actually recorded for a workflow. It is the easiest way to check what the engine did, rather than what the code says it should do.

## A2A coverage

- REST, JSON-RPC 2.0 and gRPC bindings, all sharing one `TaskRunner` per agent. A task started on one binding is visible on the others.
- Push notifications: webhook delivery on every task state change.
- `tasks/{id}:subscribe` streaming.
- Security schemes (API key, HTTP auth, OAuth2, OIDC, mTLS) are modeled field for field. Enforcement covers API key and Bearer. OAuth2, OIDC and mTLS validation need a real identity provider, which is left to whoever deploys the agent.

gRPC needs the extra: `pip install -e ".[grpc]"`.

## Layout

```
conclave/
  core/            replay engine and SQLite event store
  a2a/             protocol models and the three transport bindings
    proto/         gRPC contract and generated stubs
  orchestrator/    durable delegate() and capability-based agent registry
  cli.py           inspection commands
examples/pipeline/ the three-agent crash recovery demo
docs/              spec notes and design rationale
tests/             unit tests and subprocess integration tests
```

## Tests

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

CI runs both on every push. The crash recovery and pipeline tests use real subprocesses and a real SQLite file, not mocks.

## License

MIT
