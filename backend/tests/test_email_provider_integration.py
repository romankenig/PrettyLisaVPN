import os
from datetime import UTC, datetime, timedelta

import pytest

from prettylisavpn.config import Settings
from prettylisavpn.emailing.service import VerificationEmailService
from prettylisavpn.emailing.timeweb import TimewebEmailProvider

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_EMAIL_INTEGRATION_TEST") != "1",
        reason="Set RUN_EMAIL_INTEGRATION_TEST=1 to send a real smoke-test email",
    ),
]


async def test_real_timeweb_mailbox_can_send_verification_email():
    recipient = os.environ["EMAIL_SMOKE_RECIPIENT"]
    settings = Settings()
    service = VerificationEmailService(TimewebEmailProvider.from_settings(settings))

    await service.send_code(
        recipient,
        "000000",
        datetime.now(UTC) + timedelta(seconds=settings.otp_ttl_seconds),
    )
