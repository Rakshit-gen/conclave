# conclave

A durable multi-agent orchestrator, built from scratch — no LangGraph, no
Temporal SDK, no A2A SDK underneath. Two things live here:

1. **A durable execution core** (`conclave/core`) — event-sourced workflow
   state, deterministic replay, crash recovery, and resumable
   human-in-the-loop approval gates. Kill the process mid-workflow and a
   fresh one, pointed at the same event log, picks up exactly where it left
   off — because nothing here ever trusted memory in the first place.
2. **An A2A (Agent2Agent) protocol implementation** (`conclave/a2a`) —
   Agent Card discovery, the real task lifecycle, and the HTTP+JSON REST
   wire binding from [the official spec](https://github.com/a2aproject/A2A),
   not a mocked-up stand-in for it. See `docs/a2a-spec-notes.md` for the
   exact field-by-field mapping.

`conclave/orchestrator` sits on top of both: a workflow can durably delegate
a task to a remote agent it's never talked to before, suspend for a human's
approval across a crash and restart, and keep going — without ever
re-sending a message an agent already acted on.

## How the durable core actually works

There's no sandboxed workflow language runtime here. Instead: a workflow is
a plain async function, and the **entire function is re-run from the top on
every drive**. Every side-effecting call goes through `step()` or
`wait_for_signal()`, which check a cursor into the recorded event log before
doing anything real:

- Already-recorded steps return their stored result instantly — the real
  side effect (an agent call, an LLM call, whatever) never happens twice.
- The first call with nothing recorded yet is the live edge of history — it
  actually runs, and its outcome is durably persisted before the function
  is allowed to continue.

This means workflow code has to be deterministic (same inputs → same
sequence of `step()` calls), exactly like Temporal's own constraint, and for
the same reason. `get_version()` is the documented escape hatch for
changing a workflow's step sequence across a deploy without breaking runs
already in flight.

The module docstrings in `conclave/core/execution.py` and
`conclave/core/runtime.py` go deeper on the replay model — written as
design rationale while building it, not after-the-fact commentary.

## The demo: a three-agent pipeline that survives a real kill -9

`examples/pipeline/` runs Researcher → Writer → **human approval gate** →
Reviewer, with each agent a genuinely separate OS process serving A2A over
a real localhost port — not three functions in one process pretending to
be agents.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m examples.pipeline.run start "distributed consensus"
python -m examples.pipeline.run status    # -> suspended, waiting on approve_draft
python -m examples.pipeline.run approve   # -> completed, prints the final draft
python -m examples.pipeline.run stop      # stop the three agent processes
```

To see crash recovery for real, not just take it on faith:

```bash
python -m examples.pipeline.run start "distributed consensus" --crash-after write
# exits via os._exit(137) right after "write" durably completes —
# a real simulated kill -9 mid-workflow. echo $? -> 137

python -m examples.pipeline.run resume
# -> suspended, waiting on approve_draft. Replayed "research" and "write"
#    from the event log instead of re-delegating to those agents, then
#    genuinely reached the suspension point the crashed run never got to.

python -m examples.pipeline.run approve
# -> completed. research and write still never ran twice.
```

`tests/examples/test_pipeline_demo.py` runs this exact sequence as a real
subprocess-driven integration test, so it can't silently rot.

Each demo agent's "intelligence" is a plain deterministic string transform,
not a model call — the demo exists to prove the orchestration layer, and a
canned LLM call would add cost and flakiness without making any of that
more convincing. Swap the handler in `examples/pipeline/agents.py` for a
real model call and nothing else in the package needs to change.

## Inspecting a workflow

```bash
conclave status <workflow-id> --db examples/pipeline/.run/conclave.db
conclave history <workflow-id> --db examples/pipeline/.run/conclave.db
conclave list --db examples/pipeline/.run/conclave.db
conclave agent-card http://127.0.0.1:9001
```

`history` prints every event actually recorded for a workflow — this is how
the execution engine gets reviewed as it's built: what's really in the log,
not what the code claims is in it.

## Layout

```
conclave/
  core/           event-sourced replay engine, SQLite-backed event store
  a2a/            protocol wire models, HTTP+JSON REST server + client
  orchestrator/   durable delegate(), capability-based agent registry
  cli.py          workflow/agent inspection commands
examples/pipeline/  the three-agent crash-recoverable demo
docs/               spec notes and design rationale
tests/              unit + real-subprocess integration tests
```

## Running the tests

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

CI runs both on every push (`.github/workflows/ci.yml`).

## Status

Phase 1 complete: durable core, A2A REST binding, orchestrator, CLI, and
the crash-recoverable demo, all covered by tests that exercise real
subprocesses and a real SQLite file — not mocks standing in for them.

Not yet built, and not silently pretended to be: the JSON-RPC and gRPC A2A
bindings (REST is spec-complete on its own), push notifications, and the
OAuth2/OIDC/mTLS security-scheme flows (see the "Scoped out for now"
section of `docs/a2a-spec-notes.md`).

## License

MIT
