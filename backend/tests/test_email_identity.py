"""Confirmed domain aliases preserve delivery addresses and isolate unrelated mailboxes."""

from unittest.mock import AsyncMock

import pytest
from test_otp import settings

from prettylisavpn.otp import OtpService
from prettylisavpn.users.email_identity import DOMAIN_GROUPS, email_aliases, email_identity


@pytest.mark.parametrize("domains", DOMAIN_GROUPS)
def test_confirmed_provider_domains_share_one_case_insensitive_identity(domains):
    expected = f"member@{domains[0]}"
    for domain in domains:
        assert email_identity(f"  MemBER@{domain.upper()}  ") == expected
        assert set(email_aliases(f"member@{domain}")) == {f"member@{item}" for item in domains}


@pytest.mark.parametrize(
    "first,second",
    [
        ("member@example.com", "member@example.ru"),
        ("member@hotmail.com", "member@outlook.com"),
        ("member@yahoo.com", "member@ymail.com"),
        ("member@mail.ru", "member@bk.ru"),
        ("member@icloud.com", "member@me.com"),
        ("member@aol.com", "member@aim.com"),
        ("member@gmx.com", "member@gmx.de"),
        ("member@zoho.com", "member@zohomail.com"),
        ("member@qq.com", "member@foxmail.com"),
        ("member@yandex.ru.evil.test", "member@yandex.ru"),
        ("member@yandex.com.tr", "member@yandex.com"),
        ("member@proton.me.evil.test", "member@proton.me"),
        ("member+one@gmail.com", "member@gmail.com"),
        ("first.last@gmail.com", "firstlast@gmail.com"),
    ],
)
def test_no_guessing_tlds_custom_aliases_or_local_part_changes(first, second):
    assert email_identity(first) != email_identity(second)


async def test_aliases_share_challenge_cooldown_rate_limit_attempts_and_consumption():
    redis = AsyncMock()
    redis.eval.return_value = 1
    service = OtpService(redis, settings())
    issued = await service.request("Member@Yandex.COM", "192.0.2.1")
    issue = redis.eval.await_args.args
    assert issued
    await service.verify("member@ya.ru", issued.code)
    verify = redis.eval.await_args.args
    assert issue[2] == verify[2]
    assert issue[6] == verify[3]
    await service.discard("member@yandex.by")
    redis.delete.assert_awaited_once_with(issue[2])
    await service.request("member@yandex.kz", "192.0.2.1")
    assert redis.eval.await_args.args[2:6] == issue[2:6]
