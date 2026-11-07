"""Browser-only data-plane authentication, remote DNS fencing and stream relay."""

import asyncio
import base64
import time
from unittest.mock import AsyncMock

import pytest

from prettylisavpn.client_vpn.domain import ConnectRequest
from prettylisavpn.fleet.domain import proxy_address_supported
from prettylisavpn.fleet.ubuntu import browser_proxy as proxy

AUTH = b"Basic " + base64.b64encode(b"lease:test-secret")


@pytest.mark.parametrize("capable", [False, True])
def test_proxy_address_contract_preserves_legacy_clients(capable):
    assert proxy_address_supported("proxy-de.prettylisavpn.com", allow_ip=capable)
    assert proxy_address_supported("5.181.49.183", allow_ip=capable) is capable
    for host in (None, "", "127.0.0.1", "192.168.1.1", "999.1.1.1", "005.181.49.183"):
        assert not proxy_address_supported(host, allow_ip=capable)


def raw(uri="example.com:443", method="CONNECT", extra=b""):
    return (
        f"{method} {uri} HTTP/1.1\r\n".encode()
        + b"Proxy-Authorization: "
        + AUTH
        + b"\r\n"
        + extra
        + b"\r\n"
    )


def test_chrome_transport_has_no_relay_or_native_alias():
    key = base64.b64encode(b"p" * 32).decode()
    assert ConnectRequest(public_key=key, method="https_proxy").method == "https_proxy"
    with pytest.raises(ValueError):
        ConnectRequest(public_key=key, method="https_proxy_relay")


def test_forward_http_strips_proxy_credentials_and_rewrites_host():
    host, port, tunnel, forwarded = proxy.request(
        raw("http://example.com/path?q=1", "POST", b"Host: other.example\r\nContent-Length: 3\r\n"),
        AUTH,
    )
    assert (host, port, tunnel) == ("example.com", 80, False)
    assert forwarded.startswith(b"POST /path?q=1 HTTP/1.1\r\n")
    assert b"host: example.com\r\n" in forwarded
    assert b"test-secret" not in forwarded and b"proxy-authorization" not in forwarded.lower()
    assert b"connection: close\r\n" in forwarded


@pytest.mark.parametrize(
    "authority",
    [
        "user:pass@example.com:443",
        "[::1]:443",
        "example.com:25",
        "example.com:0",
        "example.com:65536",
        "example.com/path",
        "example.com?x=1",
    ],
)
def test_unsupported_destinations_are_rejected(authority):
    with pytest.raises(ValueError):
        proxy.request(raw(authority), AUTH)


def test_authentication_precedes_dns_and_dial():
    with pytest.raises(PermissionError):
        proxy.request(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n", AUTH)


@pytest.mark.parametrize(
    "extra",
    [
        b"Host: a\r\nHost: b\r\n",
        b"Content-Length: 1\r\nTransfer-Encoding: chunked\r\n",
        b"X-Test: unsafe\rvalue\r\n",
    ],
)
def test_ambiguous_headers_are_rejected(extra):
    with pytest.raises(ValueError):
        proxy.request(raw("http://example.com/", "POST", extra), AUTH)


async def test_dns_rebinding_and_private_answers_are_rejected(monkeypatch):
    loop = asyncio.get_running_loop()
    resolver = AsyncMock(
        return_value=[(2, 1, 6, "", ("1.1.1.1", 443)), (2, 1, 6, "", ("169.254.169.254", 443))]
    )
    monkeypatch.setattr(loop, "getaddrinfo", resolver)
    with pytest.raises(ValueError, match="NONPUBLIC_TARGET"):
        await proxy.resolve_public("test.example", 443)


async def test_authenticated_connect_transfers_bytes_and_wrong_auth_never_dials(monkeypatch):
    async def echo(reader, writer):
        try:
            while data := await reader.read(4096):
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()

    upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
    upstream_port = upstream.sockets[0].getsockname()[1]
    real_open = asyncio.open_connection

    async def local_dial(*_args):
        return await real_open("127.0.0.1", upstream_port)

    dial = AsyncMock(side_effect=local_dial)
    monkeypatch.setattr(proxy, "resolve_public", AsyncMock(return_value=["1.1.1.1"]))
    monkeypatch.setattr(proxy.asyncio, "open_connection", dial)
    instance = proxy.Proxy({"id": "lease", "secret": "test-secret", "expires": time.time() + 30})
    server = await asyncio.start_server(instance.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await real_open("127.0.0.1", port)
        writer.write(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
        await writer.drain()
        assert b"407" in await reader.read(4096)
        writer.close()
        dial.assert_not_called()
        reader, writer = await real_open("127.0.0.1", port)
        writer.write(raw())
        await writer.drain()
        assert b"200 Connection Established" in await reader.readuntil(b"\r\n\r\n")
        writer.write(b"bounded-test-payload")
        await writer.drain()
        assert await asyncio.wait_for(reader.readexactly(20), 2) == b"bounded-test-payload"
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        upstream.close()
        await server.wait_closed()
        await upstream.wait_closed()


async def test_expired_proxy_refuses_streams():
    instance = proxy.Proxy({"id": "lease", "secret": "test-secret", "expires": time.time() - 1})
    server = await asyncio.start_server(instance.handle, "127.0.0.1", 0)
    try:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", server.sockets[0].getsockname()[1]
        )
        assert await asyncio.wait_for(reader.read(1), 2) == b""
        writer.close()
        await writer.wait_closed()
        assert instance.connections == 0
    finally:
        server.close()
        await server.wait_closed()
