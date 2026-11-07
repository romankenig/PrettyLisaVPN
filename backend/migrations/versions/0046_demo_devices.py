"""Durable anonymous device quota principals; existing account budgets are unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0046_demo_devices"
down_revision = "0045_platega_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE subscription_plan ADD VALUE IF NOT EXISTS 'DEMO'")
    op.create_table(
        "demo_devices",
        sa.Column("identity_digest", sa.LargeBinary(32), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("installation_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_check_constraint(
        "ck_subscriptions_demo_no_auto_renew", "subscriptions", "plan <> 'DEMO' OR NOT auto_renew"
    )


def downgrade() -> None:
    # Dropping identity records would reset reinstall quotas. Explicit operator migration required.
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM demo_devices)")):
        raise RuntimeError(
            "DEMO identity and quota data must be retained; use a forward-compatible rollback"
        )
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM subscriptions WHERE plan = 'DEMO')")
    ):
        raise RuntimeError("DEMO subscriptions must be retained; use a compatible rollback")
    op.drop_constraint("ck_subscriptions_demo_no_auto_renew", "subscriptions", type_="check")
    op.drop_table("demo_devices")
    # Keep the PostgreSQL enum member, as with PLATINUM; an empty pre-activation rollback is safe.
