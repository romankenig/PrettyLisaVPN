"""Durable simulated reusable-payment authorities and their revocation.

Revision ID: 0026_sandbox_mandates
Revises: 0025_billing_sandbox
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_sandbox_mandates"
down_revision: str | None = "0025_billing_sandbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_sandbox_mandates",
        sa.Column("reference", sa.String(200), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED')", name="ck_billing_sandbox_mandates_status"
        ),
    )
    # Recover authorities from the already committed 0.8.0 provider receipts,
    # including an accepted result awaiting local settlement after a crash.
    # This reconstructs simulated state only; it does not create real mandates.
    op.execute("""INSERT INTO billing_sandbox_mandates (reference, user_id, status)
        SELECT DISTINCT p.result->'mandate'->>'reference', o.user_id,
          CASE WHEN EXISTS (
            SELECT 1 FROM billing_sandbox_payments n
            JOIN billing_operations no ON no.id = n.operation_id
            WHERE no.provider_name = 'development-sandbox-v1'
              AND n.result->>'status' = 'SUCCEEDED'
              AND n.request->>'previous_mandate_reference' = p.result->'mandate'->>'reference'
              AND n.result->>'previous_mandate_revoked' = 'true'
              AND (n.result->'mandate'->>'reference')
                  IS DISTINCT FROM (p.result->'mandate'->>'reference')
          ) THEN 'REVOKED' ELSE 'ACTIVE' END
        FROM billing_sandbox_payments p
        JOIN billing_operations o ON o.id = p.operation_id
        WHERE o.provider_name = 'development-sandbox-v1'
          AND p.result->>'status' = 'SUCCEEDED'
          AND p.result->'mandate'->>'reference' IS NOT NULL""")


def downgrade() -> None:
    op.drop_table("billing_sandbox_mandates")
