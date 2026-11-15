"""Bounded public-content sampler. Synthetic URLs stay in memory, never in logs.

Shared by the worker's discovery adapter and the isolated WireGuard namespace.
DNS answers are validated and pinned to the TLS connection (including redirects).
"""

import http.client
import ipaddress
import secrets
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

LIMIT = 1024 * 1024


def allowed(url: str, domains: list[str]) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return (
            len(url) <= 2048
            and parsed.scheme == "https"
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
            and any(
                host == value.removeprefix("*.")
                or (value.startswith("*.") and host.endswith("." + value[2:]))
                for value in domains
            )
        )
    except ValueError:
        return False


class PublicHTTPS(http.client.HTTPSConnection):
    def connect(self) -> None:
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(row[4][0]).is_global
            or ipaddress.ip_address(row[4][0]).is_multicast
            for row in addresses
        ):
            raise ValueError("NON_PUBLIC_SAMPLE")
        address = str(addresses[secrets.randbelow(len(addresses))][4][0])
        sock = socket.create_connection((address, 443), timeout=4)
        try:
            self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def fetch(url: str, domains: list[str]) -> tuple[str, bytes, str]:
    deadline = time.monotonic() + 10
    for _ in range(5):
        if time.monotonic() >= deadline:
            raise TimeoutError("SAMPLE_TIMEOUT")
        if not allowed(url, domains):
            raise ValueError("SAMPLE_OUTSIDE_SERVICE")
        parsed = urlsplit(url)
        connection = PublicHTTPS(parsed.hostname or "", timeout=4)
        try:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": "PrettyLisaVPN-Availability/1.0",
                    "Accept": "text/html,application/atom+xml,application/rss+xml",
                },
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = urljoin(url, response.getheader("Location", ""))
                continue
            if response.status != 200:
                raise ValueError("SAMPLE_HTTP_FAILED")
            content = bytearray()
            while len(content) < LIMIT:
                if time.monotonic() >= deadline:
                    raise TimeoutError("SAMPLE_TIMEOUT")
                chunk = response.read1(min(65536, LIMIT - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
            return url, bytes(content), response.getheader("Content-Type", "")
        finally:
            connection.close()
    raise ValueError("SAMPLE_REDIRECT_LIMIT")


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.feeds: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        href = values.get("href")
        if href and tag == "a":
            self.links.append(href)
        if (
            href
            and tag == "link"
            and values.get("type") in ("application/rss+xml", "application/atom+xml")
        ):
            self.feeds.append(href)


def candidates(body: bytes, root: str, domains: list[str]) -> tuple[list[str], list[str]]:
    parser = Links()
    parser.feed(body.decode("utf-8", errors="replace"))
    links = parser.links
    try:
        tree = ElementTree.fromstring(body)
        # Publishers normally order feeds newest first; take only recent entries.
        entries = [
            item for item in tree.iter() if item.tag.rsplit("}", 1)[-1] in ("item", "entry")
        ][:20]
        links = [
            link.get("href") or link.text or ""
            for entry in entries
            for link in entry
            if link.tag.rsplit("}", 1)[-1] == "link"
        ] or links
    except ElementTree.ParseError:
        pass
    resolved = list(dict.fromkeys(urljoin(root, value) for value in links))
    resolved = [
        value
        for value in resolved
        if allowed(value, domains)
        and urlsplit(value).path not in ("", "/")
        and not any(
            part in urlsplit(value).path.lower()
            for part in ("login", "signin", "privacy", "terms", "logout")
        )
    ]
    recent = [
        value
        for value in resolved
        if any(part in value.lower() for part in ("/news/", "/blog/", "/posts/", "/20", "/watch?"))
    ]
    feeds = [
        urljoin(root, value) for value in parser.feeds if allowed(urljoin(root, value), domains)
    ]
    return recent or resolved, feeds


def discover(domains: list[str]) -> str | None:
    # Use primary catalog domains, never a manually supplied customer rule.
    roots = list(dict.fromkeys(value for value in domains if not value.startswith("*.")))[:3]
    deadline = time.monotonic() + 25
    for host in roots:
        if time.monotonic() >= deadline:
            break
        try:
            root, body, _ = fetch("https://" + host + "/", domains)
            links, feeds = candidates(body, root, domains)
            if feeds and time.monotonic() < deadline:
                try:
                    feed, content, _ = fetch(secrets.choice(feeds), domains)
                    fresh, _ = candidates(content, feed, domains)
                    links = fresh or links
                except Exception:
                    pass
            if not links:
                continue
            # Confirm existence before assessing reachability through a VPN path.
            for _ in range(min(3, len(links))):
                if time.monotonic() >= deadline:
                    return None
                candidate = secrets.choice(links)
                links.remove(candidate)
                try:
                    final, _, _ = fetch(candidate, domains)
                    return final
                except Exception:
                    pass
        except Exception:
            pass
    return None


def check(url: str, domains: list[str]) -> bool:
    try:
        fetch(url, domains)
        return True
    except Exception:
        return False
