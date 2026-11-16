"""Pure shared-contract and SemVer acceptance tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from prettylisavpn.account_messages.domain import Content, MessageContext, Publication
from prettylisavpn.account_messages.version import Version


def document(**changes):
    return {
        "id": str(uuid4()),
        "revision": 1,
        "redisplay_after_ack": False,
        "platforms": {"WINDOWS": {"min_version": "0.8.0"}, "ANDROID": {"min_version": "0.1.0"}},
        "default_locale": "ru",
        "localizations": {
            "ru": {
                "title": "новости PrettyLisaVPN",
                "fallback_text": "текст",
                "blocks": [{"type": "paragraph", "text": "<b>это текст</b>"}],
                "primary_action": {"type": "OPEN_SETTINGS", "label": "настройки"},
            }
        },
        **changes,
    }


@pytest.mark.parametrize(
    "value", ["1", "01.0.0", "1.0.0-01", "1.0.0+", "v1.0.0", "1.2.3.4", "1.0.0-", " 1.0.0"]
)
def test_semver_rejects_invalid_identifiers(value):
    with pytest.raises(ValueError):
        Version.parse(value)


def test_semver_uses_precedence_and_ignores_build_metadata():
    ordered = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
        "1.0.1",
        "1.10.0",
    ]
    parsed = [Version.parse(value) for value in ordered]
    assert all(left < right for left, right in zip(parsed, parsed[1:], strict=False))
    assert Version.parse("1.0.0+windows.999") == Version.parse("1.0.0+android.1")


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": True},
        {"revision": 0},
        {"redisplay_after_ack": "false"},
        {"platforms": {}},
        {"user_ids": []},
        {"localizations": []},
        {"default_locale": "missing"},
        {"platforms": {"WINDOWS": {"min_version": "1.0.0", "max_version_exclusive": "0.9.0"}}},
        {"starts_at": "2026-10-18T00:00:00"},
        {"starts_at": datetime.now(UTC), "expires_at": datetime.now(UTC) - timedelta(days=1)},
    ],
)
def test_rejects_invalid_publications(changes):
    with pytest.raises(ValidationError):
        Publication.model_validate(document(**changes))


@pytest.mark.parametrize(
    "content",
    [
        {"blocks": [{"type": "html", "text": "<script>bad</script>"}]},
        {"primary_action": {"type": "OPEN_URL", "label": "visit", "url": "https://example.test"}},
        {"primary_action": {"type": "OPEN_SETTINGS", "label": "ok", "path": "/arbitrary"}},
        {"title": " "},
        {"title": "😀" * 61},
        {"blocks": [{"type": "list", "items": [" "]}]},
    ],
)
def test_rejects_executable_unknown_or_client_incompatible_content(content):
    payload = document()
    payload["localizations"]["ru"].update(content)
    with pytest.raises(ValidationError):
        Publication.model_validate(payload)


def test_localization_text_and_literal_html_are_preserved():
    payload = document()
    payload["localizations"]["en"] = {**payload["localizations"]["ru"], "title": "English"}
    pub = Publication.model_validate(payload)
    assert pub.localized("ru-ru").blocks[0].text == "<b>это текст</b>"
    assert pub.localized("en-us").title == "English"
    assert pub.localized("fr-fr").title == "новости PrettyLisaVPN"
    assert (
        MessageContext(
            platform="WINDOWS", app_version="0.8.0", locale="ru-RU", schema_version="1"
        ).locale
        == "ru-ru"
    )


def test_multibyte_payload_budget_is_checked_before_publication():
    text = "字" * 3000
    payload = document()
    payload["localizations"]["ru"]["blocks"] = [{"type": "paragraph", "text": text}] * 12
    with pytest.raises(ValidationError):
        Publication.model_validate(payload)


def test_content_limits_match_contract():
    assert (
        Content(
            title="x", blocks=[{"type": "list", "items": ["one"]}], fallback_text="one"
        ).dismiss_label
        == "понятно"
    )
    payload = document()
    payload["localizations"] = {
        "ru": payload["localizations"]["ru"],
        "RU": payload["localizations"]["ru"],
    }
    with pytest.raises(ValidationError):
        Publication.model_validate(payload)


def mandatory_document(**changes):
    value = document(schema_version=2, dismissible=False, **changes)
    value["localizations"]["ru"]["primary_action"] = None
    value["localizations"]["ru"]["links"] = [
        {"label": "обновить", "url": "https://prettylisavpn.com/download#latest"}
    ]
    return value


def test_v2_mandatory_contract_and_v1_compatibility():
    publication = Publication.model_validate(mandatory_document())
    assert publication.localized("ru").dismissible is False
    assert len(publication.localized("ru").links) == 1
    assert Publication.model_validate(document()).dismissible is True
    assert MessageContext(platform="IOS", app_version="1.0.0", schema_version=2)
    legacy = Publication.model_validate(document())
    stored = legacy.storage_payload()
    assert "dismissible" not in stored
    assert "links" not in stored["localizations"]["ru"]
    assert Publication.model_validate(stored) == legacy
    assert publication.storage_payload()["dismissible"] is False


@pytest.mark.parametrize("change", ["v1", "no_link", "internal_action", "not_boolean"])
def test_mandatory_requires_v2_explicit_boolean_and_external_exit_path(change):
    payload = mandatory_document()
    if change == "v1":
        payload["schema_version"] = 1
    elif change == "no_link":
        payload["localizations"]["ru"]["links"] = []
    elif change == "internal_action":
        payload["localizations"]["ru"]["primary_action"] = {"type": "OPEN_ABOUT", "label": "about"}
    else:
        payload["dismissible"] = "false"
    with pytest.raises(ValidationError):
        Publication.model_validate(payload)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "javascript:alert(1)",
        "file:///tmp/x",
        "https://user@example.com",
        "https://@example.com",
        "https://example.com:8443",
        "https://example.com\\@evil.com",
        "https://example.com/\n",
        "https:///missing",
        "https://example.com/" + "a" * 2048,
    ],
)
def test_message_links_reject_unsafe_urls(url):
    payload = mandatory_document()
    payload["localizations"]["ru"]["links"][0]["url"] = url
    with pytest.raises(ValidationError):
        Publication.model_validate(payload)
