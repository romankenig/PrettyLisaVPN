"""Android's shared wire fixture, strict diagnostic fields and readable support mail."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_support import client_service, report

from prettylisavpn.auth.session_service import AccessIdentity
from prettylisavpn.support.delivery import SupportSmtpMailer
from prettylisavpn.support.domain import Receipt, Report
from prettylisavpn.support.model import SupportRequestRecord


def android_diagnostics():
    path = (
        Path(__file__).resolve().parents[2]
        / "apps/android/app/src/test/resources/support-android-v2.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_shared_android_fixture_and_large_bounded_http_report():
    data = android_diagnostics()
    data["logs"]["events"] *= 200
    payload = report(diagnostics=data)
    encoded = json.dumps(payload)
    assert 32768 < len(encoded) < 262144
    parsed = Report.model_validate_json(encoded)
    assert parsed.diagnostics.platform == "ANDROID"
    app = client_service()
    with TestClient(app) as client:
        service = AsyncMock()
        service.auth.authenticate.return_value = AccessIdentity(uuid4(), uuid4(), uuid4())
        service.upload_slots = asyncio.Semaphore(1)
        service.accept.return_value = Receipt(request_id=parsed.request_id, status="ACCEPTED")
        app.state.support = service
        response = client.post(
            "/support/requests",
            headers={"Authorization": "Bearer synthetic"},
            files={"report": (None, encoded)},
        )
        assert response.status_code == 202
        assert service.accept.call_args.args[1].diagnostics.platform == "ANDROID"


@pytest.mark.parametrize("section", ["device", "network", "vpn", "logs"])
@pytest.mark.parametrize(
    "field", ["access_token", "private_key", "url", "dns_queries", "ssid", "email"]
)
def test_android_diagnostics_rejects_extra_sensitive_fields(section, field):
    data = android_diagnostics()
    data[section][field] = "must-not-be-accepted"
    with pytest.raises(ValidationError):
        Report.model_validate(report(diagnostics=data))


def test_android_log_bounds_codes_utc_and_no_arbitrary_lines():
    for mutation in (
        lambda d: d["logs"]["events"][0].update(message="raw exception with a credential"),
        lambda d: d["logs"]["events"][0].update(method="https://private.example"),
        lambda d: d["logs"]["events"][0].update(api_code="arbitrary server error text"),
        lambda d: d["logs"]["events"][0].update(at="2026-11-08T12:00:00+03:00"),
        lambda d: d["logs"].update(events=d["logs"]["events"] * 201),
        lambda d: d.update(collected_at="2026-11-08T12:00:00"),
        lambda d: d["logs"]["events"][0].update(
            frames=[{"class_name": "secret", "method": "connect", "line": 1}]
        ),
    ):
        data = android_diagnostics()
        mutation(data)
        with pytest.raises(ValidationError):
            Report.model_validate(report(diagnostics=data))
    with pytest.raises(ValidationError):
        Report.model_validate(report(account_email="forged@example.com"))


async def test_android_mail_displays_sender_and_reply_and_attaches_json():
    payload = report(diagnostics=android_diagnostics())
    payload["account_email"] = "account@example.com"
    row = SupportRequestRecord(
        user_id=uuid4(), request_id=uuid4(), payload=payload, created_at=datetime.now(UTC)
    )
    transport = AsyncMock()
    await SupportSmtpMailer(transport).send(row, [])
    message = transport.send.call_args.args[0]
    text = message.get_body(preferencelist=("plain",)).get_content()
    assert "Account email: account@example.com" in text
    assert "Reply email: reply@example.com" in text
    assert message["Reply-To"] == "reply@example.com"
    attachment = list(message.iter_attachments())[0]
    assert attachment.get_filename() == "diagnostics.json"
    assert attachment.get_content_type() == "application/json"
    assert json.loads(attachment.get_payload(decode=True)) == payload["diagnostics"]
