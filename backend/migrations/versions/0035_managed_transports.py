"""Managed transports share customer admission, quota and durable cleanup."""

import sqlalchemy as sa
from alembic import op

revision = "0035_managed_transports"
down_revision = "0034_short_free_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_wireguard_leases", sa.Column("engine_port", sa.Integer(), nullable=True))
    op.alter_column(
        "client_wireguard_leases", "address", existing_type=sa.String(18), nullable=True
    )
    op.drop_constraint("ck_client_lease_relay", "client_wireguard_leases", type_="check")
    op.create_check_constraint(
        "ck_client_lease_relay",
        "client_wireguard_leases",
        "(right(method, 6) <> '_relay' AND relay_node_id IS NULL AND relay_port IS NULL) OR "
        "(right(method, 6) = '_relay' AND relay_node_id IS NOT NULL AND relay_port IS NOT NULL "
        "AND relay_port BETWEEN 20000 AND 29999 AND relay_node_id <> node_id)",
    )
    op.create_check_constraint(
        "ck_client_lease_engine",
        "client_wireguard_leases",
        "(method IN ('wireguard','wireguard_relay') AND address IS NOT NULL "
        "AND engine_port IS NULL) OR "
        "(method NOT IN ('wireguard','wireguard_relay') AND address IS NULL "
        "AND engine_port BETWEEN 40000 AND 49899 AND engine_port IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_client_lease_method",
        "client_wireguard_leases",
        "method IN ('wireguard','wireguard_relay','vless_reality','vless_reality_relay',"
        "'amneziawg','amneziawg_relay','vless','vless_relay','vmess','vmess_relay',"
        "'shadowsocks2022','shadowsocks2022_relay','hysteria2','hysteria2_relay',"
        "'hysteria2_salamander','hysteria2_salamander_relay')",
    )
    op.create_index(
        "uq_client_lease_engine_port",
        "client_wireguard_leases",
        ["node_id", "engine_port"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL AND engine_port IS NOT NULL"),
    )


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM client_wireguard_leases "
                "WHERE engine_port IS NOT NULL)"
            )
        )
        .scalar()
    ):
        # Do not erase managed authorization/usage history or run old workers over it.
        raise RuntimeError("Retain managed transport schema after managed leases have been issued")
    op.drop_index("uq_client_lease_engine_port", table_name="client_wireguard_leases")
    op.drop_constraint("ck_client_lease_method", "client_wireguard_leases", type_="check")
    op.drop_constraint("ck_client_lease_engine", "client_wireguard_leases", type_="check")
    op.drop_constraint("ck_client_lease_relay", "client_wireguard_leases", type_="check")
    op.create_check_constraint(
        "ck_client_lease_relay",
        "client_wireguard_leases",
        "(method = 'wireguard' AND relay_node_id IS NULL AND relay_port IS NULL) OR "
        "(method = 'wireguard_relay' AND relay_node_id IS NOT NULL AND relay_port IS NOT NULL "
        "AND relay_port BETWEEN 20000 AND 29999 AND relay_node_id <> node_id)",
    )
    op.alter_column(
        "client_wireguard_leases", "address", existing_type=sa.String(18), nullable=False
    )
    op.drop_column("client_wireguard_leases", "engine_port")
