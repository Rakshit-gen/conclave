# A2A wire format — reference notes

Pulled directly from the official spec (`specification/a2a.proto`,
[a2aproject/A2A](https://github.com/a2aproject/A2A), protocol v1.0) while
implementing `conclave/a2a/models.py`. Kept here so the mapping from spec to
code is checkable without re-reading the proto.

JSON field names follow standard protobuf JSON mapping: `snake_case` proto
fields become `camelCase` JSON (`context_id` → `contextId`). conclave's
Pydantic models declare the snake_case name with a camelCase alias, so both
`Task(context_id=...)` in Python and `{"contextId": ...}` off the wire work.

## Transport

The spec defines three interchangeable bindings (JSON-RPC, gRPC, HTTP+JSON
REST) with identical semantics, and conclave implements all three — see
"JSON-RPC binding" and "gRPC binding" below for the other two. The REST
route table:

| Operation | REST route |
|---|---|
| Send a message | `POST /message:send` |
| Send a streaming message | `POST /message:stream` (SSE) |
| Get a task | `GET /tasks/{id}` |
| List tasks | `GET /tasks` |
| Cancel a task | `POST /tasks/{id}:cancel` |
| Subscribe to task updates | `GET /tasks/{id}:subscribe` (SSE) |
| Create push notification config | `POST /tasks/{task_id}/pushNotificationConfigs` |
| Get extended agent card | `GET /extendedAgentCard` |

Agent discovery: `GET https://{host}/.well-known/agent-card.json` (RFC 8615).
`AgentInterface.protocol_binding` for this transport is the literal string
`"HTTP+JSON"`.

## Task lifecycle (`TaskState`)

`SUBMITTED → WORKING → {COMPLETED, FAILED, CANCELED, REJECTED}` (terminal),
or `WORKING → {INPUT_REQUIRED, AUTH_REQUIRED}` (interrupted, resumable back
to `WORKING`).

## `Part` is one message, not three

The spec does *not* have separate `TextPart`/`FilePart`/`DataPart` classes —
that was an earlier (pre-v1.0) shape. `Part` is a single message with a
`oneof content`: `text | raw (bytes) | url | data (JSON value)`, plus
`filename` and `media_type`. conclave's `Part` model mirrors the oneof as
mutually-exclusive optional fields with a validator.

## Security schemes

`SecurityScheme`'s full `oneof` (API key, HTTP auth, OAuth2 + all five
flow shapes, OpenID Connect, mTLS) is modeled field-for-field in
`models.py`. Enforcement (`conclave/a2a/auth.py`) only covers
`api_key_security_scheme` (header-located) and `http_auth_security_scheme`
(Bearer) — those are self-contained checks. OAuth2 and OIDC are modeled
but not enforced: validating a real token means talking to a real identity
provider, which is an integration point for whoever deploys the agent,
not something this library should try to *be*.

## Push notifications and `tasks/{id}:subscribe`

Both are real, not modeled-but-unreachable. That required moving task
execution off the request that creates it and onto a background
`asyncio.Task` (`TaskRunner._spawn`), fanning its events out to however
many subscribers (SSE connections, push-notification webhooks) are
attached at the time — otherwise `return_immediately=True` would have
nothing async to return immediately *from*, and `/tasks/{id}:subscribe`
would have no still-running task to attach to.

## JSON-RPC binding

`conclave/a2a/jsonrpc.py` implements all eleven `A2AService` RPCs (spec §9)
as a single `POST /jsonrpc` endpoint on the *same* `AgentServer`/FastAPI
app as the REST binding — same `TaskRunner`, same `TaskStore`, same
`Authenticator`, same push-notification store. A task created over REST is
visible over JSON-RPC on the same server and vice versa, because there's
only ever one runner underneath both; the binding is just which envelope
a request arrives in. Streaming methods (`SendStreamingMessage`,
`SubscribeToTask`) reuse the REST binding's SSE transport, framing one
full JSON-RPC response object per `StreamResponse` instead of the bare
`StreamResponse` REST sends.

Error codes use JSON-RPC 2.0's spec-reserved "server error" range
(-32000 to -32099) for app-level failures (auth, not-found, already-
terminal) and the standard codes for framing failures.

## gRPC binding

`conclave/a2a/proto/a2a.proto` is conclave's own stripped copy of the
spec's gRPC contract, not a checkout of the official one — it mirrors the
same message/field names and numbers but drops the `google.api.http` /
`google.api.field_behavior` HTTP-transcoding annotations, which need the
googleapis common-protos repo that plain `grpcio-tools` doesn't bundle.
Those annotations exist so the official binding can *generate* a REST
surface from the gRPC one; conclave's REST binding is hand-written
separately, so it doesn't need them. `GetExtendedAgentCard` returns a
deliberately minimal `AgentCardSummary` over gRPC — full Agent Card
fidelity (skills, capabilities, security schemes) is only ever served over
REST's well-known URI, regardless of which transport handles tasks.

`conclave/a2a/grpc_server.py`'s `add_to_server(agent_server, server)`
mounts a servicer on an `agent_server`'s *existing* `TaskRunner`, push
store, and `Authenticator` — the same state its REST/JSON-RPC routes use,
not a separate copy. Translating between conclave's Pydantic wire models
and the generated protobuf classes doesn't need hand-written per-field
mapping code: `WireModel` already dumps camelCase field names, `TASK_STATE_*`
enum strings, and RFC3339 timestamps, because that's protobuf's own JSON
mapping convention — so `conclave/a2a/proto/convert.py` just round-trips
through `google.protobuf.json_format.ParseDict`/`MessageToDict`, with
`always_print_fields_with_no_presence=True` on the way back (otherwise a
proto3 scalar left at its zero value, like an empty `context_id`, is
dropped from the JSON entirely — and some `WireModel` fields, like
`TaskStatusUpdateEvent.context_id`, are required rather than optional).

`grpc.aio.ServicerContext.abort()` is itself a coroutine, unlike the sync
grpc API's `context.abort()` — every call site awaits it, since an
un-awaited `abort()` just constructs a coroutine object and returns
normally instead of terminating the RPC (caught by
`test_grpc_auth_is_enforced` failing with "DID NOT RAISE" on the first
pass, not by inspection).

`grpcio`/`protobuf` are an optional `grpc` extra
(`pip install -e ".[grpc]"`), not a core dependency — `conclave/a2a/__init__.py`
only exposes `GrpcAgentClient`/`add_to_server`/`build_server` if the import
succeeds, so importing `conclave.a2a` at all doesn't require a protobuf
toolchain unless the gRPC binding is actually used.
