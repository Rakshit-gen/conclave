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
REST) with identical semantics. conclave implements the **HTTP+JSON REST**
binding — it's the one that maps onto FastAPI/httpx without a protobuf
toolchain, and the spec treats it as a first-class binding, not a fallback.

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

## Scoped out for now

`SecurityScheme`'s OAuth2/OpenID/mTLS sub-messages are modeled only down to
the discriminator — conclave's demo agents run as unauthenticated local
processes, so the flow-specific fields (`AuthorizationCodeOAuthFlow`, etc.)
aren't exercised. Add them when an example actually needs an authenticated
agent.
