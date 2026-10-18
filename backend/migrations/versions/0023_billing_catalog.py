"""Account-group scheduled offers and immutable subscription contract prices.

Revision ID: 0023_billing_catalog
Revises: 0022_free_quota_platinum
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0023_billing_catalog"
down_revision: str | None = "0022_free_quota_platinum"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    groups = op.create_table("client_groups", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False))
    group_id = UUID("e3a7f90a-983a-4d5d-8f93-4d536e00be01")
    op.bulk_insert(groups, [{"id": group_id, "name": "Default"}])
    op.create_table("client_group_memberships",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("client_groups.id"), nullable=False))
    op.create_index("ix_client_group_memberships_group_id", "client_group_memberships", ["group_id"])
    catalog = op.create_table(
        "billing_catalog",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Uuid(), nullable=False),
        sa.Column("document", JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_billing_catalog_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Temporary working prices explicitly authorized by the owner, not client fallbacks.
    op.bulk_insert(catalog, [{"id": 1, "revision": UUID("8e6278f5-286a-4a56-9ab4-cf877d4e3446"), "document": {
        "schema_version": 1, "entries": [{"group_id": str(group_id), "valid_from": "2026-01-01T00:00:00Z", "valid_to": None,
            "offer": {"id": "eb54867b-5954-4b07-9690-560d4fbd4155", "plan": "PREMIUM", "period": "MONTH", "prices": {
                "RUB": {"amount_minor": 19900, "original_amount_minor": 29900},
                "USD": {"amount_minor": 299, "original_amount_minor": 399}}}}]}}])
    op.create_table("subscription_prices",
        sa.Column("subscription_id", sa.Uuid(), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("client_groups.id"), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=False), sa.Column("catalog_revision", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0 AND amount_minor <= 1000000000000", name="ck_subscription_prices_amount"),
        sa.CheckConstraint("currency IN ('RUB', 'USD')", name="ck_subscription_prices_currency"))
    op.execute("""CREATE FUNCTION billing_price_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Subscription contract price is immutable'; END $$""")
    op.execute("""CREATE TRIGGER subscription_price_no_update BEFORE UPDATE ON subscription_prices
        FOR EACH ROW EXECUTE FUNCTION billing_price_immutable()""")


def downgrade() -> None:
    op.drop_table("subscription_prices")
    op.execute("DROP FUNCTION billing_price_immutable()")
    op.drop_table("billing_catalog")
    op.drop_index("ix_client_group_memberships_group_id", table_name="client_group_memberships")
    op.drop_table("client_group_memberships")
    op.drop_table("client_groups")
