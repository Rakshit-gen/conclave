"""Generic Pydantic <-> protobuf JSON bridge for the gRPC binding.

conclave's `WireModel` (models.py) already emits protobuf's own JSON
mapping — camelCase field names, `TASK_STATE_*` enum strings, RFC3339
timestamps — because that's what the REST/JSON-RPC bindings are built on
too (see docs/a2a-spec-notes.md). That means translating to/from the
generated proto classes is exactly what `google.protobuf.json_format` is
for; no hand-written per-message field mapping needed.
"""

from __future__ import annotations

from typing import TypeVar

from google.protobuf import json_format
from google.protobuf.message import Message as ProtoMessage
from pydantic import BaseModel

_M = TypeVar("_M", bound=ProtoMessage)
_P = TypeVar("_P", bound=BaseModel)


def to_proto(model: BaseModel, proto_cls: type[_M]) -> _M:
    msg = proto_cls()
    json_format.ParseDict(
        model.model_dump(mode="json", by_alias=True, exclude_none=True),
        msg,
        ignore_unknown_fields=True,
    )
    return msg


def from_proto(msg: ProtoMessage, model_cls: type[_P]) -> _P:
    # `always_print_fields_with_no_presence` is needed because a proto3
    # scalar left at its zero value (e.g. `context_id: ""`) is otherwise
    # dropped entirely, and some WireModel fields (like
    # TaskStatusUpdateEvent.context_id) are required rather than optional.
    return model_cls.model_validate(
        json_format.MessageToDict(
            msg, preserving_proto_field_name=False, always_print_fields_with_no_presence=True
        )
    )
