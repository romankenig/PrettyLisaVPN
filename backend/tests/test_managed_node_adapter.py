"""Private node requests use authenticated mTLS client and closed acknowledgements."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient, MockTransport, Response
from test_vpn_node_health import make_node

from prettylisavpn.vpn_nodes.agent import HttpNodeAgentClient, NodeAgentUnavailableError


async def test_issue_and_remove_bind_session_and_authentication():
    identifier, password = uuid4(), str(uuid4())
    expires = datetime.now(UTC) + timedelta(minutes=15)
    calls = []

    def handle(request):
        calls.append(request.method)
        assert str(request.url) == f"https://203.0.113.10:8443/v1/managed/{identifier}"
        assert request.headers["Authorization"] == "Bearer private-token"
        if request.method == "PUT":
            assert json.loads(request.content) == {
                "secret": password,
                "expires": int(expires.timestamp()),
            }
            return Response(
                200,
                json={
                    "port": 18443,
                    "public_key": "a" * 43,
                    "server_name": "api.prettylisavpn.com",
                    "short_id": "ab",
                },
            )
        return Response(200, json={"removed": True})

    async with AsyncClient(transport=MockTransport(handle)) as client:
        agent = HttpNodeAgentClient(client, "private-token", 8443)
        assert (await agent.issue_managed(make_node(), identifier, password, expires)).port == 18443
        await agent.remove_managed(make_node(), identifier)
    assert calls == ["PUT", "DELETE"]


@pytest.mark.parametrize(
    "reply", [{}, {"removed": False}, {"removed": "true"}, {"removed": True, "extra": 1}]
)
async def test_incomplete_removal_is_not_acknowledged(reply):
    async with AsyncClient(transport=MockTransport(lambda _: Response(200, json=reply))) as client:
        with pytest.raises(NodeAgentUnavailableError):
            await HttpNodeAgentClient(client, "private", 8443).remove_managed(make_node(), uuid4())
