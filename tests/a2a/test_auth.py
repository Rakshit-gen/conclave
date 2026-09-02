import httpx
import pytest

from conclave.a2a import (
    AgentServer,
    ApiKeyAuthenticator,
    BearerAuthenticator,
    api_key_headers,
    bearer_headers,
)
from conclave.a2a.models import APIKeySecurityScheme, HTTPAuthSecurityScheme, Message, Part, Role

from .test_server_client import client_for, make_card, uppercase_handler


async def test_unauthenticated_request_is_rejected_with_401_when_api_key_required():
    scheme = APIKeySecurityScheme(location="header", name="X-API-Key")
    authenticator = ApiKeyAuthenticator(scheme, valid_keys={"secret-key"})
    server = AgentServer(make_card(), uppercase_handler, authenticator=authenticator)
    client = client_for(server)

    message = Message(role=Role.USER, parts=[Part.of_text("hi")])
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await client.send_message(message)
    assert excinfo.value.response.status_code == 401


async def test_correct_api_key_is_accepted():
    scheme = APIKeySecurityScheme(location="header", name="X-API-Key")
    authenticator = ApiKeyAuthenticator(scheme, valid_keys={"secret-key"})
    server = AgentServer(make_card(), uppercase_handler, authenticator=authenticator)
    client = client_for(server, auth_headers=api_key_headers("X-API-Key", "secret-key"))

    message = Message(role=Role.USER, parts=[Part.of_text("hi")])
    task = await client.send_message(message)
    assert task.artifacts[0].parts[0].text == "HI"


async def test_wrong_api_key_is_rejected():
    scheme = APIKeySecurityScheme(location="header", name="X-API-Key")
    authenticator = ApiKeyAuthenticator(scheme, valid_keys={"secret-key"})
    server = AgentServer(make_card(), uppercase_handler, authenticator=authenticator)
    client = client_for(server, auth_headers=api_key_headers("X-API-Key", "wrong-key"))

    message = Message(role=Role.USER, parts=[Part.of_text("hi")])
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await client.send_message(message)
    assert excinfo.value.response.status_code == 401


async def test_bearer_token_authenticator_accepts_valid_token_rejects_others():
    scheme = HTTPAuthSecurityScheme(scheme="Bearer")
    authenticator = BearerAuthenticator(scheme, valid_tokens={"good-token"})
    server = AgentServer(make_card(), uppercase_handler, authenticator=authenticator)

    good_client = client_for(server, auth_headers=bearer_headers("good-token"))
    message = Message(role=Role.USER, parts=[Part.of_text("hi")])
    task = await good_client.send_message(message)
    assert task.artifacts[0].parts[0].text == "HI"

    bad_client = client_for(server, auth_headers=bearer_headers("bad-token"))
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await bad_client.send_message(message)
    assert excinfo.value.response.status_code == 401


async def test_agent_card_discovery_stays_public_even_when_the_agent_requires_auth():
    scheme = APIKeySecurityScheme(location="header", name="X-API-Key")
    authenticator = ApiKeyAuthenticator(scheme, valid_keys={"secret-key"})
    server = AgentServer(make_card(), uppercase_handler, authenticator=authenticator)
    client = client_for(server)  # no credentials at all

    card = await client.discover()
    assert card.name == "Echo Agent"
