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
    application_version: str = Field(default="0.1.0", min_length=1)
    environment: str = Field(default="development", min_length=1)
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
        if (
            self.environment == "production"
            and self.otp_hmac_secret.get_secret_value() == DEVELOPMENT_OTP_HMAC_SECRET
        ):
            raise ValueError("OTP_HMAC_SECRET must be changed in production")
        return self
