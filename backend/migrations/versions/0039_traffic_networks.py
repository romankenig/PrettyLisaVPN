"""Add explicit service IPv4 networks for native Telegram connections."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039_traffic_networks"
down_revision = "0038_traffic_presets"
branch_labels = None
depends_on = None

# https://core.telegram.org/resources/cidr.txt, verified 2026-10-31.
# IPv6 remains blocked by the existing tunnel policy, not sent directly.
TELEGRAM_IPV4 = [
    "91.108.56.0/22",
    "91.108.4.0/22",
    "91.108.8.0/22",
    "91.108.16.0/22",
    "91.108.12.0/22",
    "149.154.160.0/20",
    "91.105.192.0/23",
    "91.108.20.0/22",
    "185.76.151.0/24",
]


def upgrade() -> None:
    op.add_column(
        "traffic_services",
        sa.Column(
            "ipv4_cidrs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.create_check_constraint(
        "ck_traffic_service_networks", "traffic_services", "jsonb_typeof(ipv4_cidrs) = 'array'"
    )
    table = sa.table(
        "traffic_services",
        sa.column("slug", sa.String()),
        sa.column("ipv4_cidrs", postgresql.JSONB()),
    )
    op.execute(table.update().where(table.c.slug == "telegram").values(ipv4_cidrs=TELEGRAM_IPV4))


def downgrade() -> None:
    op.drop_constraint("ck_traffic_service_networks", "traffic_services", type_="check")
    op.drop_column("traffic_services", "ipv4_cidrs")
