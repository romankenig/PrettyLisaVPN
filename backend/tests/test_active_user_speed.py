"""Account/direction activity, counter lifecycle, real intervals and API boundary."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from test_fleet import ADMIN, MONITOR, settings

from prettylisavpn.fleet.traffic import Snapshot, TrafficRollup, intervals
from prettylisavpn.fleet.traffic_service import TrafficService
from prettylisavpn.main import create_app

BASE = 1794052800


def sample(at, lease, download=0, upload=0, **kwargs):
    counter = dict(
        lease_id=lease, epoch="peer-1", at=BASE + at, monotonic=at, download=download, upload=upload
    )
    counter.update(kwargs.pop("counter", {}))
    return Snapshot(
        at=BASE + at, monotonic=at, boot="boot-1", complete=True, counters=[counter], **kwargs
    )


def row(user, start, end, down, up=0):
    return dict(user=user, start=BASE + start, end=BASE + end, download=down, upload=up)


def rollup(nodes=("a", "b"), step=60, threshold=10000):
    return TrafficRollup(BASE, BASE + step, step, list(nodes), threshold)


def test_unequal_users_are_weighted_by_activity_seconds_not_server_means():
    metric = rollup()
    metric.add("a", [row("alice", 0, 5, 625000)], BASE, BASE + 5, True)  # 1 Mbps
    metric.add("b", [row("bob", 0, 5, 6250000), row("carol", 0, 5, 6250000)], BASE, BASE + 5, True)
    point = metric.points()[0]
    assert point["download"]["mean_mbps"] == 7  # not (1 + 10) / 2
    assert point["download"]["median_mbps"] == 10
    assert point["download"]["active_users"] == 3
    assert point["upload"]["mean_mbps"] is None


def test_merge_devices_and_servers_before_threshold_and_count_time_once():
    metric = rollup()
    for node in ("a", "b"):
        metric.add(node, [row("alice", 0, 5, 3750)], BASE, BASE + 5, True)  # 6 Kbps each
    point = metric.points()[0]["download"]
    assert point["mean_mbps"] == 0.012
    assert point["active_users"] == 1
    assert point["active_seconds"] == 5
    selected = rollup(nodes=("a",))
    selected.add("a", [row("alice", 0, 5, 3750)], BASE, BASE + 5, True)
    selected.add("b", [row("alice", 0, 5, 3750)], BASE, BASE + 5, True)
    assert selected.points()[0]["download"]["mean_mbps"] is None


def test_partial_directional_activity_excludes_idle_bytes_and_seconds():
    metric = rollup()
    metric.add(
        "a",
        [row("alice", 0, 5, 625000, 100), row("alice", 5, 10, 6250, 1250000)],
        BASE,
        BASE + 10,
        True,
    )
    point = metric.points()[0]
    assert point["download"]["mean_mbps"] == 1  # 10 Kbps is NOT strictly above threshold
    assert point["download"]["bytes"] == 625000
    assert point["download"]["active_seconds"] == 5
    assert point["upload"]["mean_mbps"] == 2
    assert point["upload"]["active_seconds"] == 5


def test_real_overlap_union_and_minute_boundary_preserve_bytes():
    metric = TrafficRollup(BASE, BASE + 120, 60, ["a", "b"], 0)
    metric.add("a", [row("alice", 58, 63, 5000)], BASE + 58, BASE + 63, True)
    metric.add("b", [row("alice", 59, 64, 5000)], BASE + 59, BASE + 64, True)
    points = metric.points()
    assert sum(p["download"]["bytes"] for p in points) == 10000
    assert sum(p["download"]["active_seconds"] for p in points) == 6
    assert points[0]["download"]["mean_mbps"] == 0.012


def test_long_period_recomputes_per_user_median_and_weighted_mean():
    metric = rollup(step=3600, threshold=0)
    metric.add("a", [row("alice", 0, 5, 625000), row("bob", 0, 5, 6250000)], BASE, BASE + 5, True)
    metric.add("a", [row("alice", 60, 65, 1250000)], BASE + 60, BASE + 65, True)
    point = metric.points()[0]["download"]
    assert point["mean_mbps"] == pytest.approx(13 / 3)
    assert point["median_mbps"] == 5.75  # median(1.5, 10), not mean(5.5, 2)
    assert point["active_users"] == 2


def test_current_hour_uses_completed_minutes_and_correct_partial_coverage():
    metric = TrafficRollup(BASE + 60, BASE + 3660, 3600, ["a"], 0)
    metric.add("a", [row("alice", 3600, 3605, 625000)], BASE + 3600, BASE + 3660, True)
    points = metric.points()
    assert [point["duration_seconds"] for point in points] == [3540, 60]
    assert points[1]["coverage"]["fraction"] == 1
    assert points[1]["download"]["mean_mbps"] == 1


def test_no_activity_or_missing_samples_are_null_with_independent_coverage():
    metric = rollup()
    metric.add("a", [], BASE, BASE + 60, True)
    point = metric.points()[0]
    assert point["download"]["mean_mbps"] is None
    assert point["download"]["median_mbps"] is None
    assert point["coverage"]["fraction"] == 0.5
    assert point["coverage"]["complete_servers"] == 1
    assert point["coverage"]["expected_servers"] == 2


@pytest.mark.parametrize(
    "change", ["new", "reset", "epoch", "boot", "gap", "clock", "duplicate", "owner"]
)
def test_unknown_baselines_never_produce_negative_rates_or_spikes(change):
    lease, user = uuid4(), uuid4()
    before = sample(5, lease, download=1000000)
    after = sample(10, lease, download=2000000)
    owners = {lease: user}
    if change == "new":
        before = None
    if change == "reset":
        after.counters[0].download = 0
    if change == "epoch":
        after.counters[0].epoch = "new-peer"
    if change == "boot":
        after.boot = "new-boot"
    if change == "gap":
        after = sample(20, lease, download=2000000)
    if change == "clock":
        after.counters[0].monotonic = 8
    if change == "duplicate":
        after = before
    if change == "owner":
        owners = {}
    data, complete = intervals(before, after, owners)
    assert not data and not complete


def test_actual_elapsed_time_and_independent_user_mapping():
    lease, user = uuid4(), uuid4()
    before, after = sample(1, lease, 999), sample(7, lease, 6000999, 3000000)
    data, complete = intervals(before, after, {lease: user})
    assert complete
    metric = rollup(threshold=0)
    metric.add("a", data, before.at, after.at, complete)
    point = metric.points()[0]
    assert point["download"]["mean_mbps"] == 8
    assert point["upload"]["mean_mbps"] == 4
    assert point["download"]["active_seconds"] == 6


def test_duplicate_connection_and_negative_counters_rejected():
    value = sample(5, uuid4())
    raw = value.model_dump()
    raw["counters"] *= 2
    with pytest.raises(ValidationError):
        Snapshot.model_validate(raw)
    with pytest.raises(ValidationError):
        sample(5, uuid4(), -1)


@pytest.mark.parametrize("token,status", [(None, 401), (MONITOR, 200), (ADMIN, 200)])
async def test_endpoint_uses_existing_monitor_authorization_and_validates_filters(
    monkeypatch, token, status
):
    history = AsyncMock(return_value={"points": [], "nodes": []})
    monkeypatch.setattr(TrafficService, "history", history)
    app = create_app(settings(), postgres=AsyncMock(), valkey=AsyncMock())
    headers = {"Authorization": "Bearer " + token} if token else {}
    identifier = uuid4()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        response = await client.get(
            f"/admin/monitoring/active-user-speed?period=24h&node_ids={identifier}", headers=headers
        )
        assert response.status_code == status
        if status == 200:
            history.assert_awaited_once_with("24h", [identifier])
            assert (
                await client.get("/admin/monitoring/active-user-speed?period=30d", headers=headers)
            ).status_code == 422
            assert (
                await client.get(
                    "/admin/monitoring/active-user-speed?node_ids=bad", headers=headers
                )
            ).status_code == 422
        else:
            history.assert_not_called()
