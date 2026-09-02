"""gRPC binding (spec §9): the third A2A transport, alongside REST and
JSON-RPC. Same `TaskRunner`, same push-notification store, same
`Authenticator` as whichever `AgentServer` it's attached to — `add_to_server`
takes the `AgentServer` itself so all three bindings share identical state
when mounted together, the same way the JSON-RPC binding shares REST's.

`conclave/a2a/proto/a2a.proto` is conclave's own stripped copy of the
spec's gRPC contract (no `google.api.*` HTTP-transcoding annotations —
those exist because the official binding *generates* its REST surface from
them, but conclave's REST binding is hand-written separately, so it
doesn't need them). `GetExtendedAgentCard` here returns a deliberately
minimal `AgentCardSummary`; full Agent Card fidelity is only ever served
over REST's well-known URI, regardless of which transport handles tasks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import grpc

from .auth import AuthenticationError, Authenticator
from .models import AgentCard, Message, Task, TaskPushNotificationConfig
from .proto import a2a_pb2 as pb
from .proto import a2a_pb2_grpc as pb_grpc
from .proto.convert import from_proto, to_proto
from .push import PushNotificationStore
from .runner import TaskAlreadyTerminalError, TaskNotFoundError, TaskRunner


class A2AGrpcServicer(pb_grpc.A2AServiceServicer):
    def __init__(
        self,
        card: AgentCard,
        runner: TaskRunner,
        push_configs: PushNotificationStore,
        authenticator: Authenticator,
    ):
        self.card = card
        self.runner = runner
        self.push_configs = push_configs
        self.authenticator = authenticator

    async def _require_auth(self, context: grpc.aio.ServicerContext) -> None:
        headers = dict(context.invocation_metadata() or ())
        try:
            self.authenticator.authenticate(headers)
        except AuthenticationError as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))

    async def SendMessage(self, request: pb.SendMessageRequest, context) -> pb.Task:
        await self._require_auth(context)
        message = from_proto(request.message, Message)
        push_config, return_immediately = _read_configuration(request)
        task = await self.runner.run(
            message, push_config=push_config, return_immediately=return_immediately
        )
        return to_proto(task, pb.Task)

    async def SendStreamingMessage(
        self, request: pb.SendMessageRequest, context
    ) -> AsyncIterator[pb.StreamResponse]:
        await self._require_auth(context)
        message = from_proto(request.message, Message)
        async for event in self.runner.stream(message):
            yield to_proto(event, pb.StreamResponse)

    async def GetTask(self, request: pb.GetTaskRequest, context) -> pb.Task:
        await self._require_auth(context)
        task = self.runner.get(request.id)
        if task is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"no such task {request.id!r}")
        return to_proto(task, pb.Task)

    async def ListTasks(
        self, request: pb.ListTasksRequest, context
    ) -> pb.ListTasksResponse:
        await self._require_auth(context)
        tasks: list[Task] = self.runner.list()
        return pb.ListTasksResponse(tasks=[to_proto(t, pb.Task) for t in tasks])

    async def CancelTask(self, request: pb.CancelTaskRequest, context) -> pb.Task:
        await self._require_auth(context)
        task = self.runner.cancel(request.id)
        if task is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"no such task {request.id!r}")
        return to_proto(task, pb.Task)

    async def SubscribeToTask(
        self, request: pb.SubscribeToTaskRequest, context
    ) -> AsyncIterator[pb.StreamResponse]:
        await self._require_auth(context)
        try:
            async for event in self.runner.subscribe(request.id):
                yield to_proto(event, pb.StreamResponse)
        except TaskNotFoundError:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"no such task {request.id!r}")
        except TaskAlreadyTerminalError:
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, f"task {request.id!r} is already terminal"
            )

    async def CreateTaskPushNotificationConfig(
        self, request: pb.TaskPushNotificationConfig, context
    ) -> pb.TaskPushNotificationConfig:
        await self._require_auth(context)
        config = from_proto(request, TaskPushNotificationConfig)
        self.push_configs.put(config.task_id or "", config)
        return to_proto(config, pb.TaskPushNotificationConfig)

    async def GetTaskPushNotificationConfig(
        self, request: pb.GetTaskPushNotificationConfigRequest, context
    ) -> pb.TaskPushNotificationConfig:
        await self._require_auth(context)
        config = self.push_configs.get(request.task_id, request.id)
        if config is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, "no such push notification config")
        return to_proto(config, pb.TaskPushNotificationConfig)

    async def ListTaskPushNotificationConfigs(
        self, request: pb.ListTaskPushNotificationConfigsRequest, context
    ) -> pb.ListTaskPushNotificationConfigsResponse:
        await self._require_auth(context)
        configs = self.push_configs.for_task(request.task_id)
        return pb.ListTaskPushNotificationConfigsResponse(
            configs=[to_proto(c, pb.TaskPushNotificationConfig) for c in configs]
        )

    async def DeleteTaskPushNotificationConfig(
        self, request: pb.DeleteTaskPushNotificationConfigRequest, context
    ):
        from google.protobuf import empty_pb2

        await self._require_auth(context)
        if not self.push_configs.delete(request.task_id, request.id):
            await context.abort(grpc.StatusCode.NOT_FOUND, "no such push notification config")
        return empty_pb2.Empty()

    async def GetExtendedAgentCard(
        self, request: pb.GetExtendedAgentCardRequest, context
    ) -> pb.AgentCardSummary:
        await self._require_auth(context)
        return pb.AgentCardSummary(
            name=self.card.name,
            description=self.card.description,
            version=self.card.version,
            documentation_url=self.card.documentation_url or "",
        )


def _read_configuration(
    request: pb.SendMessageRequest,
) -> tuple[TaskPushNotificationConfig | None, bool]:
    if not request.HasField("configuration"):
        return None, False
    configuration = request.configuration
    push_config = None
    if configuration.HasField("task_push_notification_config"):
        push_config = from_proto(
            configuration.task_push_notification_config, TaskPushNotificationConfig
        )
    return push_config, configuration.return_immediately


def add_to_server(agent_server, server: grpc.aio.Server) -> None:
    """Mounts `agent_server`'s existing `TaskRunner`/push store/authenticator
    onto `server` — the same underlying state the REST/JSON-RPC bindings on
    `agent_server.app` use, not a separate copy of it.
    """
    servicer = A2AGrpcServicer(
        agent_server.card,
        agent_server.runner,
        agent_server.push_configs,
        agent_server.authenticator,
    )
    pb_grpc.add_A2AServiceServicer_to_server(servicer, server)


def build_server(agent_server, address: str = "[::]:50051") -> grpc.aio.Server:
    server = grpc.aio.server()
    add_to_server(agent_server, server)
    server.add_insecure_port(address)
    return server


__all__ = ["A2AGrpcServicer", "add_to_server", "build_server"]
