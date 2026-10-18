"""The shared support contract accepts only an explicit diagnostic projection."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Version = Annotated[
    str, Field(max_length=160, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.+-]+)?$")
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class VpnDiagnostics(StrictModel):
    phase: Literal[
        "RECONCILING",
        "CONNECTING",
        "DISCONNECTING",
        "DISCONNECTED",
        "CONNECTED",
        "TUNNEL_ESTABLISHED",
        "VERIFYING_INTERNET",
        "DEGRADED",
        "FAILED",
        "UNAVAILABLE",
    ]
    backend: Literal["UNKNOWN", "ACTIVE", "NONE", "UNAVAILABLE"]
    tunnel: Literal["UNKNOWN", "UP", "DOWN", "UNAVAILABLE"]
    session_id: UUID | None
    failure_code: (
        Literal[
            "TRANSPORT_TIMEOUT",
            "HANDSHAKE_FAILED",
            "TUNNEL_ESTABLISHED_NO_TRAFFIC",
            "DNS_FAILED",
            "HTTPS_CHECK_FAILED",
            "EGRESS_MISMATCH",
            "ROUTE_LEAK_DETECTED",
            "SERVER_UNREACHABLE",
            "OBFUSCATION_FAILED",
            "UNKNOWN",
            "CONNECTION_FAILED",
            "INTERNET_UNVERIFIED",
            "UNSUPPORTED_CONFIGURATION",
            "RUNTIME_UNAVAILABLE",
        ]
        | None
    )


class Diagnostics(StrictModel):
    schema_version: Literal[1]
    collected_at: datetime
    frontend_version: Version | None
    backend_version: Version | None
    platform: Literal["WINDOWS"]
    language: Annotated[str, Field(max_length=40, pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")]
    timezone: Annotated[str, Field(max_length=80, pattern=r"^[A-Za-z0-9_+/-]+$")]
    plan: Literal["FREE", "PREMIUM", "PLATINUM"] | None
    auth_session_id: UUID | None
    vpn: VpnDiagnostics

    @field_validator("collected_at")
    @classmethod
    def utc_required(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("UTC required")
        return value


class Report(StrictModel):
    request_id: UUID
    subject: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    reply_email: EmailStr = Field(max_length=254)
    diagnostics: Diagnostics | None

    @model_validator(mode="after")
    def valid_text(self) -> Self:
        if not self.subject.strip() or not self.description.strip():
            raise ValueError("Empty text")
        if any(ord(c) < 32 or ord(c) == 127 for c in self.subject):
            raise ValueError("Invalid subject")
        if any(ord(c) < 32 and c not in "\n\r\t" for c in self.description):
            raise ValueError("Invalid description")
        if any(c in str(self.reply_email) for c in "\r\n"):
            raise ValueError("Invalid reply address")
        return self


Status = Literal["ACCEPTED", "RETRYING", "SENT", "FAILED", "EXPIRED"]


class Receipt(StrictModel):
    request_id: UUID
    status: Status


class SupportError(Exception):
    def __init__(self, code: str, status: int) -> None:
        self.code = code
        self.status = status
        super().__init__(code)
