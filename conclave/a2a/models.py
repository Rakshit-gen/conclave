"""Wire types for the A2A (Agent2Agent) protocol, v1.0.

Field shapes follow `specification/a2a.proto` in github.com/a2aproject/A2A
directly — see docs/a2a-spec-notes.md for the mapping. Every model accepts
both its Python (snake_case) field name and the camelCase alias protobuf's
JSON mapping produces on the wire.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _new_id() -> str:
    return str(uuid.uuid4())


def _camel(snake: str) -> str:
    """`context_id` -> `contextId`, matching protobuf's JSON mapping."""
    head, *tail = snake.split("_")
    return head + "".join(word.capitalize() for word in tail)


class WireModel(BaseModel):
    """Base for A2A types: camelCase-on-the-wire, snake_case in Python."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_camel)


class Role(StrEnum):
    UNSPECIFIED = "ROLE_UNSPECIFIED"
    USER = "ROLE_USER"
    AGENT = "ROLE_AGENT"


class TaskState(StrEnum):
    UNSPECIFIED = "TASK_STATE_UNSPECIFIED"
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    CANCELED = "TASK_STATE_CANCELED"
    REJECTED = "TASK_STATE_REJECTED"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    AUTH_REQUIRED = "TASK_STATE_AUTH_REQUIRED"

    @property
    def is_terminal(self) -> bool:
        return self in (
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELED,
            TaskState.REJECTED,
        )

    @property
    def is_interrupted(self) -> bool:
        return self in (TaskState.INPUT_REQUIRED, TaskState.AUTH_REQUIRED)


class Part(WireModel):
    """A `oneof content` (text | raw | url | data) plus shared metadata."""

    text: str | None = None
    raw: bytes | None = None
    url: str | None = None
    data: Any | None = None
    metadata: dict[str, Any] | None = None
    filename: str | None = None
    media_type: str | None = None

    @model_validator(mode="after")
    def _exactly_one_content_field(self) -> Part:
        set_fields = [f for f in ("text", "raw", "url", "data") if getattr(self, f) is not None]
        if len(set_fields) != 1:
            raise ValueError(
                f"Part must set exactly one of text/raw/url/data, got {set_fields or 'none'}"
            )
        return self

    @classmethod
    def of_text(cls, text: str) -> Part:
        return cls(text=text)

    @classmethod
    def of_data(cls, data: Any) -> Part:
        return cls(data=data)


class TaskStatus(WireModel):
    state: TaskState
    message: Message | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Message(WireModel):
    message_id: str = Field(default_factory=_new_id)
    context_id: str | None = None
    task_id: str | None = None
    role: Role
    parts: list[Part]
    metadata: dict[str, Any] | None = None
    extensions: list[str] = Field(default_factory=list)
    reference_task_ids: list[str] = Field(default_factory=list)


class Artifact(WireModel):
    artifact_id: str = Field(default_factory=_new_id)
    name: str | None = None
    description: str | None = None
    parts: list[Part]
    metadata: dict[str, Any] | None = None


class Task(WireModel):
    id: str = Field(default_factory=_new_id)
    context_id: str | None = None
    status: TaskStatus
    artifacts: list[Artifact] = Field(default_factory=list)
    history: list[Message] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class TaskStatusUpdateEvent(WireModel):
    task_id: str
    context_id: str
    status: TaskStatus
    metadata: dict[str, Any] | None = None


class TaskArtifactUpdateEvent(WireModel):
    task_id: str
    context_id: str
    artifact: Artifact
    append: bool = False
    last_chunk: bool = False
    metadata: dict[str, Any] | None = None


class StreamResponse(WireModel):
    """One SSE frame from `message:stream` or `tasks/{id}:subscribe`."""

    task: Task | None = None
    status_update: TaskStatusUpdateEvent | None = None
    artifact_update: TaskArtifactUpdateEvent | None = None


class AuthenticationInfo(WireModel):
    scheme: str
    credentials: str | None = None


class TaskPushNotificationConfig(WireModel):
    tenant: str | None = None
    id: str = Field(default_factory=_new_id)
    task_id: str | None = None
    url: str
    token: str | None = None
    authentication: AuthenticationInfo | None = None


class AgentProvider(WireModel):
    url: str
    organization: str


class AgentExtension(WireModel):
    uri: str
    description: str | None = None
    required: bool = False
    params: dict[str, Any] | None = None


class AgentCapabilities(WireModel):
    streaming: bool = False
    push_notifications: bool = False
    extensions: list[AgentExtension] = Field(default_factory=list)
    extended_agent_card: bool = False


class StringList(WireModel):
    # Named `values` in Python (a field literally named `list` shadows the
    # builtin in its own annotation) but still `list` on the wire, matching
    # the proto's `repeated string list = 1`.
    values: list[str] = Field(default_factory=list, alias="list")


class SecurityRequirement(WireModel):
    schemes: dict[str, StringList] = Field(default_factory=dict)


class AgentSkill(WireModel):
    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    input_modes: list[str] = Field(default_factory=list)
    output_modes: list[str] = Field(default_factory=list)
    security_requirements: list[SecurityRequirement] = Field(default_factory=list)


class AgentInterface(WireModel):
    url: str
    protocol_binding: str = "HTTP+JSON"
    tenant: str | None = None
    protocol_version: str = "1.0"


class APIKeySecurityScheme(WireModel):
    description: str | None = None
    location: str  # "query" | "header" | "cookie"
    name: str


class HTTPAuthSecurityScheme(WireModel):
    description: str | None = None
    scheme: str  # IANA HTTP auth scheme name, e.g. "Bearer", "Basic"
    bearer_format: str | None = None


class AuthorizationCodeOAuthFlow(WireModel):
    authorization_url: str
    token_url: str
    refresh_url: str | None = None
    scopes: dict[str, str] = Field(default_factory=dict)
    pkce_required: bool = False


class ClientCredentialsOAuthFlow(WireModel):
    token_url: str
    refresh_url: str | None = None
    scopes: dict[str, str] = Field(default_factory=dict)


class ImplicitOAuthFlow(WireModel):
    """Deprecated by the spec itself (use authorization_code + PKCE) — modeled for completeness."""

    authorization_url: str | None = None
    refresh_url: str | None = None
    scopes: dict[str, str] = Field(default_factory=dict)


class PasswordOAuthFlow(WireModel):
    """Deprecated by the spec itself (use authorization_code + PKCE, or device_code)."""

    token_url: str | None = None
    refresh_url: str | None = None
    scopes: dict[str, str] = Field(default_factory=dict)


class DeviceCodeOAuthFlow(WireModel):
    device_authorization_url: str
    token_url: str
    refresh_url: str | None = None
    scopes: dict[str, str] = Field(default_factory=dict)


class OAuthFlows(WireModel):
    """`oneof flow` — exactly one of these should be set, mirroring `Part`."""

    authorization_code: AuthorizationCodeOAuthFlow | None = None
    client_credentials: ClientCredentialsOAuthFlow | None = None
    implicit: ImplicitOAuthFlow | None = None
    password: PasswordOAuthFlow | None = None
    device_code: DeviceCodeOAuthFlow | None = None


class OAuth2SecurityScheme(WireModel):
    description: str | None = None
    flows: OAuthFlows
    oauth2_metadata_url: str | None = None


class OpenIdConnectSecurityScheme(WireModel):
    description: str | None = None
    open_id_connect_url: str


class MutualTlsSecurityScheme(WireModel):
    description: str | None = None


class SecurityScheme(WireModel):
    """`oneof scheme` (spec §4.5) — exactly one of these five is set.

    Enforcement only exists for `api_key_security_scheme` and
    `http_auth_security_scheme` (see `conclave/a2a/auth.py`) — the OAuth2/
    OIDC/mTLS shapes are modeled field-for-field but validating a real
    token means talking to a real identity provider, which is an
    integration point for whoever deploys the agent, not something a
    protocol library should try to *be*.
    """

    api_key_security_scheme: APIKeySecurityScheme | None = None
    http_auth_security_scheme: HTTPAuthSecurityScheme | None = None
    oauth2_security_scheme: OAuth2SecurityScheme | None = None
    open_id_connect_security_scheme: OpenIdConnectSecurityScheme | None = None
    mtls_security_scheme: MutualTlsSecurityScheme | None = None


class AgentCard(WireModel):
    name: str
    description: str
    supported_interfaces: list[AgentInterface]
    provider: AgentProvider | None = None
    version: str = "0.1.0"
    documentation_url: str | None = None
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    security_schemes: dict[str, SecurityScheme] = Field(default_factory=dict)
    security_requirements: list[SecurityRequirement] = Field(default_factory=list)
    default_input_modes: list[str] = Field(default_factory=lambda: ["text/plain"])
    default_output_modes: list[str] = Field(default_factory=lambda: ["text/plain"])
    skills: list[AgentSkill] = Field(default_factory=list)
    icon_url: str | None = None


class SendMessageConfiguration(WireModel):
    accepted_output_modes: list[str] = Field(default_factory=list)
    task_push_notification_config: TaskPushNotificationConfig | None = None
    history_length: int | None = None
    return_immediately: bool = False


class SendMessageRequest(WireModel):
    message: Message
    configuration: SendMessageConfiguration | None = None


class SendMessageResponse(WireModel):
    task: Task | None = None
    message: Message | None = None


class ListTasksResponse(WireModel):
    tasks: list[Task]
    next_page_token: str | None = None
