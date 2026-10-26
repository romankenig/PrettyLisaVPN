"""Bounded managed VPN authorizations and durable revocation acknowledgements."""

import sqlalchemy as sa
from alembic import op

revision = "0028_managed_vpn_leases"
down_revision = "0027_vpn_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vpn_managed_leases",
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("vpn_sessions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("node_removed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("expires_at > created_at", name="ck_managed_lease_lifetime"),
        sa.CheckConstraint(
            "node_removed_at IS NULL OR revoked_at IS NOT NULL", name="ck_managed_lease_removal"
        ),
    )


def downgrade() -> None:
    op.drop_table("vpn_managed_leases")
