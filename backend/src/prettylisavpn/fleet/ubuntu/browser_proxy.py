"""Per-lease HTTPS forward proxy. No access logs, packet logs or control API.

Launched unprivileged by managed.py; private configuration and deadline renewals
arrive over stdin. Only aggregate counters and readiness leave this process.
"""

import asyncio
import base64
import contextlib
import hmac
import ipaddress
import json
import os
import socket
import ssl
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

WEB_PORTS = frozenset((80, 443, 8080, 8443))
MAX_CONNECTIONS = 64
MAX_HEADERS = 16384


def target(authority: str, default_port: int) -> tuple[str, int]:
    parsed = urlsplit("//" + authority)
    if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("INVALID_TARGET")
    host, port = parsed.hostname, parsed.port if parsed.port is not None else default_port
    if not host or len(host) > 253 or port not in WEB_PORTS or ":" in host:
        raise ValueError("INVALID_TARGET")
    host = host.encode("idna").decode("ascii")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for char in host.lower()):
        raise ValueError("INVALID_TARGET")
    return host, port


def request(raw: bytes, credentials: bytes) -> tuple[str, int, bool, bytes]:
    lines = raw.decode("iso-8859-1").split("\r\n")
    method, uri, version = lines[0].split(" ")
    if version not in ("HTTP/1.0", "HTTP/1.1"):
        raise ValueError("INVALID_REQUEST")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if line[0].isspace() or ":" not in line:
            raise ValueError("INVALID_REQUEST")
        key, value = line.split(":", 1)
        if any(ord(c) < 32 and c != "\t" for c in value) or "\x7f" in value:
            raise ValueError("INVALID_REQUEST")
        key = key.lower()
        if (
            key in headers
            or not key
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in key)
        ):
            raise ValueError("INVALID_REQUEST")
        headers[key] = value.strip()
    supplied = headers.pop("proxy-authorization", "").encode("ascii", errors="ignore")
    if not hmac.compare_digest(supplied, credentials):
        raise PermissionError("AUTH_REQUIRED")
    if "content-length" in headers and "transfer-encoding" in headers:
        raise ValueError("INVALID_REQUEST")
    if method == "CONNECT":
        host, port = target(uri, 443)
        return host, port, True, b""
    if method not in ("GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
        raise ValueError("INVALID_REQUEST")
    parsed = urlsplit(uri)
    if parsed.scheme != "http" or parsed.fragment:
        raise ValueError("INVALID_REQUEST")
    host, port = target(parsed.netloc, 80)
    headers.pop("proxy-connection", None)
    headers["host"] = host + (":" + str(port) if port != 80 else "")
    # One ordinary HTTP exchange per connection; encrypted CONNECT supports
    # arbitrary HTTP/2 streams and WSS without interpreting their contents.
    headers["connection"] = "close"
    path = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
    forwarded = (
        f"{method} {path} {version}\r\n"
        + "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        + "\r\n"
    )
    return host, port, False, forwarded.encode("iso-8859-1")


async def resolve_public(host: str, port: int) -> list[str]:
    addresses = await asyncio.get_running_loop().getaddrinfo(
        host, port, family=socket.AF_INET, type=socket.SOCK_STREAM
    )
    ips = list(dict.fromkeys(str(item[4][0]) for item in addresses))
    # Validate every answer, then dial the validated literal (no DNS rebinding
    # between the check and connect). IPv6/private/link-local traffic is blocked.
    if not ips or any(not ipaddress.IPv4Address(ip).is_global for ip in ips):
        raise ValueError("NONPUBLIC_TARGET")
    return ips


class Proxy:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.expires = float(payload["expires"])
        self.credentials = b"Basic " + base64.b64encode(
            (str(payload["id"]) + ":" + str(payload["secret"])).encode()
        )
        self.connections = 0
        self.counters = {"rx_bytes": 0, "tx_bytes": 0}

    async def pipe(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, counter: str
    ) -> None:
        while self.expires > time.time():
            data = await asyncio.wait_for(reader.read(65536), 120)
            if not data:
                return
            writer.write(data)
            await writer.drain()
            self.counters[counter] += len(data)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream: asyncio.StreamWriter | None = None
        tasks: list[asyncio.Task[None]] = []
        if self.connections >= MAX_CONNECTIONS or self.expires <= time.time():
            writer.close()
            return
        self.connections += 1
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            host, port, tunnel, forwarded = request(raw, self.credentials)
            ips = await asyncio.wait_for(resolve_public(host, port), 10)
            remote, upstream = await asyncio.wait_for(asyncio.open_connection(ips[0], port), 10)
            assert upstream is not None
            if tunnel:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                upstream.write(forwarded)
                await upstream.drain()
            tasks = [
                asyncio.create_task(self.pipe(reader, upstream, "tx_bytes")),
                asyncio.create_task(self.pipe(remote, writer, "rx_bytes")),
            ]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except PermissionError:
            writer.write(
                b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                b'Proxy-Authenticate: Basic realm="PrettyLisaVPN"\r\n'
                b"Content-Length: 0\r\nConnection: close\r\n\r\n"
            )
            with contextlib.suppress(Exception):
                await writer.drain()
        except Exception:
            # Do not disclose or log request destinations or exception contents.
            if upstream is None:
                writer.write(
                    b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
                with contextlib.suppress(Exception):
                    await writer.drain()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for stream in (upstream, writer):
                if stream is not None:
                    stream.close()
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(stream.wait_closed(), 2)
            self.connections -= 1


def tls_context(payload: dict[str, Any]) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["http/1.1"])
    # SSLContext requires files; they are private, node-local, and immediately
    # removed after loading. Nothing is written to a process command line.
    with tempfile.TemporaryDirectory(prefix="pl-proxy-") as folder:
        certificate, key = Path(folder) / "cert.pem", Path(folder) / "key.pem"
        certificate.write_text(str(payload["tls_certificate"]), encoding="ascii")
        key.write_text(str(payload["tls_key"]), encoding="ascii")
        certificate.chmod(0o600)
        key.chmod(0o600)
        context.load_cert_chain(certificate, key)
    return context


async def run(payload: dict[str, Any]) -> None:
    proxy = Proxy(payload)
    if not time.time() < proxy.expires <= time.time() + 180:
        return
    server = await asyncio.start_server(
        proxy.handle,
        payload["listen"],
        int(payload["port"]),
        ssl=tls_context(payload),
        ssl_handshake_timeout=10,
        limit=MAX_HEADERS,
    )
    print("READY", flush=True)
    control = asyncio.StreamReader(limit=1024)
    await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(control), sys.stdin
    )

    async def renew() -> None:
        while raw := await control.readline():
            value = json.loads(raw)
            expiry = float(value["expires"])
            if set(value) != {"expires"} or not time.time() < expiry <= time.time() + 180:
                return
            proxy.expires = expiry

    renewal = asyncio.create_task(renew())
    try:
        while not renewal.done() and proxy.expires > time.time():
            await asyncio.sleep(0.5)
            print(json.dumps(proxy.counters), flush=True)
    finally:
        server.close()
        await server.wait_closed()
        renewal.cancel()
        await asyncio.gather(renewal, return_exceptions=True)
        # asyncio.run cancels live handlers, closing every active connection.


if __name__ == "__main__":
    try:
        os.umask(0o077)
        config = json.loads(sys.stdin.buffer.readline(65536))
        asyncio.run(run(config))
    except Exception:
        raise SystemExit(1) from None
