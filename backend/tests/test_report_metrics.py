from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from test_client_vpn import KEY
from test_fleet import ADMIN, MONITOR, settings

from prettylisavpn.client_vpn.domain import ConnectRequest
from prettylisavpn.fleet.service_checks import assessment_score, choose_candidate, daily_slot
from prettylisavpn.fleet.traffic import PERIODS, TrafficRollup
from prettylisavpn.fleet.ubuntu.service_probe import allowed, candidates, discover
from prettylisavpn.main import create_app
from prettylisavpn.product_analytics.domain import (
    Activity,
    Attempt,
    boundary,
    distribution,
    snapshot,
)
from prettylisavpn.product_analytics.model import SessionSilenceRecord
from prettylisavpn.product_analytics.silence import advance_silence

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


def test_seven_days_are_calendar_days_and_weight_raw_bytes_not_hour_means():
    step = PERIODS["7d"][1]
    assert step == 86400
    start = int(boundary(date(2026, 11, 7)).timestamp())
    end = start + 604800
    rollup = TrafficRollup(start, end, step, ["node"], 0, offset=10800)
    rollup.add(
        "node",
        [{"user": "a", "start": start, "end": start + 5, "download": 5000, "upload": 0}],
        start,
        start + 5,
        True,
    )
    rollup.add(
        "node",
        [{"user": "a", "start": start + 5, "end": start + 15, "download": 1000, "upload": 0}],
        start + 5,
        start + 15,
        True,
    )
    rollup.add(
        "node",
        [
            {
                "user": "a",
                "start": start + 86400,
                "end": start + 86405,
                "download": 50000,
                "upload": 0,
            }
        ],
        start + 86400,
        start + 86405,
        True,
    )
    points = rollup.points()
    assert len(points) == 7
    assert points[0]["at"] == "2026-11-06T21:00:00+00:00"
    assert points[0]["download"]["mean_mbps"] == pytest.approx(6000 * 8 / 15 / 1e6)
    assert points[1]["download"]["mean_mbps"] == 0.08
    assert points[2]["download"]["mean_mbps"] is None


def test_duration_boundaries_demo_cohorts_and_open_sessions():
    assert distribution([0, 10, 10.1, 60, 60.1, 180, 180.1, 300, 300.1, 900, 900.1])["counts"] == [
        2,
        2,
        2,
        2,
        2,
        1,
    ]
    assert distribution([])["shares"] == [None] * 6
    start = NOW - timedelta(days=1)
    result = snapshot(
        NOW,
        [Activity(uuid4(), start, "DEMO")],
        [],
        [
            Attempt(
                start,
                start,
                start + timedelta(hours=1),
                "wg",
                "ANDROID",
                start + timedelta(seconds=10),
                start + timedelta(seconds=3),
                True,
            ),
            Attempt(start, start, None, "wg", "WINDOWS"),
            Attempt(start, None, start + timedelta(seconds=10), "wg", "IOS"),
        ],
        start,
        start,
        start,
    )
    assert result["devices"] == {"ANDROID": 1, "WINDOWS": 1}
    assert result["mean_session_seconds"] == 10  # removal delay is not session length
    assert result["session_duration"]["counts"] == [1, 0, 0, 0, 0, 0]
    assert result["duration_unobserved_sessions"] == 1
    assert result["time_to_silence"]["counts"][0] == 1
    assert result["points"][-1]["dau"]["plans"]["DEMO"] == 1
    assert result["points"][-1]["mean_session_seconds"] == 10


def test_first_silence_requires_ten_seconds_not_an_outage_or_duplicate():
    state = SessionSilenceRecord(lease_id=uuid4(), observed_until=NOW, complete=True)
    advance_silence(state, NOW, NOW + timedelta(seconds=5), True, True)
    advance_silence(state, NOW + timedelta(seconds=5), NOW + timedelta(seconds=10), False, True)
    assert state.first_silence_at is None
    advance_silence(state, NOW + timedelta(seconds=10), NOW + timedelta(seconds=15), False, True)
    assert state.first_silence_at == NOW + timedelta(seconds=5)
    advance_silence(state, NOW + timedelta(seconds=15), NOW + timedelta(seconds=20), True, True)
    assert state.first_silence_at == NOW + timedelta(seconds=5)
    missing = SessionSilenceRecord(lease_id=uuid4(), observed_until=NOW, complete=True)
    advance_silence(missing, NOW + timedelta(seconds=10), NOW + timedelta(seconds=15), False, True)
    advance_silence(missing, NOW + timedelta(seconds=15), NOW + timedelta(seconds=30), False, True)
    assert not missing.complete and missing.first_silence_at is None


def test_random_retry_changes_both_dimensions_and_never_repeats_pair():
    a, b = uuid4(), uuid4()
    roster = [(a, "wg"), (b, "wg"), (a, "vless"), (b, "vless")]
    attempts = [{"node": str(a), "method": "wg"}]
    assert choose_candidate(roster, attempts) == (b, "vless")
    for _ in range(3):
        value = choose_candidate(roster, attempts)
        assert value is not None
        attempts.append({"node": str(value[0]), "method": value[1]})
    assert choose_candidate(roster, attempts) is None
    assert assessment_score(NOW, NOW, True) == 100
    assert assessment_score(NOW, NOW + timedelta(minutes=15), True) == 50
    assert assessment_score(NOW, NOW + timedelta(minutes=30), True) == 0
    assert assessment_score(NOW, NOW, False) == 0
    slots = [daily_slot(uuid4(), date(2026, 11, 14)) for _ in range(50)]
    assert len(set(slots)) > 45
    assert all(
        boundary(date(2026, 11, 14)) <= slot < boundary(date(2026, 11, 15)) - timedelta(minutes=30)
        for slot in slots
    )


@pytest.mark.parametrize("late", [False, True])
async def test_probe_success_must_finish_before_assessment_deadline(monkeypatch, late):
    import prettylisavpn.fleet.service_check_worker as module

    class Clock:
        value = NOW + timedelta(minutes=29)

        @classmethod
        def now(cls, tz):
            return cls.value

    token, service_id = uuid4(), uuid4()
    row = SimpleNamespace(
        claim_token=token,
        started_at=NOW,
        finished_at=None,
        attempts=[{"tested": True}, {"tested": False}],
    )
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.begin = MagicMock(return_value=AsyncMock())
    session.get.return_value = row
    postgres = SimpleNamespace(session=MagicMock(return_value=session))

    async def probe(*args):
        Clock.value = NOW + timedelta(minutes=31 if late else 29, seconds=10)
        return SimpleNamespace(
            status="HEALTHY", mode="SYNTHETIC", code="SERVICE_CHECK_PASSED", cleanup_confirmed=True
        )

    worker = module.ServiceCheckWorker(postgres, SimpleNamespace(probe=probe), AsyncMock())
    worker.schedule = AsyncMock()
    worker.claim = AsyncMock(
        return_value=(
            service_id,
            NOW.date(),
            token,
            None,
            None,
            "wireguard",
            ["example.com"],
            Clock.value,
            NOW + timedelta(minutes=30),
        )
    )
    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(module, "discover", lambda _: "https://example.com/news/item")
    await worker.tick()
    assert row.finished_at == Clock.value
    assert row.score == (0 if late else 3.3)
    assert row.code == ("UNAVAILABLE" if late else "SERVICE_CHECK_PASSED")


def test_sampler_prefers_fresh_links_and_rejects_credentials_external_redirects():
    domains = ["sample.example", "*.sample.example"]
    assert allowed("https://sample.example/news/recent", domains)
    assert not allowed("https://sample.example.evil.test/news/recent", domains)
    for url in [
        "http://sample.example/a",
        "https://user@sample.example/a",
        "https://sample.example:444/a",
        "https://sample.example/a#fragment",
    ]:
        assert not allowed(url, domains)
    links, feeds = candidates(
        b'<a href="/about">About</a><a href="/news/2026-new">News</a>'
        b'<a href="https://evil.test/a">Escape</a>'
        b'<link type="application/rss+xml" href="/rss"/>',
        "https://sample.example",
        domains,
    )
    assert links == ["https://sample.example/news/2026-new"]
    assert feeds == ["https://sample.example/rss"]


def test_sampler_confirms_existing_link_and_missing_sample_is_not_success(monkeypatch):
    import prettylisavpn.fleet.ubuntu.service_probe as sampler

    calls = []

    def fetch(url, domains):
        calls.append(url)
        return (
            url,
            b'<a href="/news/fresh">News</a>' if url.endswith("/") else b"publication",
            "text/html",
        )

    monkeypatch.setattr(sampler, "fetch", fetch)
    assert discover(["sample.example"]) == "https://sample.example/news/fresh"
    assert calls == ["https://sample.example/", "https://sample.example/news/fresh"]
    monkeypatch.setattr(sampler, "fetch", lambda *a: (a[0], b"no links", "text/html"))
    assert discover(["sample.example"]) is None


def test_connection_accepts_only_configured_rules_not_browsing_urls():
    base = {"public_key": KEY, "traffic_mode": "include"}
    parsed = ConnectRequest(
        **base, custom_rules=["*.EXAMPLE.com", "*.example.com"], service_ids=[uuid4()]
    )
    assert parsed.custom_rules == ["*.example.com"]
    for rule in [
        "https://example.com/news",
        "example.com/private",
        "127.0.0.1",
        "a@example.com",
        "example.com?q=private",
    ]:
        with pytest.raises(ValidationError):
            ConnectRequest(**base, custom_rules=[rule])


@pytest.mark.parametrize(
    "token,status", [(None, 401), ("wrong", 401), (MONITOR, 200), (ADMIN, 200)]
)
async def test_service_report_is_private_and_read_only(token, status, monkeypatch):
    from prettylisavpn.fleet.service_checks import ServiceAnalytics

    report = AsyncMock(return_value={"services": [], "selection": {}})
    monkeypatch.setattr(ServiceAnalytics, "report", report)
    app = create_app(settings(), postgres=AsyncMock(), valkey=AsyncMock())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client,
    ):
        response = await client.get(
            "/admin/monitoring/services",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        assert response.status_code == status
        assert report.await_count == (1 if status == 200 else 0)
