"""Cleanup acknowledgements must survive database commit, not just node removal."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from test_vpn_sessions import make_session

from prettylisavpn.vpn_nodes.agent import NodeAgentUnavailableError
from prettylisavpn.vpn_sessions import termination
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus


@pytest.mark.parametrize(
    "outcome", ["success", "commit_failure", "node_failure", "missing", "live", "already_removed"]
)
async def test_cleanup_acknowledges_only_durable_removal(monkeypatch, outcome):
    now = datetime.now(UTC)
    record = make_session(
        created_at=now - timedelta(seconds=2),
        started_at=now - timedelta(seconds=1),
        status=VpnSessionStatus.DISCONNECTED,
        disconnected_at=now,
        peer_removed_at=now if outcome == "already_removed" else None,
    )
    current = make_session() if outcome == "live" else record
    repository = AsyncMock()
    repository.get_for_update.return_value = None if outcome == "missing" else current
    monkeypatch.setattr(termination, "VpnSessionRepository", lambda _: repository)

    @asynccontextmanager
    async def begin():
        yield
        if outcome == "commit_failure":
            raise SQLAlchemyError("commit failed")

    @asynccontextmanager
    async def session():
        yield SimpleNamespace(begin=begin)

    agent = AsyncMock()
    if outcome == "node_failure":
        agent.remove_peer.side_effect = NodeAgentUnavailableError
    confirmed = await termination.remove_and_record_peer(
        SimpleNamespace(session=session), agent, record, object()
    )
    assert confirmed is (outcome in {"success", "already_removed"})
    assert agent.remove_peer.await_count == (
        outcome in {"success", "commit_failure", "node_failure"}
    )
    assert repository.update.await_count == (outcome in {"success", "commit_failure"})
