"""Shared completion rules for service and connection-method assessments."""

from datetime import datetime

from prettylisavpn.fleet.domain import Observation
from prettylisavpn.fleet.method_check_model import MethodCheckRecord
from prettylisavpn.fleet.service_check_model import ServiceCheckRecord
from prettylisavpn.fleet.service_checks import assessment_score


def finish_attempt(
    job: ServiceCheckRecord | MethodCheckRecord,
    result: Observation | None,
    code: str,
    attempt_at: datetime,
    finished: datetime,
    deadline: datetime,
) -> None:
    tested = bool(
        result is not None
        and result.mode == "SYNTHETIC"
        and result.code
        in {
            "SERVICE_CHECK_PASSED",
            "SERVICE_HTTP_FAILED",
            "HANDSHAKE_FAILED",
            "DNS_FAILED",
            "HTTPS_FAILED",
            "EGRESS_IP_MISMATCH",
        }
    )
    job.attempts = [*job.attempts[:-1], {**job.attempts[-1], "code": code, "tested": tested}]
    job.code, job.claim_token, job.claim_until = code, None, None
    if finished >= deadline:
        job.score = 0 if any(a.get("tested") for a in job.attempts) else None
        job.code = "UNAVAILABLE" if job.score == 0 else "NOT_OBSERVED"
        job.finished_at = finished
    elif (
        result is not None
        and result.status == "HEALTHY"
        and result.code == "SERVICE_CHECK_PASSED"
        and result.cleanup_confirmed
    ):
        assert job.started_at is not None
        job.score = assessment_score(job.started_at, attempt_at, True)
        job.finished_at = finished
    elif len(job.attempts) >= 30:
        job.score = 0 if any(a.get("tested") for a in job.attempts) else None
        job.code = "UNAVAILABLE" if job.score == 0 else "NOT_OBSERVED"
        job.finished_at = finished
