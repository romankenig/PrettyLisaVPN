"""Real durable lease intervals, JSON null coverage, both report contracts and privacy."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from test_client_vpn_integration import connect, vpn_state  # noqa: F401
from test_fleet_integration import fleet_state  # noqa: F401

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.fleet.method_checks import MethodAnalytics
from prettylisavpn.fleet.service_checks import ServiceAnalytics
from prettylisavpn.product_analytics.domain import boundary, day
from prettylisavpn.traffic.model import TrafficServiceRecord
from prettylisavpn.users.model import UserRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires disposable PostgreSQL"
    ),
]


async def test_daily_method_and_service_history_include_closed_today_and_survive_reread(vpn_state):  # noqa: F811
    postgres, service, worker, _, identity = vpn_state
    lease_id = UUID((await connect(service))["id"])
    await worker.tick()
    now = datetime(2099, 10, 16, 12, tzinfo=UTC)
    start = boundary(day(now))
    email = f"daily-usage-{uuid4()}@gmail.com"
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(UserRecord).where(UserRecord.id == identity.user_id).values(email=email)
        )
        catalog = await session.scalar(select(TrafficServiceRecord).limit(1))
        selected_id, slug = str(catalog.id), catalog.slug
        lease = await session.get(ClientLeaseRecord, lease_id)
        lease.created_at = lease.verified_at = start - timedelta(days=2)
        lease.expires_at = lease.removed_at = now + timedelta(hours=1)
        lease.disconnected_at, lease.heartbeat_at = start + timedelta(minutes=1), start
        lease.status, lease.traffic_mode = "CLOSED", "include"
        lease.service_ids, lease.custom_rules = (
            [selected_id, selected_id, str(uuid4())],
            ["*.private-rule.example.org"],
        )
        await session.flush()
        fields = {
            column.key: getattr(lease, column.key) for column in ClientLeaseRecord.__table__.columns
        }
        empty_id = uuid4()
        for changes in [
            dict(
                method="https_proxy",
                address=None,
                engine_port=41000,
                verified_at=start - timedelta(hours=1),
                disconnected_at=start,
                traffic_mode="all",
                service_ids=[],
                custom_rules=[],
            ),
            dict(
                id=empty_id,
                verified_at=start + timedelta(hours=1),
                status="READY",
                disconnected_at=None,
                removed_at=None,
                service_ids=[],
                custom_rules=[],
            ),
            dict(
                verified_at=start - timedelta(hours=2),
                disconnected_at=start + timedelta(hours=2),
                traffic_mode=None,
                service_ids=None,
                custom_rules=None,
            ),
            dict(verified_at=now + timedelta(minutes=1)),
            dict(verified_at=None),
        ]:
            values = {**fields, "id": uuid4(), "request_id": uuid4(), **changes}
            values["created_at"] = (values["verified_at"] or start) - timedelta(seconds=1)
            session.add(ClientLeaseRecord(**values))
    methods = await MethodAnalytics(postgres).report(now)
    services = await ServiceAnalytics(postgres).report(now)
    assert methods["selection"]["active_sessions"] == 1
    points = methods["selection_history"]["points"]
    assert points[-2]["counts"] == {"https_proxy": 1, "wireguard": 2}
    assert points[-1]["counts"] == {"wireguard": 3}
    selected = services["selection_history"]["points"][-1]
    assert selected["counts"] == {slug: 1, "UNKNOWN": 1}
    assert selected["active_sessions"] == selected["observed_sessions"] == 2
    assert selected["unknown_mode_sessions"] == 1 and not selected["complete"]
    assert services["selection"]["items"] == []
    for report in (methods["selection_history"], services["selection_history"]):
        assert email not in str(report) and str(identity.user_id) not in str(report)
        assert str(lease_id) not in str(report) and "private-rule" not in str(report)
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(ClientLeaseRecord)
            .where(ClientLeaseRecord.id == empty_id)
            .values(service_ids=[selected_id])
        )
    fresh = (await ServiceAnalytics(postgres).report(now + timedelta(minutes=1)))[
        "selection_history"
    ]
    # Future verification now enters today, but its invalid earlier disconnect is excluded.
    assert fresh["points"][-1]["counts"] == {slug: 2, "UNKNOWN": 1}
    assert (await ServiceAnalytics(postgres).report(now))["selection_history"]["points"][
        -2
    ] == services["selection_history"]["points"][-2]
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(UserRecord)
            .where(UserRecord.id == identity.user_id)
            .values(email=f"excluded-{uuid4()}@example.com")
        )
    assert (await MethodAnalytics(postgres).report(now))["selection_history"]["points"][-1][
        "counts"
    ] == {}
    assert (await ServiceAnalytics(postgres).report(now))["selection_history"]["points"][-1][
        "counts"
    ] == {}


async def test_daily_outcomes_classify_durable_attempts_and_service_choices(vpn_state):  # noqa: F811
    postgres, service, worker, _, identity = vpn_state
    lease_id = UUID((await connect(service))["id"])
    await worker.tick()
    now = datetime(2099, 10, 16, 12, tzinfo=UTC)
    start = boundary(day(now))
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(UserRecord)
            .where(UserRecord.id == identity.user_id)
            .values(email=f"outcome-{uuid4()}@gmail.com")
        )
        catalog = await session.scalar(select(TrafficServiceRecord).limit(1))
        selected_id, slug = str(catalog.id), catalog.slug
        lease = await session.get(ClientLeaseRecord, lease_id)
        lease.created_at = lease.verified_at = start - timedelta(hours=1)
        lease.expires_at = now + timedelta(hours=1)
        lease.disconnected_at = lease.removed_at = now
        lease.status, lease.traffic_mode = "CLOSED", "include"
        lease.service_ids, lease.custom_rules = [selected_id], []
        await session.flush()
        fields = {
            column.key: getattr(lease, column.key) for column in ClientLeaseRecord.__table__.columns
        }
        pending_id = uuid4()
        for changes in [
            dict(
                method="https_proxy",
                address=None,
                engine_port=41000,
                service_ids=[selected_id, selected_id, str(uuid4())],
                custom_rules=["*.private-rule.example.org"],
            ),
            dict(created_at=start - timedelta(seconds=1)),
            dict(traffic_mode=None, service_ids=None, custom_rules=None),
            dict(
                id=pending_id,
                status="PROVISIONING",
                disconnected_at=None,
                removed_at=None,
                code="VPN_NODE_UNAVAILABLE",
            ),
        ]:
            session.add(
                ClientLeaseRecord(
                    **{
                        **fields,
                        "id": uuid4(),
                        "request_id": uuid4(),
                        "created_at": start,
                        "verified_at": None,
                        **changes,
                    }
                )
            )
    for analytics, is_service in [
        (MethodAnalytics(postgres), False),
        (ServiceAnalytics(postgres), True),
    ]:
        history = (await analytics.report(now))["selection_history"]
        outcomes = history["outcomes"]
        assert outcomes["successful"]["points"] == history["points"]
        assert all(value["categories"] == history["categories"] for value in outcomes.values())
        success, failed, all_rows = (
            outcomes[key]["points"][-1] for key in ("successful", "unsuccessful", "all")
        )
        assert success["counts"] == {slug if is_service else "wireguard": 1}
        assert failed["counts"] == (
            {slug: 1, "UNKNOWN": 1} if is_service else {"https_proxy": 1, "wireguard": 1}
        )
        assert all_rows["counts"] == (
            {slug: 2, "UNKNOWN": 1} if is_service else {"https_proxy": 1, "wireguard": 2}
        )
        assert outcomes["unsuccessful"]["points"][-2]["counts"] == {
            slug if is_service else "wireguard": 1
        }
        assert failed["complete"] is not is_service
        assert "private-rule" not in str(history) and str(lease_id) not in str(history)
    # A retry without verification enters the unsuccessful group only after it ends.
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(ClientLeaseRecord)
            .where(ClientLeaseRecord.id == pending_id)
            .values(status="REVOKING", disconnected_at=now)
        )
    fresh = (await MethodAnalytics(postgres).report(now))["selection_history"]["outcomes"]
    assert fresh["unsuccessful"]["points"][-1]["counts"] == {"https_proxy": 1, "wireguard": 2}
    assert fresh["successful"]["points"][-1]["total"] == 1
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(UserRecord)
            .where(UserRecord.id == identity.user_id)
            .values(email=f"excluded-{uuid4()}@example.com")
        )
    for analytics in (MethodAnalytics(postgres), ServiceAnalytics(postgres)):
        assert all(
            history["points"][-1]["counts"] == {}
            for history in (await analytics.report(now))["selection_history"]["outcomes"].values()
        )
