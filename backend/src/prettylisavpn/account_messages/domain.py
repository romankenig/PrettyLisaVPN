"""Validated shared JSON v1 contract and operator publication document."""

import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    ValidationInfo,
    field_validator,
    model_validator,
)

from prettylisavpn.account_messages.version import Version
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.subscriptions.domain import SubscriptionPlan

MAX_RESPONSE_BYTES = 65536
_LOCALE = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8}){0,7}")


def normalize_locale(value: str) -> str:
    if len(value) > 63 or _LOCALE.fullmatch(value) is None:
        raise ValueError("Invalid locale")
    return value.lower()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


def visible_text(value: str, limit: int) -> str:
    # Windows limits count UTF-16 code units; enforce the same rule for emoji too.
    if not value.strip() or len(value.encode("utf-16-le")) // 2 > limit:
        raise ValueError("Invalid display text")
    return value


class Paragraph(StrictModel):
    type: Literal["paragraph"]
    text: str = Field(min_length=1, max_length=3000)

    @field_validator("text")
    @classmethod
    def display_text(cls, value: str) -> str:
        return visible_text(value, 3000)


class TextList(StrictModel):
    type: Literal["list"]
    items: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        min_length=1, max_length=12
    )

    @field_validator("items")
    @classmethod
    def display_items(cls, value: list[str]) -> list[str]:
        return [visible_text(item, 500) for item in value]


class PrimaryAction(StrictModel):
    type: Literal["OPEN_SUBSCRIPTION", "OPEN_SETTINGS", "OPEN_ABOUT"]
    label: str = Field(min_length=1, max_length=60)

    @field_validator("label")
    @classmethod
    def display_label(cls, value: str) -> str:
        return visible_text(value, 60)


class Content(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    blocks: list[Annotated[Paragraph | TextList, Field(discriminator="type")]] = Field(
        min_length=1, max_length=12
    )
    fallback_text: str = Field(min_length=1, max_length=4000)
    primary_action: PrimaryAction | None = None
    dismiss_label: str = Field(default="понятно", min_length=1, max_length=60)

    @field_validator("title", "fallback_text", "dismiss_label")
    @classmethod
    def display_text(cls, value: str, info: ValidationInfo) -> str:
        limits = {"title": 120, "fallback_text": 4000, "dismiss_label": 60}
        return visible_text(value, limits[str(info.field_name)])


class MessageResponse(Content):
    id: UUID
    revision: int = Field(strict=True, gt=0, le=2147483647)
    kind: Literal["announcement", "update", "promotion"]
    expires_at: datetime | None


class MessagesResponse(StrictModel):
    schema_version: Literal[1] = 1
    messages: list[MessageResponse]


class Acknowledgement(StrictModel):
    revision: int = Field(strict=True, gt=0, le=2147483647)


class Receipt(Acknowledgement):
    id: UUID
    acknowledged: Literal[True] = True


class VersionRange(StrictModel):
    min_version: str = Field(max_length=100)
    max_version_exclusive: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        minimum = Version.parse(self.min_version)
        if self.max_version_exclusive is not None:
            if Version.parse(self.max_version_exclusive) <= minimum:
                raise ValueError("Empty version range")
        return self

    def contains(self, value: str) -> bool:
        parsed = Version.parse(value)
        return parsed >= Version.parse(self.min_version) and (
            self.max_version_exclusive is None or parsed < Version.parse(self.max_version_exclusive)
        )


class PublicationReceipt(StrictModel):
    id: UUID
    revision: int
    published: Literal[True] = True


class MessageContext(StrictModel):
    platform: DevicePlatform
    app_version: str = Field(max_length=100)
    locale: str = Field(default="ru-RU", max_length=63)
    schema_version: int = Field(default=1, ge=1, le=1)

    @field_validator("app_version")
    @classmethod
    def semver(cls, value: str) -> str:
        Version.parse(value)
        return value

    @field_validator("locale")
    @classmethod
    def locale_tag(cls, value: str) -> str:
        return normalize_locale(value)


class Publication(StrictModel):
    id: UUID
    revision: int = Field(strict=True, gt=0, le=2147483647)
    schema_version: int = Field(default=1, strict=True, ge=1, le=1)
    kind: Literal["announcement", "update", "promotion"] = "announcement"
    redisplay_after_ack: StrictBool
    priority: int = Field(default=0, strict=True, ge=-10000, le=10000)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    user_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=5000)
    plans: list[SubscriptionPlan] | None = Field(default=None, min_length=1, max_length=2)
    platforms: dict[DevicePlatform, VersionRange] = Field(min_length=1, max_length=7)
    default_locale: str = "ru"
    localizations: dict[str, Content] = Field(min_length=1, max_length=10)

    @field_validator("starts_at", "expires_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Timezone is required")
            return value.astimezone(UTC)
        return value

    @field_validator("localizations", mode="before")
    @classmethod
    def locale_keys(cls, value: Any) -> dict[str, object]:
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError("Expected locale mapping")
        normalized = {normalize_locale(key): content for key, content in value.items()}
        if len(normalized) != len(value):
            raise ValueError("Duplicate normalized locale")
        return normalized

    @field_validator("default_locale")
    @classmethod
    def default_tag(cls, value: str) -> str:
        return normalize_locale(value)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.default_locale not in self.localizations:
            raise ValueError("Missing default localization")
        if self.starts_at and self.expires_at and self.starts_at >= self.expires_at:
            raise ValueError("Empty publication interval")
        for content in self.localizations.values():
            if encoded_size(self.response(content)) > 60000:
                raise ValueError("Localized message exceeds response budget")
        return self

    def response(self, content: Content) -> MessageResponse:
        return MessageResponse(
            **content.model_dump(),
            id=self.id,
            revision=self.revision,
            kind=self.kind,
            expires_at=self.expires_at,
        )

    def localized(self, locale: str) -> MessageResponse:
        key = next(
            (
                key
                for key in (locale, locale.split("-")[0], self.default_locale)
                if key in self.localizations
            ),
            self.default_locale,
        )
        return self.response(self.localizations[key])


def encoded_size(value: BaseModel) -> int:
    return len(
        json.dumps(
            value.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
