"""Short renewable Free reservations allow several devices to share the daily hour."""

import sqlalchemy as sa
from alembic import op

revision = "0034_short_free_reservations"
down_revision = "0033_fleet_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_wireguard_leases",
        sa.Column("quota_reserved_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "client_wireguard_leases",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Preserve already running sessions during upgrade, including sleeping phones.
    op.execute(
        "UPDATE client_wireguard_leases SET verified_at = activated_at "
        "WHERE status = 'READY' AND removed_at IS NULL"
    )


def downgrade() -> None:
    # Old workers reserve the whole expires_at interval; never erase short-grant
    # accounting while leases remain live. Stop issuance and confirm removal first.
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM client_wireguard_leases "
                "WHERE removed_at IS NULL AND quota_reserved_until IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Confirm short-reservation lease removal before downgrade")
    op.drop_column("client_wireguard_leases", "quota_reserved_until")
    op.drop_column("client_wireguard_leases", "verified_at")
