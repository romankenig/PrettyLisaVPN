"""Bounded Android support projection; never accepts arbitrary log lines or payloads."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Version = Annotated[
    str, Field(max_length=160, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.+-]+)?$")
]
Method = Annotated[
    str,
    Field(
        pattern=r"^(wireguard|amneziawg|sstp|softether|shadowsocks2022|vmess|vless|vless_reality|hysteria|hysteria2|hysteria2_salamander)(_relay)?$"
    ),
]
Phase = Literal[
    "DISCONNECTED",
    "CONNECTING",
    "CONNECTED",
    "CHECKING",
    "WAITING_NETWORK",
    "RECONNECTING",
    "DISCONNECTING",
    "FAILED",
]
Failure = Literal[
    "TIMEOUT",
    "NETWORK",
    "DNS",
    "TLS",
    "PERMISSION",
    "AUTH",
    "STORAGE",
    "CANCELLED",
    "OTHER",
    "METHODS_EXHAUSTED",
    "CLEANUP",
    "ACCESS",
    "UNSTABLE",
    "DEMO_LIMIT",
]
Transport = Literal["WIFI", "CELLULAR", "ETHERNET", "VPN", "OTHER"]
Stage = Literal[
    "IDLE",
    "CONSENT",
    "PERMISSION",
    "RECOVERY",
    "ADMISSION",
    "PROVISIONING",
    "LEASE",
    "CONFIG",
    "START",
    "ENGINE",
    "HANDSHAKE",
    "NETWORK",
    "VERIFY",
    "DNS",
    "HTTPS",
    "EGRESS_MISMATCH",
    "VERIFICATION_FAILED",
    "VERIFIED",
    "HEARTBEAT",
    "STOP",
    "CLEANUP",
    "OTHER",
]
Count = Annotated[int, Field(ge=0, le=2**53)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class DeviceDiagnostics(Strict):
    manufacturer: str = Field(max_length=80)
    model: str = Field(max_length=120)
    android_release: str = Field(max_length=40)
    android_api: int = Field(ge=26, le=100)
    security_patch: str | None = Field(default=None, max_length=20)
    build_id: str = Field(max_length=120)
    abis: list[Annotated[str, Field(max_length=40)]] = Field(max_length=8)
    app_version_code: int = Field(ge=1)
    app_debuggable: bool
    app_source_sha: str = Field(pattern=r"^(local|[0-9a-f]{40})$")
    memory_available_mb: Count | None = None
    memory_total_mb: Count | None = None
    storage_available_mb: Count | None = None
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    charging: bool | None = None
    power_save: bool | None = None
    device_idle: bool | None = None
    battery_optimization_exempt: bool | None = None


class NetworkDiagnostics(Strict):
    transports: list[Transport] = Field(max_length=5)
    internet: bool
    validated: bool
    captive_portal: bool
    metered: bool | None = None


class AndroidVpnDiagnostics(Strict):
    phase: Phase | None = None
    method: Method | None = None
    failure_code: Failure | None = None
    session_id: UUID | None = None
    routing_mode: Literal["ALL", "INCLUDE", "EXCLUDE"]
    enabled_methods: list[Method] = Field(max_length=22)


class DiagnosticFrame(Strict):
    class_name: str = Field(pattern=r"^com\.prettylisavpn\.android\.[A-Za-z0-9_.$]{1,200}$")
    method: str = Field(pattern=r"^[A-Za-z0-9_$<>-]{1,100}$")
    line: int = Field(ge=-2, le=1_000_000)


class DiagnosticEvent(Strict):
    at: datetime
    elapsed_ms: Count
    event: Literal[
        "APP_START",
        "APP_FOREGROUND",
        "APP_BACKGROUND",
        "APP_ERROR",
        "NETWORK_CHANGE",
        "API_RESULT",
        "VPN_CONNECT",
        "VPN_ATTEMPT",
        "VPN_RESULT",
        "VPN_HEALTH",
        "VPN_DISCONNECT",
        "VPN_RESET",
        "VPN_TRANSPORT_LOST",
        "VPN_SERVICE_LOST",
        "VPN_RECOVER",
        "VPN_STATE",
        "VPN_STAGE",
    ]
    method: Method | None = None
    phase: Phase | None = None
    stage: Stage | None = None
    outcome: (
        Literal[
            "STARTED",
            "SUCCESS",
            "FAILED",
            "CANCELLED",
            "HEALTHY",
            "UNREACHABLE",
            "NO_NETWORK",
            "UNKNOWN",
            "SUSPENDED",
        ]
        | None
    ) = None
    failure: Failure | None = None
    operation: (
        Literal[
            "AUTH",
            "PROFILE",
            "LOCATIONS",
            "VPN",
            "SUPPORT",
            "BILLING",
            "DEVICES",
            "MESSAGES",
            "OTHER",
        ]
        | None
    ) = None
    duration_ms: Count | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    network: NetworkDiagnostics | None = None
    country: str | None = Field(default=None, pattern=r"^(AUTO|[A-Z]{2})$")
    frames: list[DiagnosticFrame] | None = Field(default=None, max_length=24)
    api_code: (
        Literal[
            "OFFLINE",
            "NETWORK_UNCERTAIN",
            "INVALID_RESPONSE",
            "HTTP_ERROR",
            "SERVICE_UNAVAILABLE",
            "INVALID_ACCESS_TOKEN",
            "INVALID_SESSION",
            "INVALID_REFRESH_TOKEN",
            "REAUTH_REQUIRED",
            "AUTHENTICATION_REQUIRED",
            "DEVICE_REVOKED",
            "DEVICE_LIMIT_REACHED",
            "USER_BLOCKED",
            "OTP_INVALID_OR_EXPIRED",
            "OTP_RATE_LIMITED",
            "STORAGE_UNAVAILABLE",
            "ROTATION_UNCERTAIN",
            "VPN_SESSION_NOT_FOUND",
            "VPN_SESSION_ALREADY_ACTIVE",
            "VPN_UNAVAILABLE",
            "COUNTRY_UNAVAILABLE",
            "FREE_DAILY_LIMIT_REACHED",
            "VPN_ADDRESS_POOL_EXHAUSTED",
            "VPN_SETUP_FAILED",
            "VPN_TERMINATION_UNAVAILABLE",
            "VPN_SESSION_STATUS_UNAVAILABLE",
            "DEMO_UNAVAILABLE",
            "DEMO_RATE_LIMITED",
            "DEMO_QUOTA_EXHAUSTED",
            "REGISTRATION_REQUIRED",
            "SUPPORT_NOT_FOUND",
            "IDEMPOTENCY_CONFLICT",
            "RATE_LIMITED",
            "ATTACHMENT_REJECTED",
            "INVALID_REQUEST",
            "BILLING_DISABLED",
            "BILLING_REVISION_CHANGED",
            "BILLING_ACTION_UNAVAILABLE",
            "BILLING_ROUTE_UNAVAILABLE",
            "BILLING_OFFER_UNAVAILABLE",
            "BILLING_CURRENCY_LOCKED",
            "BILLING_IDEMPOTENCY_CONFLICT",
            "BILLING_OPERATION_IN_PROGRESS",
            "BILLING_OPERATION_NOT_FOUND",
            "DEVICE_NOT_FOUND",
            "MESSAGE_NOT_FOUND",
            "OTHER",
        ]
        | None
    ) = None

    @field_validator("at")
    @classmethod
    def utc_required(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("UTC required")
        return value


class DiagnosticLog(Strict):
    events: list[DiagnosticEvent] = Field(max_length=400)
    omitted_events: Count
    retention_days: Literal[7]
    storage_limit_bytes: Literal[2097152]
    available: bool = True
    dropped_events: Count = 0


class AndroidDiagnostics(Strict):
    schema_version: Literal[2]
    platform: Literal["ANDROID"]
    collected_at: datetime
    frontend_version: Version
    backend_version: Version | None
    language: str = Field(max_length=40, pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
    timezone: str = Field(max_length=80, pattern=r"^[A-Za-z0-9_+/:.-]+$")
    plan: Literal["DEMO", "FREE", "PREMIUM", "PLATINUM"] | None
    auth_session_id: UUID | None = None
    device: DeviceDiagnostics
    network: NetworkDiagnostics
    vpn: AndroidVpnDiagnostics
    logs: DiagnosticLog

    @field_validator("collected_at")
    @classmethod
    def utc_required(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("UTC required")
        return value
