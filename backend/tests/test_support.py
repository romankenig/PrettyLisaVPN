"""Private support transport, raster decoding and mail adapter without external services."""

import asyncio
import json
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from pydantic import ValidationError

from prettylisavpn.config import Settings
from prettylisavpn.main import create_app
from prettylisavpn.support.delivery import SupportSmtpMailer
from prettylisavpn.support.domain import Receipt, Report, SupportError
from prettylisavpn.support.images import clean_image
from prettylisavpn.support.model import SupportAttachmentRecord, SupportRequestRecord


def diagnostics():
    return {
        "schema_version": 1,
        "collected_at": "2026-10-18T00:00:00Z",
        "frontend_version": "0.9.0",
        "backend_version": "0.4.0-dev.123+gabc",
        "platform": "WINDOWS",
        "language": "ru-RU",
        "timezone": "Europe/Moscow",
        "plan": "PREMIUM",
        "auth_session_id": str(uuid4()),
        "vpn": {
            "phase": "DISCONNECTED",
            "backend": "NONE",
            "tunnel": "DOWN",
            "session_id": None,
            "failure_code": None,
        },
    }


def report(**changes):
    return {
        "request_id": str(uuid4()),
        "subject": "Test support",
        "description": "A user supplied description.",
        "reply_email": "reply@example.com",
        "diagnostics": None,
        **changes,
    }


def image(fmt="PNG", **options):
    output = BytesIO()
    Image.new("RGB", (32, 20), "red").save(output, format=fmt, **options)
    return output.getvalue()


@pytest.mark.parametrize(
    "fmt,media", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_raster_rebuilt_without_metadata(fmt, media):
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "unnecessary metadata")
    exif = Image.Exif()
    exif[315] = "private-data"
    raw = image(fmt, pnginfo=metadata) if fmt == "PNG" else image(fmt, exif=exif)
    cleaned = clean_image(raw, media)
    with Image.open(BytesIO(cleaned.data)) as decoded:
        assert decoded.size == (32, 20)
        assert decoded.format == "PNG"
        assert decoded.info == {}
    assert b"private-data" not in cleaned.data
    assert b"unnecessary metadata" not in cleaned.data


@pytest.mark.parametrize(
    "data,media",
    [
        (b"<svg></svg>", "image/png"),
        (image(), "image/jpeg"),
        (image()[:30], "image/png"),
        (b"x" * (5 * 1024 * 1024 + 1), "image/png"),
    ],
    ids=["disguised", "wrong-media-type", "corrupt", "oversized"],
)
def test_reject_disguised_corrupt_and_oversized_images(data, media):
    with pytest.raises(SupportError, match="ATTACHMENT_REJECTED"):
        clean_image(data, media)


def test_reject_decoded_pixel_bomb_and_animation():
    output = BytesIO()
    Image.new("1", (4000, 4000)).save(output, "PNG")
    with pytest.raises(SupportError):
        clean_image(output.getvalue(), "image/png")
    output = BytesIO()
    Image.new("RGB", (10, 10), "red").save(
        output, "PNG", save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")]
    )
    with pytest.raises(SupportError):
        clean_image(output.getvalue(), "image/png")


@pytest.mark.parametrize(
    "changes",
    [
        {"subject": "bad\r\nBcc: victim@example.com"},
        {"reply_email": "reply@example.com\r\nBcc: victim@example.com"},
        {"subject": " "},
        {"description": "x" * 4001},
        {"recipient": "victim@example.com"},
        {"access_token": "secret"},
    ],
)
def test_report_rejects_unknown_fields_and_header_injection(changes):
    with pytest.raises(ValidationError):
        Report.model_validate(report(**changes))


@pytest.mark.parametrize("field", ["access_token", "private_key", "history", "ip", "email", "dns"])
def test_diagnostics_rejects_non_allowlisted_fields(field):
    data = diagnostics()
    data[field] = "private"
    with pytest.raises(ValidationError):
        Report.model_validate(report(diagnostics=data))
    data = diagnostics()
    data["vpn"][field] = "private"
    with pytest.raises(ValidationError):
        Report.model_validate(report(diagnostics=data))


def test_diagnostics_accept_projection_but_no_arbitrary_failure_text_or_non_utc():
    Report.model_validate(report(diagnostics=diagnostics()))
    data = diagnostics()
    data["vpn"]["failure_code"] = "secret raw exception"
    with pytest.raises(ValidationError):
        Report.model_validate(report(diagnostics=data))
    data = diagnostics()
    data["collected_at"] = "2026-10-18T12:00:00+03:00"
    with pytest.raises(ValidationError):
        Report.model_validate(report(diagnostics=data))


def client_service():
    dependency = AsyncMock()
    config = Settings(_env_file=None)
    app = create_app(config, postgres=dependency, valkey=dependency)
    return app


def test_support_http_auth_parse_limits_errors_and_receipt(caplog):
    app = client_service()
    with TestClient(app) as client:
        service = AsyncMock()
        service.upload_slots = asyncio.Semaphore(2)
        app.state.support = service
        request = report()
        service.accept.return_value = Receipt(request_id=request["request_id"], status="ACCEPTED")
        headers = {"Authorization": "Bearer test-only"}
        assert client.post("/support/requests").json()["error"]["code"] == "AUTH_INVALID"
        assert client.get(f"/support/requests/{request['request_id']}").status_code == 401
        assert client.post("/support/requests", headers=headers, json=request).status_code == 422
        response = client.post(
            "/support/requests",
            headers=headers,
            files={
                "report": (None, json.dumps(request)),
                "screenshots": ("../../private.png", image(), "image/png"),
            },
        )
        assert response.status_code == 202
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["request_id"] == request["request_id"]
        assert service.accept.await_count == 1
        bad = client.post(
            "/support/requests", headers=headers, files={"report": (None, "secret-invalid-report")}
        )
        assert bad.status_code == 422
        assert "secret-invalid-report" not in bad.text + caplog.text
        service.get.side_effect = SupportError("SUPPORT_NOT_FOUND", 404)
        response = client.get(f"/support/requests/{request['request_id']}", headers=headers)
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
        assert (
            client.get("/support/requests/not-a-uuid", headers=headers).json()["error"]["code"]
            == "INVALID_REQUEST"
        )


async def test_mail_fixed_envelope_reply_to_and_safe_attachments():
    transport = AsyncMock()
    payload = report(diagnostics=diagnostics())
    row = SupportRequestRecord(
        user_id=uuid4(), request_id=uuid4(), payload=payload, created_at=datetime.now(UTC)
    )
    file = SupportAttachmentRecord(position=0, data=image(), media_type="image/png")
    await SupportSmtpMailer(transport).send(row, [file])
    args = transport.send.call_args
    message = args.args[0]
    assert args.kwargs == {
        "sender": "app-helper@prettylisavpn.com",
        "recipient": "help@prettylisavpn.com",
    }
    assert message["Reply-To"] == "reply@example.com"
    assert str(row.user_id) not in message["Message-ID"]
    first_message_id = message["Message-ID"]
    await SupportSmtpMailer(transport).send(row, [file])
    assert transport.send.call_args.args[0]["Message-ID"] == first_message_id
    attachment = list(message.iter_attachments())[0]
    assert attachment.get_filename() == "screenshot-1.png"
    assert attachment.get_payload(decode=True) == image()


def test_support_credentials_separate_from_auth():
    config = Settings(_env_file=None, email_smtp_password="auth-secret")
    assert SupportSmtpMailer.from_settings(config) is None
    config = Settings(
        _env_file=None, email_smtp_password="auth-secret", support_smtp_password="helper-secret"
    )
    mailer = SupportSmtpMailer.from_settings(config)
    assert mailer is not None
    assert mailer.transport._username == "app-helper@prettylisavpn.com"
    assert mailer.transport._password == "helper-secret"
