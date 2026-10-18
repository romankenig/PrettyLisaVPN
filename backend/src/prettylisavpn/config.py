"""Environment configuration. Secrets are redacted in model representations."""

from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_OTP_HMAC_SECRET = "local-development-otp-hmac-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    application_name: str = Field(default="PrettyLisaVPN", min_length=1)
    application_version: str = Field(default="0.8.0", min_length=1)
    environment: str = Field(default="development", min_length=1)
    billing_provider: Literal["disabled", "sandbox"] = "disabled"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    postgres_url: SecretStr = SecretStr(
        "postgresql+asyncpg://prettylisa:local-development-only@localhost:5432/prettylisa"
    )
    valkey_url: SecretStr = SecretStr("redis://localhost:6379/0")
    dependency_timeout_seconds: float = Field(default=2, gt=0, le=30)
    postgres_pool_size: int = Field(default=5, ge=1)
    postgres_max_overflow: int = Field(default=5, ge=0)
    vpn_node_stale_timeout_seconds: int = Field(default=90, ge=10, le=3600)
    vpn_client_subnet: IPv4Network = IPv4Network("10.77.0.0/16")
    vpn_client_gateway_ipv4: IPv4Address = IPv4Address("10.77.0.1")
    vpn_client_dns: list[IPv4Address] = Field(
        default_factory=lambda: [IPv4Address("1.1.1.1"), IPv4Address("1.0.0.1")],
        min_length=1,
    )
    vpn_client_allowed_ips: list[IPv4Network] = Field(
        default_factory=lambda: [IPv4Network("0.0.0.0/0")], min_length=1
    )
    vpn_node_health_poll_interval_seconds: int = Field(default=30, ge=5, le=600)
    vpn_session_reconcile_interval_seconds: int = Field(default=15, ge=1, le=300)
    vpn_node_agent_port: int = Field(default=8443, ge=1, le=65535)
    vpn_node_agent_auth_token: SecretStr | None = Field(default=None, min_length=32)
    vpn_node_agent_tls_ca: Path | None = None
    vpn_node_agent_tls_client_certificate: Path | None = None
    vpn_node_agent_tls_client_key: Path | None = None
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
        if self.billing_provider == "sandbox" and self.environment not in ("development", "test"):
            raise ValueError("Sandbox billing requires development or test environment")
        if self.vpn_client_subnet.version != 4:
            raise ValueError("VPN_CLIENT_SUBNET must be IPv4")
        if any(address.version != 4 for address in self.vpn_client_dns):
            raise ValueError("VPN_CLIENT_DNS must contain only IPv4 addresses")
        if any(network.version != 4 for network in self.vpn_client_allowed_ips):
            raise ValueError("VPN_CLIENT_ALLOWED_IPS must contain only IPv4 networks")
        if self.vpn_client_allowed_ips != [IPv4Network("0.0.0.0/0")]:
            raise ValueError("VPN_CLIENT_ALLOWED_IPS must be the IPv4 full-tunnel route")
        if self.vpn_client_gateway_ipv4 not in self.vpn_client_subnet.hosts():
            raise ValueError(
                "VPN_CLIENT_GATEWAY_IPV4 must be a usable address in VPN_CLIENT_SUBNET"
            )
        if (
            self.environment == "production"
            and self.otp_hmac_secret.get_secret_value() == DEVELOPMENT_OTP_HMAC_SECRET
        ):
            raise ValueError("OTP_HMAC_SECRET must be changed in production")
        if self.email_from_address != self.email_smtp_username:
            raise ValueError("EMAIL_FROM_ADDRESS must match EMAIL_SMTP_USERNAME for Timeweb")
        agent_credentials = (
            self.vpn_node_agent_auth_token,
            self.vpn_node_agent_tls_ca,
            self.vpn_node_agent_tls_client_certificate,
            self.vpn_node_agent_tls_client_key,
        )
        if any(value is not None for value in agent_credentials) and not all(
            value is not None for value in agent_credentials
        ):
            raise ValueError("VPN node agent mTLS and token settings must be configured together")
        if self.vpn_node_health_poll_interval_seconds >= self.vpn_node_stale_timeout_seconds:
            raise ValueError("VPN node health poll interval must be shorter than stale timeout")
        return self

    def vpn_node_agent_is_configured(self) -> bool:
        return self.vpn_node_agent_auth_token is not None
