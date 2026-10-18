"""Durable billing admission, provider reconciliation and append-only contracts.

Revision ID: 0024_billing_operations
Revises: 0023_billing_catalog
"""

from collections.abc import Sequence
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision: str = "0024_billing_operations"
down_revision: str | None = "0023_billing_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("billing_contracts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("client_groups.id"), nullable=False),
        sa.Column("catalog_revision", sa.Uuid(), nullable=False), sa.Column("offer_document", JSONB(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0 AND amount_minor <= 1000000000000", name="ck_billing_contracts_amount"),
        sa.CheckConstraint("currency IN ('RUB', 'USD')", name="ck_billing_contracts_currency"))
    op.execute("CREATE TRIGGER billing_contract_no_update BEFORE UPDATE ON billing_contracts FOR EACH ROW EXECUTE FUNCTION billing_price_immutable()")
    op.create_table("billing_accounts",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("contract_id", sa.Uuid(), sa.ForeignKey("billing_contracts.id")),
        sa.Column("provider_name", sa.String(64)), sa.Column("mandate_reference", sa.String(200)), sa.Column("method_label", sa.String(100)))
    op.create_table("billing_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False), sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("command", JSONB(), nullable=False), sa.Column("quote", JSONB(), nullable=False),
        sa.Column("provider_name", sa.String(64), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("redirect_url", sa.String(2048)), sa.Column("claim_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)), sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("last_error", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "request_id", name="uq_billing_operations_user_request"),
        sa.CheckConstraint("status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'CANCELED')", name="ck_billing_operations_status"))
    op.create_index("uq_billing_operations_user_pending", "billing_operations", ["user_id"], unique=True, postgresql_where=sa.text("status = 'PENDING'"))
    op.create_index("ix_billing_operations_retry", "billing_operations", ["next_attempt_at"], postgresql_where=sa.text("status = 'PENDING'"))
    op.execute("""CREATE FUNCTION billing_operation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (NEW.id, NEW.user_id, NEW.request_id, NEW.fingerprint, NEW.command, NEW.quote, NEW.provider_name, NEW.created_at)
            IS DISTINCT FROM (OLD.id, OLD.user_id, OLD.request_id, OLD.fingerprint, OLD.command, OLD.quote, OLD.provider_name, OLD.created_at)
            OR (OLD.status <> 'PENDING' AND NEW IS DISTINCT FROM OLD) THEN
            RAISE EXCEPTION 'Billing identity, quote and terminal results are immutable';
          END IF;
          RETURN NEW;
        END $$""")
    op.execute("CREATE TRIGGER billing_operation_guard BEFORE UPDATE ON billing_operations FOR EACH ROW EXECUTE FUNCTION billing_operation_guard()")


def downgrade() -> None:
    op.drop_table("billing_operations")
    op.execute("DROP FUNCTION billing_operation_guard()")
    op.drop_table("billing_accounts")
    op.drop_table("billing_contracts")
