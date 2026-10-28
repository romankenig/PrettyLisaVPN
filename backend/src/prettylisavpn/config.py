"""Environment configuration. Secrets are redacted in model representations."""

from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_OTP_HMAC_SECRET = "local-development-otp-hmac-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    application_name: str = Field(default="PrettyLisaVPN", min_length=1)
    application_version: str = Field(default="0.20.0", min_length=1)
    environment: str = Field(default="development", min_length=1)
    billing_provider: Literal["disabled", "sandbox"] = "disabled"
    fleet_enabled: bool = False
    client_vpn_enabled: bool = False
    fleet_admin_token: SecretStr | None = None
    fleet_monitor_token: SecretStr | None = None
    fleet_inventory_path: str = "/run/fleet/inventory.json"
    fleet_speed_target_mbps: float = Field(default=100, gt=0, le=10000)
    fleet_connection_target_ms: float = Field(default=1000, gt=0, le=60000)
    fleet_quality_weights: tuple[float, float, float, float] = (0.50, 0.20, 0.15, 0.15)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    postgres_url: SecretStr = SecretStr(
        "postgresql+asyncpg://prettylisa:local-development-only@localhost:5432/prettylisa"
    )
    valkey_url: SecretStr = SecretStr("redis://localhost:6379/0")
    dependency_timeout_seconds: float = Field(default=2, gt=0, le=30)
    postgres_pool_size: int = Field(default=5, ge=1)
    postgres_max_overflow: int = Field(default=5, ge=0)
    otp_hmac_secret: SecretStr = Field(
        default=SecretStr(DEVELOPMENT_OTP_HMAC_SECRET), min_length=32
    )
    otp_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    otp_request_cooldown_seconds: int = Field(default=60, ge=0, le=3600)
    otp_email_request_limit: int = Field(default=5, ge=1, le=100)
    otp_email_rate_window_seconds: int = Field(default=3600, ge=1, le=86400)
    otp_ip_request_limit: int = Field(default=20, ge=1, le=1000)
    otp_ip_rate_window_seconds: int = Field(default=3600, ge=1, le=86400)
    otp_max_verification_attempts: int = Field(default=5, ge=1, le=20)
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=2592000, ge=3600, le=31536000)
    support_smtp_password: SecretStr | None = None
    email_provider: Literal["timeweb"] = "timeweb"
    email_smtp_host: str = Field(default="smtp.timeweb.ru", min_length=1)
    email_smtp_port: int = Field(default=465, ge=1, le=65535)
    email_smtp_tls_mode: Literal["implicit_tls", "starttls"] = "implicit_tls"
    email_smtp_username: str = Field(default="auth@prettylisavpn.com", min_length=3)
    email_smtp_password: SecretStr | None = None
    email_from_address: str = Field(default="auth@prettylisavpn.com", min_length=3)
    email_from_name: str = Field(default="PrettyLisaVPN", min_length=1, max_length=100)
    email_connection_timeout_seconds: float = Field(default=5, gt=0, le=30)
    email_send_timeout_seconds: float = Field(default=10, gt=0, le=60)

    @field_validator("postgres_url")
    @classmethod
    def validate_postgres_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("POSTGRES_URL must use postgresql+asyncpg")
        return value

    @field_validator("valkey_url")
    @classmethod
    def validate_valkey_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("VALKEY_URL must use redis or rediss")
        return value

    @model_validator(mode="after")
    def validate_production_otp_secret(self) -> Self:
        if self.client_vpn_enabled and not self.fleet_enabled:
            raise ValueError("Client VPN requires the fleet worker")
        if self.fleet_enabled:
            tokens = (self.fleet_admin_token, self.fleet_monitor_token)
            if any(token is None or len(token.get_secret_value()) < 32 for token in tokens):
                raise ValueError("Fleet requires separate administrator and monitoring tokens")
            if self.fleet_admin_token == self.fleet_monitor_token:
                raise ValueError("Fleet administrator and monitoring tokens must differ")
        if (
            any(weight < 0 for weight in self.fleet_quality_weights)
            or abs(sum(self.fleet_quality_weights) - 1) > 0.000001
        ):
            raise ValueError("Fleet quality weights must be non-negative and sum to one")
        if self.billing_provider == "sandbox" and self.environment not in ("development", "test"):
            raise ValueError("Sandbox billing requires development or test environment")
        if (
            self.environment == "production"
            and self.otp_hmac_secret.get_secret_value() == DEVELOPMENT_OTP_HMAC_SECRET
        ):
            raise ValueError("OTP_HMAC_SECRET must be changed in production")
        if self.email_from_address != self.email_smtp_username:
            raise ValueError("EMAIL_FROM_ADDRESS must match EMAIL_SMTP_USERNAME for Timeweb")
        return self
