"""Email delivery port and application-facing errors."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class OutboundEmail(BaseModel):
    model_config = ConfigDict(frozen=True)

    recipient: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    text_body: str = Field(min_length=1, repr=False)
    html_body: str = Field(min_length=1, repr=False)


class EmailProvider(Protocol):
    async def send(self, email: OutboundEmail) -> None: ...


class EmailDeliveryError(RuntimeError):
    """Base error exposed by email infrastructure to application services."""


class EmailAuthenticationError(EmailDeliveryError):
    """The provider rejected configured credentials."""


class EmailRecipientRejectedError(EmailDeliveryError):
    """The provider rejected the recipient."""


class EmailProviderUnavailableError(EmailDeliveryError):
    """The provider could not complete delivery within configured bounds."""


class EmailProviderConfigurationError(EmailDeliveryError):
    """Email provider configuration is incomplete or inconsistent."""
