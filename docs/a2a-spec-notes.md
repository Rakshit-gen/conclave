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

## Scoped out for now

The JSON-RPC and gRPC transport bindings (REST is spec-complete on its
own — all three carry identical semantics per the spec, not a fallback
tier). gRPC additionally needs a protobuf toolchain this library doesn't
otherwise depend on.
