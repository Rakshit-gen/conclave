import datetime

from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Role(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ROLE_UNSPECIFIED: _ClassVar[Role]
    ROLE_USER: _ClassVar[Role]
    ROLE_AGENT: _ClassVar[Role]

class TaskState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TASK_STATE_UNSPECIFIED: _ClassVar[TaskState]
    TASK_STATE_SUBMITTED: _ClassVar[TaskState]
    TASK_STATE_WORKING: _ClassVar[TaskState]
    TASK_STATE_COMPLETED: _ClassVar[TaskState]
    TASK_STATE_FAILED: _ClassVar[TaskState]
    TASK_STATE_CANCELED: _ClassVar[TaskState]
    TASK_STATE_INPUT_REQUIRED: _ClassVar[TaskState]
    TASK_STATE_REJECTED: _ClassVar[TaskState]
    TASK_STATE_AUTH_REQUIRED: _ClassVar[TaskState]
ROLE_UNSPECIFIED: Role
ROLE_USER: Role
ROLE_AGENT: Role
TASK_STATE_UNSPECIFIED: TaskState
TASK_STATE_SUBMITTED: TaskState
TASK_STATE_WORKING: TaskState
TASK_STATE_COMPLETED: TaskState
TASK_STATE_FAILED: TaskState
TASK_STATE_CANCELED: TaskState
TASK_STATE_INPUT_REQUIRED: TaskState
TASK_STATE_REJECTED: TaskState
TASK_STATE_AUTH_REQUIRED: TaskState

class Part(_message.Message):
    __slots__ = ("text", "raw", "url", "data", "metadata", "filename", "media_type")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    RAW_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    FILENAME_FIELD_NUMBER: _ClassVar[int]
    MEDIA_TYPE_FIELD_NUMBER: _ClassVar[int]
    text: str
    raw: bytes
    url: str
    data: _struct_pb2.Value
    metadata: _struct_pb2.Struct
    filename: str
    media_type: str
    def __init__(self, text: _Optional[str] = ..., raw: _Optional[bytes] = ..., url: _Optional[str] = ..., data: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ..., metadata: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., filename: _Optional[str] = ..., media_type: _Optional[str] = ...) -> None: ...

class Message(_message.Message):
    __slots__ = ("message_id", "context_id", "task_id", "role", "parts", "metadata", "extensions", "reference_task_ids")
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    PARTS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    EXTENSIONS_FIELD_NUMBER: _ClassVar[int]
    REFERENCE_TASK_IDS_FIELD_NUMBER: _ClassVar[int]
    message_id: str
    context_id: str
    task_id: str
    role: Role
    parts: _containers.RepeatedCompositeFieldContainer[Part]
    metadata: _struct_pb2.Struct
    extensions: _containers.RepeatedScalarFieldContainer[str]
    reference_task_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, message_id: _Optional[str] = ..., context_id: _Optional[str] = ..., task_id: _Optional[str] = ..., role: _Optional[_Union[Role, str]] = ..., parts: _Optional[_Iterable[_Union[Part, _Mapping]]] = ..., metadata: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., extensions: _Optional[_Iterable[str]] = ..., reference_task_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class Artifact(_message.Message):
    __slots__ = ("artifact_id", "name", "description", "parts", "metadata")
    ARTIFACT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    PARTS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    artifact_id: str
    name: str
    description: str
    parts: _containers.RepeatedCompositeFieldContainer[Part]
    metadata: _struct_pb2.Struct
    def __init__(self, artifact_id: _Optional[str] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., parts: _Optional[_Iterable[_Union[Part, _Mapping]]] = ..., metadata: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class TaskStatus(_message.Message):
    __slots__ = ("state", "message", "timestamp")
    STATE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    state: TaskState
    message: Message
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, state: _Optional[_Union[TaskState, str]] = ..., message: _Optional[_Union[Message, _Mapping]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class Task(_message.Message):
    __slots__ = ("id", "context_id", "status", "artifacts", "history", "metadata")
    ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ARTIFACTS_FIELD_NUMBER: _ClassVar[int]
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    id: str
    context_id: str
    status: TaskStatus
    artifacts: _containers.RepeatedCompositeFieldContainer[Artifact]
    history: _containers.RepeatedCompositeFieldContainer[Message]
    metadata: _struct_pb2.Struct
    def __init__(self, id: _Optional[str] = ..., context_id: _Optional[str] = ..., status: _Optional[_Union[TaskStatus, _Mapping]] = ..., artifacts: _Optional[_Iterable[_Union[Artifact, _Mapping]]] = ..., history: _Optional[_Iterable[_Union[Message, _Mapping]]] = ..., metadata: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class TaskStatusUpdateEvent(_message.Message):
    __slots__ = ("task_id", "context_id", "status")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    context_id: str
    status: TaskStatus
    def __init__(self, task_id: _Optional[str] = ..., context_id: _Optional[str] = ..., status: _Optional[_Union[TaskStatus, _Mapping]] = ...) -> None: ...

class TaskArtifactUpdateEvent(_message.Message):
    __slots__ = ("task_id", "context_id", "artifact", "append", "last_chunk")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_ID_FIELD_NUMBER: _ClassVar[int]
    ARTIFACT_FIELD_NUMBER: _ClassVar[int]
    APPEND_FIELD_NUMBER: _ClassVar[int]
    LAST_CHUNK_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    context_id: str
    artifact: Artifact
    append: bool
    last_chunk: bool
    def __init__(self, task_id: _Optional[str] = ..., context_id: _Optional[str] = ..., artifact: _Optional[_Union[Artifact, _Mapping]] = ..., append: _Optional[bool] = ..., last_chunk: _Optional[bool] = ...) -> None: ...

class StreamResponse(_message.Message):
    __slots__ = ("task", "status_update", "artifact_update")
    TASK_FIELD_NUMBER: _ClassVar[int]
    STATUS_UPDATE_FIELD_NUMBER: _ClassVar[int]
    ARTIFACT_UPDATE_FIELD_NUMBER: _ClassVar[int]
    task: Task
    status_update: TaskStatusUpdateEvent
    artifact_update: TaskArtifactUpdateEvent
    def __init__(self, task: _Optional[_Union[Task, _Mapping]] = ..., status_update: _Optional[_Union[TaskStatusUpdateEvent, _Mapping]] = ..., artifact_update: _Optional[_Union[TaskArtifactUpdateEvent, _Mapping]] = ...) -> None: ...

class AuthenticationInfo(_message.Message):
    __slots__ = ("scheme", "credentials")
    SCHEME_FIELD_NUMBER: _ClassVar[int]
    CREDENTIALS_FIELD_NUMBER: _ClassVar[int]
    scheme: str
    credentials: str
    def __init__(self, scheme: _Optional[str] = ..., credentials: _Optional[str] = ...) -> None: ...

class TaskPushNotificationConfig(_message.Message):
    __slots__ = ("id", "task_id", "url", "token", "authentication")
    ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    AUTHENTICATION_FIELD_NUMBER: _ClassVar[int]
    id: str
    task_id: str
    url: str
    token: str
    authentication: AuthenticationInfo
    def __init__(self, id: _Optional[str] = ..., task_id: _Optional[str] = ..., url: _Optional[str] = ..., token: _Optional[str] = ..., authentication: _Optional[_Union[AuthenticationInfo, _Mapping]] = ...) -> None: ...

class SendMessageConfiguration(_message.Message):
    __slots__ = ("accepted_output_modes", "task_push_notification_config", "history_length", "return_immediately")
    ACCEPTED_OUTPUT_MODES_FIELD_NUMBER: _ClassVar[int]
    TASK_PUSH_NOTIFICATION_CONFIG_FIELD_NUMBER: _ClassVar[int]
    HISTORY_LENGTH_FIELD_NUMBER: _ClassVar[int]
    RETURN_IMMEDIATELY_FIELD_NUMBER: _ClassVar[int]
    accepted_output_modes: _containers.RepeatedScalarFieldContainer[str]
    task_push_notification_config: TaskPushNotificationConfig
    history_length: int
    return_immediately: bool
    def __init__(self, accepted_output_modes: _Optional[_Iterable[str]] = ..., task_push_notification_config: _Optional[_Union[TaskPushNotificationConfig, _Mapping]] = ..., history_length: _Optional[int] = ..., return_immediately: _Optional[bool] = ...) -> None: ...

class SendMessageRequest(_message.Message):
    __slots__ = ("message", "configuration")
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    CONFIGURATION_FIELD_NUMBER: _ClassVar[int]
    message: Message
    configuration: SendMessageConfiguration
    def __init__(self, message: _Optional[_Union[Message, _Mapping]] = ..., configuration: _Optional[_Union[SendMessageConfiguration, _Mapping]] = ...) -> None: ...

class GetTaskRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class ListTasksRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListTasksResponse(_message.Message):
    __slots__ = ("tasks",)
    TASKS_FIELD_NUMBER: _ClassVar[int]
    tasks: _containers.RepeatedCompositeFieldContainer[Task]
    def __init__(self, tasks: _Optional[_Iterable[_Union[Task, _Mapping]]] = ...) -> None: ...

class CancelTaskRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class SubscribeToTaskRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class GetTaskPushNotificationConfigRequest(_message.Message):
    __slots__ = ("task_id", "id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    id: str
    def __init__(self, task_id: _Optional[str] = ..., id: _Optional[str] = ...) -> None: ...

class ListTaskPushNotificationConfigsRequest(_message.Message):
    __slots__ = ("task_id",)
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    def __init__(self, task_id: _Optional[str] = ...) -> None: ...

class ListTaskPushNotificationConfigsResponse(_message.Message):
    __slots__ = ("configs",)
    CONFIGS_FIELD_NUMBER: _ClassVar[int]
    configs: _containers.RepeatedCompositeFieldContainer[TaskPushNotificationConfig]
    def __init__(self, configs: _Optional[_Iterable[_Union[TaskPushNotificationConfig, _Mapping]]] = ...) -> None: ...

class DeleteTaskPushNotificationConfigRequest(_message.Message):
    __slots__ = ("task_id", "id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    id: str
    def __init__(self, task_id: _Optional[str] = ..., id: _Optional[str] = ...) -> None: ...

class GetExtendedAgentCardRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AgentCardSummary(_message.Message):
    __slots__ = ("name", "description", "version", "documentation_url")
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    DOCUMENTATION_URL_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    version: str
    documentation_url: str
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., version: _Optional[str] = ..., documentation_url: _Optional[str] = ...) -> None: ...
