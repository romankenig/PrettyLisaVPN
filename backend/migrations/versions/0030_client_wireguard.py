"""Customer WireGuard leases and confirmed-removal quota accounting."""

import sqlalchemy as sa
from alembic import op

revision = "0030_client_wireguard"
down_revision = "0029_fleet_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_wireguard_leases",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", sa.UUID(), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("auth_session_id", sa.UUID(), sa.ForeignKey("auth_sessions.id"), nullable=False),
        sa.Column("node_id", sa.UUID(), sa.ForeignKey("fleet_nodes.id"), nullable=False),
        sa.Column("country", sa.String(4), nullable=False),
        sa.Column("public_key", sa.String(44), nullable=False),
        sa.Column("address", sa.String(18), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("is_free", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_token", sa.UUID()),
        sa.Column("claim_until", sa.DateTime(timezone=True)),
        sa.Column("code", sa.String(64)),
        sa.UniqueConstraint("user_id", "request_id", name="uq_client_lease_request"),
        sa.CheckConstraint(
            "status IN ('PROVISIONING','READY','REVOKING','CLOSED')", name="ck_client_lease_status"
        ),
    )
    for name, columns in (
        ("device", ["device_id"]),
        ("key", ["public_key"]),
        ("address", ["node_id", "address"]),
    ):
        op.create_index(
            "uq_client_lease_" + name,
            "client_wireguard_leases",
            columns,
            unique=True,
            postgresql_where=sa.text("removed_at IS NULL"),
        )
    op.create_index(
        "ix_client_lease_due",
        "client_wireguard_leases",
        ["next_attempt_at"],
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_index("ix_client_lease_quota", "client_wireguard_leases", ["user_id", "created_at"])


def downgrade() -> None:
    # Operators must disable grants and confirm all node peers removed before downgrade.
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT count(*) FROM client_wireguard_leases WHERE removed_at IS NULL")
    ):
        raise RuntimeError("Remove all customer WireGuard peers before downgrade")
    op.drop_table("client_wireguard_leases")
