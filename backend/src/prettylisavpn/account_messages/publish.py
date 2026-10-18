"""Trusted server-only CLI. Requires the backend's PostgreSQL credentials.

python -m prettylisavpn.account_messages.publish publish --actor operator < message.json
python -m prettylisavpn.account_messages.publish withdraw --id MESSAGE_UUID
No message content or database exception is printed, including validation failures.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from prettylisavpn.account_messages.domain import Publication
from prettylisavpn.account_messages.service import MessagePublicationService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres

MAX_IMPORT_BYTES = 1048576


async def execute(command: str, payload: Publication | None, actor: str, message_id: UUID | None) -> None:
    postgres = Postgres(Settings())
    try:
        service = MessagePublicationService(postgres)
        if command == "publish":
            assert payload is not None
            await service.publish(payload, actor)
        else:
            assert message_id is not None
            await service.withdraw(message_id)
    finally:
        await postgres.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("--actor", required=True)
    publish.add_argument("--file", type=Path)
    withdraw = commands.add_parser("withdraw")
    withdraw.add_argument("--id", type=UUID, required=True)
    args = parser.parse_args()
    try:
        payload = None
        if args.command == "publish":
            if args.file:
                with args.file.open("rb") as source:
                    data = source.read(MAX_IMPORT_BYTES + 1)
            else:
                data = sys.stdin.buffer.read(MAX_IMPORT_BYTES + 1)
            if len(data) > MAX_IMPORT_BYTES:
                raise ValueError("Import limit exceeded")
            payload = Publication.model_validate_json(data)
        asyncio.run(execute(
            args.command, payload, getattr(args, "actor", ""), getattr(args, "id", None)
        ))
    except Exception:
        print(json.dumps({"event": "message_publication_failed"}), file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps({
        "event": "message_published" if payload else "message_withdrawn",
        "id": str(payload.id if payload else args.id),
        **({"revision": payload.revision} if payload else {}),
    }))


if __name__ == "__main__":
    main()
