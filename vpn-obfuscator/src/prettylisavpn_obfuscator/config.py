"""Validated environment configuration for the UDP obfuscator."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field

from .protocol import decode_secret
from .providers import packet_provider


@dataclass(frozen=True)
class Settings:
    secret: bytes = field(repr=False)
    bind_host: str
    bind_port: int
    wireguard_host: str
    wireguard_port: int
    max_packet_size: int
    max_padding_size: int
    max_clients: int
    client_idle_timeout_seconds: int
    status_interval_seconds: int
    obfuscation_mode: str = "PRETTYLISA_V1"
    obfuscation_version: int = 1
    max_datagram_size: int = 1400

    @classmethod
    def from_environment(cls) -> Settings:
        bind_host = _ipv4("PRETTYLISA_OBFUSCATION_BIND_HOST", "0.0.0.0")
        wireguard_host = _ipv4("PRETTYLISA_WIREGUARD_HOST", "127.0.0.1")
        if not ipaddress.ip_address(wireguard_host).is_loopback:
            raise ValueError("WireGuard transport host must be loopback")
        bind_port = _integer("PRETTYLISA_OBFUSCATION_BIND_PORT", 443, 1, 65_535)
        wireguard_port = _integer("PRETTYLISA_WIREGUARD_PORT", 51_820, 1, 65_535)
        if bind_host in {"0.0.0.0", wireguard_host} and bind_port == wireguard_port:
            raise ValueError("public and local WireGuard endpoints must not overlap")
        mode = os.getenv("PRETTYLISA_OBFUSCATION_MODE", "PRETTYLISA_V1")
        version = _integer("PRETTYLISA_OBFUSCATION_VERSION", 0 if mode == "NONE" else 1, 0, 255)
        maximum = _integer("PRETTYLISA_MAX_DATAGRAM_SIZE", 1400, 1320, 65507)
        if mode != "PRETTYLISA_V1":
            packet_provider(mode, version, maximum)
        elif version != 1:
            raise ValueError("unsupported legacy version")
        return cls(
            obfuscation_mode=mode,
            obfuscation_version=version,
            max_datagram_size=maximum,
            secret=decode_secret(_required("PRETTYLISA_OBFUSCATION_SECRET"))
            if mode == "PRETTYLISA_V1"
            else b"",
            bind_host=bind_host,
            bind_port=bind_port,
            wireguard_host=wireguard_host,
            wireguard_port=wireguard_port,
            max_packet_size=_integer("PRETTYLISA_MAX_PACKET_SIZE", 4_096, 1, 65_535),
            max_padding_size=_integer("PRETTYLISA_MAX_PADDING_SIZE", 255, 0, 65_535),
            max_clients=_integer("PRETTYLISA_MAX_CLIENTS", 1_024, 1, 65_535),
            client_idle_timeout_seconds=_integer(
                "PRETTYLISA_CLIENT_IDLE_TIMEOUT_SECONDS", 180, 30, 86_400
            ),
            status_interval_seconds=_integer("PRETTYLISA_STATUS_INTERVAL_SECONDS", 60, 10, 3_600),
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value:
        raise ValueError(f"missing required environment variable: {name}")
    return value


def _ipv4(name: str, default: str) -> str:
    value = os.getenv(name, default)
    address = ipaddress.ip_address(value)
    if address.version != 4:
        raise ValueError(f"{name} must be an IPv4 address")
    return str(address)


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value
