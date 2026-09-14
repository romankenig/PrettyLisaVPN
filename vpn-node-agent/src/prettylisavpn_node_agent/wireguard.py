"""Validated WireGuard peer operations using argv-only native commands."""

import json
import subprocess
from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from threading import Lock

WG_PATH = "/usr/bin/wg"
IP_PATH = "/usr/sbin/ip"
COMMAND_TIMEOUT_SECONDS = 5


class WireGuardError(RuntimeError):
    """The local WireGuard interface could not complete an operation."""


class PeerConflictError(ValueError):
    """The requested peer conflicts with existing runtime state."""


def validate_public_key(value: str) -> str:
    normalized = value.strip()
    try:
        decoded = b64decode(normalized, validate=True)
    except (Base64Error, ValueError) as error:
        raise ValueError("public_key must be valid base64") from error
    if len(normalized) != 44 or len(decoded) != 32:
        raise ValueError("public_key must encode exactly 32 bytes")
    return normalized


CommandRunner = Callable[[Sequence[str]], str]


def native_command_runner(arguments: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(arguments),
            check=True,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise WireGuardError("WireGuard command failed") from error
    return completed.stdout


@dataclass(frozen=True, slots=True)
class PeerState:
    public_key: str
    vpn_ip: IPv4Address
    latest_handshake_at: datetime | None


@dataclass(frozen=True, slots=True)
class InterfaceState:
    is_up: bool
    listen_port: int | None
    public_key_available: bool


class WireGuardController:
    def __init__(
        self,
        interface: str,
        client_subnet: IPv4Network,
        gateway: IPv4Interface,
        runner: CommandRunner = native_command_runner,
    ) -> None:
        self._interface = interface
        self._client_subnet = client_subnet
        self._gateway = gateway
        self._runner = runner
        self._mutation_lock = Lock()

    def add_peer(self, public_key: str, vpn_ip: IPv4Address) -> tuple[PeerState, bool]:
        key = validate_public_key(public_key)
        self._validate_client_ip(vpn_ip)
        with self._mutation_lock:
            peers = self.list_peers()
            existing = peers.get(key)
            if existing is not None:
                if existing.vpn_ip != vpn_ip:
                    raise PeerConflictError("peer already exists with another VPN IP")
                return existing, False
            if any(peer.vpn_ip == vpn_ip for peer in peers.values()):
                raise PeerConflictError("VPN IP is already allocated to another peer")
            self._runner(
                [
                    WG_PATH,
                    "set",
                    self._interface,
                    "peer",
                    key,
                    "allowed-ips",
                    f"{vpn_ip}/32",
                ]
            )
            return PeerState(key, vpn_ip, None), True

    def remove_peer(self, public_key: str) -> bool:
        key = validate_public_key(public_key)
        with self._mutation_lock:
            if key not in self.list_peers():
                return False
            self._runner([WG_PATH, "set", self._interface, "peer", key, "remove"])
            return True

    def get_peer(self, public_key: str) -> PeerState | None:
        return self.list_peers().get(validate_public_key(public_key))

    def list_peers(self) -> dict[str, PeerState]:
        allowed_ips = self._parse_allowed_ips(
            self._runner([WG_PATH, "show", self._interface, "allowed-ips"])
        )
        handshakes = self._parse_handshakes(
            self._runner([WG_PATH, "show", self._interface, "latest-handshakes"])
        )
        return {
            key: PeerState(key, vpn_ip, handshakes.get(key)) for key, vpn_ip in allowed_ips.items()
        }

    def interface_state(self) -> InterfaceState:
        link_json = self._runner([IP_PATH, "-j", "link", "show", "dev", self._interface])
        try:
            link = json.loads(link_json)[0]
            is_up = "UP" in link.get("flags", []) and link.get("operstate") != "DOWN"
            listen_port_text = self._runner(
                [WG_PATH, "show", self._interface, "listen-port"]
            ).strip()
            public_key = self._runner([WG_PATH, "show", self._interface, "public-key"]).strip()
            listen_port = int(listen_port_text) if listen_port_text else None
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise WireGuardError("invalid WireGuard interface state") from error
        return InterfaceState(is_up, listen_port, bool(public_key))

    def _validate_client_ip(self, vpn_ip: IPv4Address) -> None:
        if vpn_ip not in self._client_subnet:
            raise ValueError("vpn_ip must be inside the configured client subnet")
        if vpn_ip in (
            self._client_subnet.network_address,
            self._client_subnet.broadcast_address,
            self._gateway.ip,
        ):
            raise ValueError("vpn_ip is reserved")

    @staticmethod
    def _parse_allowed_ips(output: str) -> dict[str, IPv4Address]:
        peers: dict[str, IPv4Address] = {}
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) != 2:
                raise WireGuardError("invalid allowed-ips output")
            key = validate_public_key(fields[0])
            allowed = fields[1].split(",")
            if len(allowed) != 1:
                raise WireGuardError("peer must have exactly one allowed IP")
            try:
                network = IPv4Network(allowed[0], strict=False)
            except ValueError as error:
                raise WireGuardError("invalid peer allowed IP") from error
            if network.prefixlen != 32:
                raise WireGuardError("peer allowed IP must be a single IPv4 address")
            peers[key] = network.network_address
        return peers

    @staticmethod
    def _parse_handshakes(output: str) -> dict[str, datetime | None]:
        handshakes: dict[str, datetime | None] = {}
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) != 2:
                raise WireGuardError("invalid latest-handshakes output")
            key = validate_public_key(fields[0])
            try:
                timestamp = int(fields[1])
            except ValueError as error:
                raise WireGuardError("invalid handshake timestamp") from error
            handshakes[key] = datetime.fromtimestamp(timestamp, UTC) if timestamp else None
        return handshakes
