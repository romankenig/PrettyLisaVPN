from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from prettylisavpn.users.domain import User, UserStatus, normalize_email
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService


def test_normalize_email_trims_and_casefolds():
    assert normalize_email("  Lisa.Example@Example.COM\t") == "lisa.example@example.com"


def test_user_rejects_naive_timestamps():
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        User(
            id=uuid4(),
            email="lisa@example.com",
            status=UserStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(UTC),
        )


async def test_service_creates_normalized_active_user():
    repository = AsyncMock(spec=UserRepository)
    repository.add.side_effect = lambda user: user

    user = await UserService(repository).create("  Lisa@Example.COM ")

    assert isinstance(user, User)
    assert user.email == "lisa@example.com"
    assert user.status is UserStatus.ACTIVE
    assert user.created_at == user.updated_at
    assert user.created_at.tzinfo is UTC
    repository.add.assert_awaited_once_with(user)
