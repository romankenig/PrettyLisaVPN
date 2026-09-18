"""Validated environment configuration for the UDP obfuscator."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass

from .protocol import decode_secret


@dataclass(frozen=True)
class Settings:
    secret: bytes
    bind_host: str
    bind_port: int
    wireguard_host: str
    wireguard_port: int
    max_packet_size: int
    max_padding_size: int
    max_clients: int
    client_idle_timeout_seconds: int
    status_interval_seconds: int

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
        return cls(
            secret=decode_secret(_required("PRETTYLISA_OBFUSCATION_SECRET")),
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
