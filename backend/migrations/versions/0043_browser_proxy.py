"""Browser-only HTTPS proxy reuses durable account-wide lease accounting."""

import sqlalchemy as sa
from alembic import op

revision = "0043_browser_proxy"
down_revision = "0042_cardlink_inbox"
branch_labels = None
depends_on = None

METHODS = (
    "'wireguard','wireguard_relay','vless_reality','vless_reality_relay',"
    "'amneziawg','amneziawg_relay','vless','vless_relay','vmess','vmess_relay',"
    "'hysteria','hysteria_relay','sstp','sstp_relay','softether','softether_relay',"
    "'shadowsocks2022','shadowsocks2022_relay','hysteria2','hysteria2_relay',"
    "'hysteria2_salamander','hysteria2_salamander_relay'"
)


def upgrade() -> None:
    op.drop_constraint("ck_client_lease_method", "client_wireguard_leases", type_="check")
    op.create_check_constraint(
        "ck_client_lease_method",
        "client_wireguard_leases",
        "method IN (" + METHODS + ",'https_proxy')",
    )


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM client_wireguard_leases WHERE method = 'https_proxy')"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Retain proxy authorization and quota history after browser use")
    op.drop_constraint("ck_client_lease_method", "client_wireguard_leases", type_="check")
    op.create_check_constraint(
        "ck_client_lease_method", "client_wireguard_leases", "method IN (" + METHODS + ")"
    )
