from .auth import (
    ApiKeyAuthenticator,
    AuthenticationError,
    Authenticator,
    BearerAuthenticator,
    NoAuth,
)
from .client import AgentClient, api_key_headers, bearer_headers
from .jsonrpc_client import JsonRpcAgentClient, JsonRpcError
from .push import (
    HttpPushNotifier,
    InMemoryPushNotificationStore,
    PushNotificationStore,
    PushNotifier,
)
from .runner import AgentHandler, TaskRunner
from .server import AgentServer
from .tasks import InMemoryTaskStore, TaskStore

try:
    from .grpc_client import GrpcAgentClient
    from .grpc_server import add_to_server, build_server
except ImportError:  # grpcio is an optional extra ([grpc]), not a core dependency
    GrpcAgentClient = None  # type: ignore[assignment]
    add_to_server = None  # type: ignore[assignment]
    build_server = None  # type: ignore[assignment]

__all__ = [
    "AgentClient",
    "JsonRpcAgentClient",
    "JsonRpcError",
    "AgentServer",
    "AgentHandler",
    "TaskRunner",
    "TaskStore",
    "InMemoryTaskStore",
    "PushNotificationStore",
    "InMemoryPushNotificationStore",
    "PushNotifier",
    "HttpPushNotifier",
    "Authenticator",
    "AuthenticationError",
    "NoAuth",
    "ApiKeyAuthenticator",
    "BearerAuthenticator",
    "api_key_headers",
    "bearer_headers",
    "GrpcAgentClient",
    "add_to_server",
    "build_server",
]
