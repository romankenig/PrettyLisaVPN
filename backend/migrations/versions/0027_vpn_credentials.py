"""Durable OpenVPN credential issuance and revocation ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_vpn_credentials"
down_revision: str | None = "0026_sandbox_mandates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vpn_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("vpn_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "vpn_node_id",
            sa.Uuid(),
            sa.ForeignKey("vpn_nodes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("authority_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("certificate_pem", sa.LargeBinary()),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("node_removed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "authority_sha256 ~ '^[0-9a-f]{64}$'", name="ck_vpn_credentials_authority"
        ),
        sa.CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="ck_vpn_credentials_request"),
        sa.CheckConstraint("expires_at > created_at", name="ck_vpn_credentials_lifetime"),
        sa.CheckConstraint(
            "(certificate_pem IS NULL) = (issued_at IS NULL)", name="ck_vpn_credentials_issuance"
        ),
        sa.CheckConstraint(
            "certificate_pem IS NULL OR octet_length(certificate_pem) BETWEEN 1 AND 16384",
            name="ck_vpn_credentials_certificate_size",
        ),
        sa.CheckConstraint(
            "issued_at IS NULL OR (issued_at >= created_at AND issued_at < expires_at)",
            name="ck_vpn_credentials_issued_time",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at", name="ck_vpn_credentials_revoked_time"
        ),
        sa.CheckConstraint(
            "node_removed_at IS NULL OR (revoked_at IS NOT NULL AND node_removed_at >= revoked_at)",
            name="ck_vpn_credentials_removal",
        ),
    )
    op.create_index("ix_vpn_credentials_session", "vpn_credentials", ["session_id"])
    op.create_index(
        "ix_vpn_credentials_authority", "vpn_credentials", ["vpn_node_id", "authority_sha256"]
    )
    op.create_index(
        "ix_vpn_credentials_pending_revocation",
        "vpn_credentials",
        ["vpn_node_id"],
        postgresql_where=sa.text("revoked_at IS NOT NULL AND node_removed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("vpn_credentials")
