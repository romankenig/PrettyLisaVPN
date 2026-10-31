"""Expand the operator-owned traffic catalog; retain existing service identities."""

from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038_traffic_presets"
down_revision = "0037_traffic_catalog"
branch_labels = None
depends_on = None

SERVICES = [
    {
        "id": "112446d1-3622-5bf6-9db5-8fd4753bf4c5",
        "slug": "facebook",
        "name": "Facebook",
        "icon": "facebook",
        "category": "popular",
        "domains": [
            "facebook.com",
            "*.facebook.com",
            "fb.com",
            "*.fb.com",
            "fbcdn.net",
            "*.fbcdn.net",
            "fbsbx.com",
            "*.fbsbx.com",
            "messenger.com",
            "*.messenger.com",
        ],
    },
    {
        "id": "b6c380d9-fd27-5e41-bd2e-bcc41d939a48",
        "slug": "whatsapp",
        "name": "WhatsApp",
        "icon": "whatsapp",
        "category": "popular",
        "domains": [
            "whatsapp.com",
            "*.whatsapp.com",
            "whatsapp.net",
            "*.whatsapp.net",
            "wa.me",
            "*.wa.me",
        ],
    },
    {
        "id": "6cbb9213-108e-5bf7-b4f9-5f10a42d2b0c",
        "slug": "telegram",
        "name": "Telegram",
        "icon": "telegram",
        "category": "popular",
        "domains": [
            "telegram.org",
            "*.telegram.org",
            "t.me",
            "*.t.me",
            "telegram.me",
            "*.telegram.me",
            "telesco.pe",
            "*.telesco.pe",
            "telegra.ph",
            "*.telegra.ph",
        ],
    },
    {
        "id": "6b0631c2-63e3-5b23-9a9f-cdaf88f8ccf3",
        "slug": "discord",
        "name": "Discord",
        "icon": "discord",
        "category": "popular",
        "domains": [
            "discord.com",
            "*.discord.com",
            "discord.gg",
            "*.discord.gg",
            "discordapp.com",
            "*.discordapp.com",
            "discordapp.net",
            "*.discordapp.net",
            "discord.media",
            "*.discord.media",
        ],
    },
    {
        "id": "81d9d898-90c6-52e3-9e73-ce1a4ff86dcd",
        "slug": "signal",
        "name": "Signal",
        "icon": "signal",
        "category": "popular",
        "domains": [
            "signal.org",
            "*.signal.org",
            "signal.art",
            "*.signal.art",
            "signal.group",
            "*.signal.group",
            "signal.link",
            "*.signal.link",
            "signal.me",
            "*.signal.me",
            "signal.tube",
            "*.signal.tube",
        ],
    },
    {
        "id": "ffd3378c-8274-5dfa-8866-4804c4b4e9d4",
        "slug": "x",
        "name": "X",
        "icon": "x",
        "category": "popular",
        "domains": [
            "x.com",
            "*.x.com",
            "twitter.com",
            "*.twitter.com",
            "t.co",
            "*.t.co",
            "twimg.com",
            "*.twimg.com",
        ],
    },
    {
        "id": "60d6480a-40e2-5ee6-be06-19508bdff50d",
        "slug": "linkedin",
        "name": "LinkedIn",
        "icon": "linkedin",
        "category": "popular",
        "domains": [
            "linkedin.com",
            "*.linkedin.com",
            "licdn.com",
            "*.licdn.com",
            "lnkd.in",
            "*.lnkd.in",
        ],
    },
    {
        "id": "b905328d-ddc1-51d1-926b-65f5dff13710",
        "slug": "tiktok",
        "name": "TikTok",
        "icon": "tiktok",
        "category": "popular",
        "domains": [
            "tiktok.com",
            "*.tiktok.com",
            "tiktokv.com",
            "*.tiktokv.com",
            "tiktokcdn.com",
            "*.tiktokcdn.com",
            "tiktokcdn-us.com",
            "*.tiktokcdn-us.com",
            "tiktokv.us",
            "*.tiktokv.us",
            "musical.ly",
            "*.musical.ly",
        ],
    },
    {
        "id": "05374f29-c584-533b-ab4f-774b299ca78f",
        "slug": "vk",
        "name": "ВКонтакте",
        "icon": "vk",
        "category": "whitelist",
        "domains": [
            "vk.com",
            "*.vk.com",
            "vk.ru",
            "*.vk.ru",
            "vk.me",
            "*.vk.me",
            "vkuseraudio.net",
            "*.vkuseraudio.net",
            "vkuserlive.net",
            "*.vkuserlive.net",
            "vkuserphoto.ru",
            "*.vkuserphoto.ru",
            "vkuser.net",
            "*.vkuser.net",
            "userapi.com",
            "*.userapi.com",
            "vkvideo.ru",
            "*.vkvideo.ru",
        ],
    },
    {
        "id": "72e6b490-ffd7-5b09-9d0d-e8a7ca3d763a",
        "slug": "ok",
        "name": "Одноклассники",
        "icon": "ok",
        "category": "whitelist",
        "domains": [
            "ok.ru",
            "*.ok.ru",
            "odnoklassniki.ru",
            "*.odnoklassniki.ru",
            "okcdn.ru",
            "*.okcdn.ru",
            "mycdn.me",
            "*.mycdn.me",
        ],
    },
    {
        "id": "5993366b-1579-58ae-b969-bfa778286703",
        "slug": "mail",
        "name": "Почта Mail",
        "icon": "mail",
        "category": "whitelist",
        "domains": ["mail.ru", "*.mail.ru", "imgsmail.ru", "*.imgsmail.ru"],
    },
    {
        "id": "29f03293-eb8a-575e-bfb2-07a2cbfb6b2a",
        "slug": "max",
        "name": "MAX",
        "icon": "max",
        "category": "whitelist",
        "domains": ["max.ru", "*.max.ru", "max-d.ru", "*.max-d.ru"],
    },
    {
        "id": "40aa1228-0c24-5e3c-a251-2e5359be910f",
        "slug": "yandex",
        "name": "Яндекс",
        "icon": "yandex",
        "category": "whitelist",
        "domains": [
            "yandex.ru",
            "*.yandex.ru",
            "yandex.com",
            "*.yandex.com",
            "ya.ru",
            "*.ya.ru",
            "yastatic.net",
            "*.yastatic.net",
            "yandex.net",
            "*.yandex.net",
        ],
    },
    {
        "id": "ae30bed7-e5c1-58e2-bbfa-023b86289e9f",
        "slug": "ozon",
        "name": "Ozon",
        "icon": "ozon",
        "category": "whitelist",
        "domains": ["ozon.ru", "*.ozon.ru", "ozone.ru", "*.ozone.ru"],
    },
    {
        "id": "ddc4fd7b-5f7f-5195-a994-a5d0e865e0c3",
        "slug": "wildberries",
        "name": "Wildberries",
        "icon": "wildberries",
        "category": "whitelist",
        "domains": [
            "wildberries.ru",
            "*.wildberries.ru",
            "wb.ru",
            "*.wb.ru",
            "wbstatic.net",
            "*.wbstatic.net",
            "wbbasket.ru",
            "*.wbbasket.ru",
        ],
    },
    {
        "id": "1d06eb53-8cb2-5b80-8403-e28de64a3eb2",
        "slug": "gosuslugi",
        "name": "Госуслуги",
        "icon": "gosuslugi",
        "category": "whitelist",
        "domains": ["gosuslugi.ru", "*.gosuslugi.ru", "esia.gosuslugi.ru", "*.esia.gosuslugi.ru"],
    },
    {
        "id": "4d063abd-4fa5-59a7-a284-bd2b680e5bbf",
        "slug": "rutube",
        "name": "Rutube",
        "icon": "rutube",
        "category": "whitelist",
        "domains": [
            "rutube.ru",
            "*.rutube.ru",
            "rutubelist.ru",
            "*.rutubelist.ru",
            "rutubevideo.ru",
            "*.rutubevideo.ru",
        ],
    },
    {
        "id": "3d077243-3821-5958-92e0-4b8cac5a96a4",
        "slug": "dzen",
        "name": "Дзен",
        "icon": "dzen",
        "category": "whitelist",
        "domains": ["dzen.ru", "*.dzen.ru", "dzeninfra.ru", "*.dzeninfra.ru"],
    },
]


def upgrade() -> None:
    op.add_column(
        "traffic_services",
        sa.Column("category", sa.String(16), nullable=False, server_default="popular"),
    )
    op.create_check_constraint(
        "ck_traffic_service_category", "traffic_services", "category IN ('popular', 'whitelist')"
    )
    table = sa.table(
        "traffic_services",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sa.String()),
        sa.column("name", sa.String()),
        sa.column("icon", sa.String()),
        sa.column("category", sa.String()),
        sa.column("domains", postgresql.JSONB()),
    )
    op.bulk_insert(table, [{**row, "id": UUID(row["id"])} for row in SERVICES])


def downgrade() -> None:
    table = sa.table("traffic_services", sa.column("id", sa.Uuid()))
    op.execute(table.delete().where(table.c.id.in_([UUID(row["id"]) for row in SERVICES])))
    op.drop_constraint("ck_traffic_service_category", "traffic_services", type_="check")
    op.drop_column("traffic_services", "category")
