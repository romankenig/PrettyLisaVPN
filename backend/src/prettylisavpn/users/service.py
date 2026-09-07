"""Application service for user operations."""

from datetime import UTC, datetime
from uuid import uuid4

from prettylisavpn.users.domain import User, UserStatus, normalize_email
from prettylisavpn.users.repository import UserRepository


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def create(self, email: str) -> User:
        now = datetime.now(UTC)
        user = User(
            id=uuid4(),
            email=normalize_email(email),
            status=UserStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.add(user)
