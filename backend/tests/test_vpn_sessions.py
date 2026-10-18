"""VPN session domain tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from ipaddress import IPv4Address, IPv6Address
from uuid import uuid4

import pytest

from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.entitlements import FREE_ENTITLEMENTS
from prettylisavpn.vpn_sessions.domain import VpnSession, VpnSessionStatus

PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def make_session(**changes: object) -> VpnSession:
    now = datetime.now(UTC)
    session = VpnSession(
        id=uuid4(),
        user_id=uuid4(),
        device_id=uuid4(),
        vpn_node_id=uuid4(),
        client_wireguard_public_key=PUBLIC_KEY,
        allocated_client_ipv4=IPv4Address("10.88.0.2"),
        plan_snapshot=SubscriptionPlan.FREE,
        status=VpnSessionStatus.PENDING,
        started_at=now,
        expires_at=now + timedelta(hours=1),
        disconnected_at=None,
        peer_removed_at=None,
        created_at=now,
        updated_at=now,
    )
    return replace(session, **changes)


def test_new_free_session_uses_server_side_entitlement_duration():
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)

    session = VpnSession.new(
        user_id=uuid4(),
        device_id=uuid4(),
        vpn_node_id=uuid4(),
        client_wireguard_public_key=PUBLIC_KEY,
        allocated_client_ipv4=IPv4Address("10.88.0.2"),
        plan_snapshot=SubscriptionPlan.FREE,
        now=now,
    )

    assert FREE_ENTITLEMENTS.vpn_session_limit == timedelta(hours=1)
    assert session.expires_at == now + timedelta(hours=1)
    assert session.status is VpnSessionStatus.PENDING
    assert session.is_live()


def test_new_premium_session_has_no_duration_limit():
    session = VpnSession.new(
        user_id=uuid4(),
        device_id=uuid4(),
        vpn_node_id=uuid4(),
        client_wireguard_public_key=PUBLIC_KEY,
        allocated_client_ipv4=IPv4Address("10.88.0.2"),
        plan_snapshot=SubscriptionPlan.PREMIUM,
        now=datetime.now(UTC),
    )

    assert session.expires_at is None


def test_normalizes_session_times_to_utc():
    offset = timezone(timedelta(hours=3))
    started_at = datetime.now(UTC).astimezone(offset)
    session = make_session(
        started_at=started_at,
        expires_at=started_at + timedelta(hours=1),
        created_at=started_at,
        updated_at=started_at,
    )

    assert session.started_at.tzinfo is UTC
    assert session.expires_at is not None
    assert session.expires_at.tzinfo is UTC


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"client_wireguard_public_key": "private-key"}, "must be valid base64"),
        ({"allocated_client_ipv4": IPv6Address("fd00::2")}, "must be an IPv4 address"),
        ({"expires_at": None}, "FREE VPN sessions must expire"),
        ({"started_at": datetime.now()}, "started_at must be timezone-aware"),
    ],
)
def test_rejects_invalid_session_metadata(changes: dict[str, object], message: str):
    with pytest.raises(ValueError, match=message):
        make_session(**changes)


def test_rejects_non_positive_free_session_limit():
    with pytest.raises(ValueError, match="free_session_limit must be positive"):
        VpnSession.new(
            user_id=uuid4(),
            device_id=uuid4(),
            vpn_node_id=uuid4(),
            client_wireguard_public_key=PUBLIC_KEY,
            allocated_client_ipv4=IPv4Address("10.88.0.2"),
            plan_snapshot=SubscriptionPlan.FREE,
            now=datetime.now(UTC),
            free_session_limit=timedelta(0),
        )


def test_disconnected_status_and_timestamp_must_agree():
    now = datetime.now(UTC) + timedelta(minutes=1)
    with pytest.raises(ValueError, match="status and disconnected_at are inconsistent"):
        make_session(status=VpnSessionStatus.DISCONNECTED, disconnected_at=None)
    with pytest.raises(ValueError, match="status and disconnected_at are inconsistent"):
        make_session(status=VpnSessionStatus.ACTIVE, disconnected_at=now)


def test_terminal_status_is_not_live():
    assert not make_session(status=VpnSessionStatus.EXPIRED).is_live()


def test_peer_cleanup_completion_is_valid_only_for_terminal_sessions():
    removed_at = datetime.now(UTC) + timedelta(minutes=1)
    with pytest.raises(ValueError, match="live sessions"):
        make_session(peer_removed_at=removed_at)

    disconnected = make_session(
        status=VpnSessionStatus.DISCONNECTED,
        disconnected_at=removed_at,
        peer_removed_at=removed_at,
        updated_at=removed_at,
    )
    assert disconnected.peer_removed_at == removed_at

