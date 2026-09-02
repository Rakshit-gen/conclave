"""A thin gRPC client mirroring `AgentClient`/`JsonRpcAgentClient`'s public
surface. Errors surface as `grpc.aio.AioRpcError` with the status codes
`grpc_server.py` sets (`NOT_FOUND`, `FAILED_PRECONDITION`, `UNAUTHENTICATED`)
rather than being translated into conclave-specific exception types — a
gRPC client should behave like a gRPC client.

No `discover()`/full `AgentCard` fetch here: gRPC's `GetExtendedAgentCard`
intentionally returns a minimal `AgentCardSummary` (see `proto/a2a.proto`'s
header comment), so full-fidelity discovery stays REST-only regardless of
which transport a caller uses for task operations.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import grpc

from .models import Message, StreamResponse, Task, TaskPushNotificationConfig
from .proto import a2a_pb2 as pb
from .proto import a2a_pb2_grpc as pb_grpc
from .proto.convert import from_proto, to_proto


class GrpcAgentClient:
    def __init__(
        self,
        target: str,
        channel: grpc.aio.Channel | None = None,
        auth_headers: dict[str, str] | None = None,
    ):
        self._channel = channel or grpc.aio.insecure_channel(target)
        self._owns_channel = channel is None
        self._stub = pb_grpc.A2AServiceStub(self._channel)
        self._metadata = list((auth_headers or {}).items())

    async def close(self) -> None:
        if self._owns_channel:
            await self._channel.close()

    async def send_message(
        self,
        message: Message,
        push_config: TaskPushNotificationConfig | None = None,
        return_immediately: bool = False,
    ) -> Task:
        configuration = pb.SendMessageConfiguration(return_immediately=return_immediately)
        if push_config is not None:
            configuration.task_push_notification_config.MergeFrom(
                to_proto(push_config, pb.TaskPushNotificationConfig)
            )
        request = pb.SendMessageRequest(
            message=to_proto(message, pb.Message), configuration=configuration
        )
        response = await self._stub.SendMessage(request, metadata=self._metadata)
        return from_proto(response, Task)

    async def stream_message(self, message: Message) -> AsyncIterator[StreamResponse]:
        request = pb.SendMessageRequest(message=to_proto(message, pb.Message))
        async for response in self._stub.SendStreamingMessage(request, metadata=self._metadata):
            yield from_proto(response, StreamResponse)

    async def subscribe_task(self, task_id: str) -> AsyncIterator[StreamResponse]:
        request = pb.SubscribeToTaskRequest(id=task_id)
        async for response in self._stub.SubscribeToTask(request, metadata=self._metadata):
            yield from_proto(response, StreamResponse)

    async def get_task(self, task_id: str) -> Task:
        response = await self._stub.GetTask(pb.GetTaskRequest(id=task_id), metadata=self._metadata)
        return from_proto(response, Task)

    async def list_tasks(self) -> list[Task]:
        response = await self._stub.ListTasks(pb.ListTasksRequest(), metadata=self._metadata)
        return [from_proto(t, Task) for t in response.tasks]

    async def cancel_task(self, task_id: str) -> Task:
        response = await self._stub.CancelTask(
            pb.CancelTaskRequest(id=task_id), metadata=self._metadata
        )
        return from_proto(response, Task)

    async def create_push_notification_config(
        self, task_id: str, config: TaskPushNotificationConfig
    ) -> TaskPushNotificationConfig:
        updated = config.model_copy(update={"task_id": task_id})
        request = to_proto(updated, pb.TaskPushNotificationConfig)
        response = await self._stub.CreateTaskPushNotificationConfig(
            request, metadata=self._metadata
        )
        return from_proto(response, TaskPushNotificationConfig)

    async def get_push_notification_config(
        self, task_id: str, config_id: str
    ) -> TaskPushNotificationConfig:
        request = pb.GetTaskPushNotificationConfigRequest(task_id=task_id, id=config_id)
        response = await self._stub.GetTaskPushNotificationConfig(
            request, metadata=self._metadata
        )
        return from_proto(response, TaskPushNotificationConfig)

    async def list_push_notification_configs(
        self, task_id: str
    ) -> list[TaskPushNotificationConfig]:
        request = pb.ListTaskPushNotificationConfigsRequest(task_id=task_id)
        response = await self._stub.ListTaskPushNotificationConfigs(
            request, metadata=self._metadata
        )
        return [from_proto(c, TaskPushNotificationConfig) for c in response.configs]

    async def delete_push_notification_config(self, task_id: str, config_id: str) -> None:
        request = pb.DeleteTaskPushNotificationConfigRequest(task_id=task_id, id=config_id)
        await self._stub.DeleteTaskPushNotificationConfig(request, metadata=self._metadata)

    async def get_extended_agent_card(self) -> pb.AgentCardSummary:
        return await self._stub.GetExtendedAgentCard(
            pb.GetExtendedAgentCardRequest(), metadata=self._metadata
        )
