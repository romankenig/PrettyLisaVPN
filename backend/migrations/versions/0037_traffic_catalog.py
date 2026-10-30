"""Seed database-owned service masks for device-local routing."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_traffic_catalog"
down_revision = "0036_daily_allowance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "traffic_services",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("icon", sa.String(40), nullable=False),
        sa.Column("domains", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("jsonb_typeof(domains) = 'array'", name="ck_traffic_service_domains"),
    )
    from uuid import UUID

    services = [
        (
            "0bd811da-f080-4f25-887a-67bf534ac2c6",
            "youtube",
            "YouTube",
            [
                "youtube.com",
                "youtu.be",
                "youtube-nocookie.com",
                "googlevideo.com",
                "ytimg.com",
                "youtubei.googleapis.com",
                "youtube.googleapis.com",
                "yt3.ggpht.com",
            ],
        ),
        (
            "4e2b8d7c-289f-4c57-8f26-aeb680408cda",
            "instagram",
            "Instagram",
            ["instagram.com", "cdninstagram.com", "ig.me", "igcdn.com", "fbcdn.net"],
        ),
    ]
    op.bulk_insert(
        table,
        [
            {
                "id": UUID(identifier),
                "slug": slug,
                "name": name,
                "icon": slug,
                "domains": [mask for domain in domains for mask in (domain, "*." + domain)],
            }
            for identifier, slug, name, domains in services
        ],
    )


def downgrade() -> None:
    op.drop_table("traffic_services")
