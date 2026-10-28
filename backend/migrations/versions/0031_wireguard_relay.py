"""Explicit node groups and durable WireGuard relay reservations."""

import sqlalchemy as sa
from alembic import op

revision = "0031_wireguard_relay"
down_revision = "0030_client_wireguard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fleet_nodes", sa.Column("group", sa.String(16), nullable=True))
    op.execute(
        'UPDATE fleet_nodes SET "group" = '
        "CASE WHEN is_available_for_free THEN 'FREE' ELSE 'PREMIUM' END"
    )
    op.alter_column("fleet_nodes", "group", nullable=False)
    op.create_check_constraint(
        "ck_fleet_node_group", "fleet_nodes", "\"group\" IN ('INTERMEDIATE','FREE','PREMIUM')"
    )
    op.create_check_constraint(
        "ck_fleet_node_group_access", "fleet_nodes", "is_available_for_free = (\"group\" = 'FREE')"
    )
    op.add_column(
        "client_wireguard_leases",
        sa.Column("method", sa.String(32), nullable=False, server_default="wireguard"),
    )
    op.add_column(
        "client_wireguard_leases",
        sa.Column(
            "relay_node_id",
            sa.UUID(),
            sa.ForeignKey("fleet_nodes.id", name="fk_client_lease_relay"),
        ),
    )
    op.add_column("client_wireguard_leases", sa.Column("relay_port", sa.Integer()))
    op.create_check_constraint(
        "ck_client_lease_relay",
        "client_wireguard_leases",
        "(method = 'wireguard' AND relay_node_id IS NULL AND relay_port IS NULL) OR "
        "(method = 'wireguard_relay' AND relay_node_id IS NOT NULL AND relay_port IS NOT NULL "
        "AND relay_port BETWEEN 20000 AND 29999 AND relay_node_id <> node_id)",
    )
    op.create_index(
        "uq_client_lease_relay_port",
        "client_wireguard_leases",
        ["relay_node_id", "relay_port"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL AND relay_node_id IS NOT NULL"),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM client_wireguard_leases "
            "WHERE relay_node_id IS NOT NULL AND removed_at IS NULL"
        )
    ):
        raise RuntimeError("Confirm removal of all relay accesses before downgrade")
    # An old backend must never expose an intermediate as a paid exit node.
    op.execute("UPDATE fleet_nodes SET enabled = false WHERE \"group\" = 'INTERMEDIATE'")
    op.drop_index("uq_client_lease_relay_port", "client_wireguard_leases")
    op.drop_constraint("ck_client_lease_relay", "client_wireguard_leases")
    op.drop_constraint("fk_client_lease_relay", "client_wireguard_leases", type_="foreignkey")
    for column in ("relay_port", "relay_node_id", "method"):
        op.drop_column("client_wireguard_leases", column)
    op.drop_constraint("ck_fleet_node_group_access", "fleet_nodes")
    op.drop_constraint("ck_fleet_node_group", "fleet_nodes")
    op.drop_column("fleet_nodes", "group")
