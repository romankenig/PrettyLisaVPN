"""Application service for user operations."""

from datetime import UTC, datetime
from uuid import uuid4

from prettylisavpn.subscriptions.domain import Subscription
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.domain import User, UserStatus, normalize_email
from prettylisavpn.users.repository import UserRepository


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        subscription_repository: SubscriptionRepository,
    ) -> None:
        self._repository = repository
        self._subscription_repository = subscription_repository

    async def create(self, email: str) -> User:
        now = datetime.now(UTC)
        user = User(
            id=uuid4(),
            email=normalize_email(email),
            status=UserStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        persisted = await self._repository.add(user)
        await self._subscription_repository.add(Subscription.new_free(persisted.id, now))
        return persisted

    async def find_or_create_with_subscription(self, email: str) -> tuple[User, Subscription, bool]:
        normalized_email = normalize_email(email)
        await self._repository.lock_identity(normalized_email)
        user = await self._repository.get_by_email_for_update(normalized_email)
        created = user is None
        if user is None:
            now = datetime.now(UTC)
            user = await self._repository.add(
                User(
                    id=uuid4(),
                    email=normalized_email,
                    status=UserStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )

        subscription = await self._subscription_repository.get_by_user_id(user.id)
        if subscription is None:
            subscription = await self._subscription_repository.add(
                Subscription.new_free(user.id, datetime.now(UTC))
            )
        return user, subscription, created
