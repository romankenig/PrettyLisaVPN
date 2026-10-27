"""Pinned inventory is worker-only. API input cannot select arbitrary SSH credentials."""

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field

from prettylisavpn.fleet.domain import FleetError, Node, Value


class Credential(Value):
    host: str = Field(pattern=r"^[0-9.]+$")
    user: str = Field(pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    port: int = Field(default=22, ge=1, le=65535)
    key_file: str
    known_hosts: str


class NodeTransport(Protocol):
    async def call(
        self,
        node: Node,
        action: str,
        payload: dict[str, Any] | None = None,
        command_timeout: int = 60,
    ) -> dict[str, Any]: ...
    async def bootstrap(self, node: Node) -> None: ...


async def process(
    argv: list[str],
    payload: bytes = b"",
    *,
    command_timeout: int = 60,
    env: dict[str, str] | None = None,
) -> bytes:
    child = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
    )
    try:
        stdout, _ = await asyncio.wait_for(child.communicate(payload), timeout=command_timeout)
    except (TimeoutError, asyncio.CancelledError):
        child.kill()
        await child.wait()
        raise FleetError("NODE_COMMAND_TIMEOUT") from None
    if child.returncode or len(stdout) > 1048576:
        raise FleetError("NODE_COMMAND_FAILED")
    return stdout


class SshTransport:
    def __init__(self, inventory: dict[str, Credential]) -> None:
        self.inventory = inventory

    @classmethod
    def from_file(cls, path: str) -> "SshTransport":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls({key: Credential.model_validate(value) for key, value in raw.items()})

    def credential(self, node: Node) -> Credential:
        entry = self.inventory.get(node.credential_ref)
        if entry is None or entry.host != node.host:
            raise FleetError("NODE_CREDENTIAL_NOT_ENROLLED")
        for filename in (entry.key_file, entry.known_hosts):
            if not Path(filename).is_absolute() or not Path(filename).is_file():
                raise FleetError("NODE_CREDENTIAL_UNAVAILABLE")
        return entry

    async def call(
        self,
        node: Node,
        action: str,
        payload: dict[str, Any] | None = None,
        command_timeout: int = 60,
    ) -> dict[str, Any]:
        entry = self.credential(node)
        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "ServerAliveInterval=10",
            "-o",
            "ServerAliveCountMax=2",
            "-o",
            f"UserKnownHostsFile={entry.known_hosts}",
            "-i",
            entry.key_file,
            "-p",
            str(entry.port),
            f"{entry.user}@{entry.host}",
            "sudo -n /usr/bin/python3 /usr/local/lib/prettylisavpn-fleet/node.py",
        ]
        data = await process(
            command,
            json.dumps({"action": action, **(payload or {})}).encode(),
            command_timeout=command_timeout,
        )
        try:
            response = json.loads(data)
            if not isinstance(response, dict):
                raise ValueError()
            if response.get("error"):
                code = str(response["error"])
                raise FleetError(
                    code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code) else "NODE_OPERATION_FAILED"
                )
            return response
        except (ValueError, UnicodeDecodeError):
            raise FleetError("NODE_RESPONSE_INVALID") from None

    async def bootstrap(self, node: Node) -> None:
        entry = self.credential(node)
        # Ansible is an isolated infrastructure executable, not invoked by the HTTP process.
        with tempfile.TemporaryDirectory(prefix="pl-fleet-") as directory:
            inventory = Path(directory) / "inventory.json"
            inventory.write_text(
                json.dumps(
                    {
                        "all": {
                            "hosts": {
                                "vpn_node": {
                                    "ansible_host": entry.host,
                                    "ansible_user": entry.user,
                                    "ansible_port": entry.port,
                                    "ansible_ssh_private_key_file": entry.key_file,
                                    "ansible_ssh_common_args": (
                                        "-o BatchMode=yes -o IdentitiesOnly=yes "
                                        "-o StrictHostKeyChecking=yes -o UserKnownHostsFile="
                                    )
                                    + entry.known_hosts,
                                    "ansible_become": True,
                                    "ansible_become_flags": "-n",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            inventory.chmod(0o600)
            env = {
                **os.environ,
                "ANSIBLE_LOCAL_TEMP": directory,
                "ANSIBLE_HOST_KEY_CHECKING": "True",
                "ANSIBLE_RETRY_FILES_ENABLED": "False",
            }
            playbook = str(Path(__file__).parent / "ubuntu" / "configure.yml")
            await process(
                ["ansible-playbook", "-i", str(inventory), playbook], command_timeout=600, env=env
            )
