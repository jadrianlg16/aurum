"""SSRF guard for server-side fetches.

``fetch_public_url(url)`` only talks to public hosts: http/https, no ``localhost``/``*.localhost``/
``host.docker.internal``/``api``, and **every** address ``getaddrinfo`` returns (IPv4-mapped IPv6
unwrapped) must be public — not loopback, private, link-local (169.254.169.254 included), multicast,
reserved or unspecified. Redirects are followed manually so each hop is re-validated, and the body is
streamed and capped at ``AURUM_FETCH_MAX_MB``. ``AURUM_ALLOW_PRIVATE_FETCH=1`` disables the address
class check for an operator ingesting from a LAN NAS (scheme/host-name rules still apply).

Residual risk (not yet verified, see docs/SECURITY.md): the resolver is consulted here and again by httpx
when it connects — a DNS answer that changes between the two lookups (rebinding) would bypass the
address check. Pinning the resolved address into the transport would close it; not done yet.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from .config import settings

BLOCKED_HOSTNAMES = frozenset({"localhost", "host.docker.internal", "api", "metadata.google.internal"})
_CHUNK = 64 * 1024


class FetchBlocked(ValueError):
    """The URL points at a scheme/host/address class we refuse to fetch."""


class FetchTooLarge(ValueError):
    """The response body exceeded ``AURUM_FETCH_MAX_MB``."""


def _unwrap(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def address_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    ip = _unwrap(ip)
    return not (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (isinstance(ip, ipaddress.IPv6Address) and ip.is_site_local)
    )


def resolve_addresses(host: str, port: int | None) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return [literal]
    try:
        infos = socket.getaddrinfo(host, port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchBlocked(f"could not resolve {host!r}") from e
    out = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    if not out:
        raise FetchBlocked(f"no addresses for {host!r}")
    return out


def check_url(url: str, *, allow_private: bool | None = None) -> None:
    """Raise ``FetchBlocked`` unless ``url`` is an http(s) URL to a public host."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchBlocked(f"scheme not allowed: {parts.scheme or '(none)'}")
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise FetchBlocked("missing host")
    if host in BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        raise FetchBlocked(f"host not allowed: {host}")
    if parts.username or parts.password:
        raise FetchBlocked("credentials in URL are not allowed")
    if allow_private is None:
        allow_private = settings().allow_private_fetch
    try:
        port = parts.port
    except ValueError as e:
        raise FetchBlocked("invalid port") from e
    addresses = resolve_addresses(host, port)
    if allow_private:
        return
    for ip in addresses:
        if not address_is_public(ip):
            raise FetchBlocked(f"address class not allowed for {host}: {_unwrap(ip)}")


def fetch_public_url(
    url: str,
    *,
    timeout: float = 20.0,
    max_bytes: int | None = None,
    max_redirects: int = 3,
    headers: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Response:
    """GET ``url`` with the SSRF rules above. Returns an ``httpx.Response`` whose ``content`` is fully
    read (so ``.text`` works); ``FetchBlocked`` / ``FetchTooLarge`` on refusal."""
    limit = max_bytes if max_bytes is not None else settings().fetch_max_mb * 1024 * 1024
    check_url(url)
    client_kwargs: dict = {"timeout": timeout, "follow_redirects": False}
    if transport is not None:
        client_kwargs["transport"] = transport
    hops = 0
    with httpx.Client(**client_kwargs) as client:
        while True:
            with client.stream("GET", url, headers=headers) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    hops += 1
                    if hops > max_redirects:
                        raise FetchBlocked(f"too many redirects (> {max_redirects})")
                    url = urljoin(url, resp.headers["location"])
                    check_url(url)
                    continue
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > limit:
                    raise FetchTooLarge(f"content-length {declared} exceeds {limit} bytes")
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes(_CHUNK):
                    total += len(chunk)
                    if total > limit:
                        raise FetchTooLarge(f"body exceeds {limit} bytes")
                    chunks.append(chunk)
                body = b"".join(chunks)  # already decoded by httpx (gzip/br), so drop the transfer headers
                kept = [(k, v) for k, v in resp.headers.multi_items() if k.lower() not in ("content-encoding", "content-length")]
                return httpx.Response(status_code=resp.status_code, headers=kept, content=body, request=resp.request)
