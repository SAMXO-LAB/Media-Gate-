"""SSRF-hardened outbound HTTP.

Every outbound request made by the API or worker goes through SafeHttpClient:

* https only;
* hostname must match the allowlist passed in by the caller;
* the hostname is resolved once, *every* resulting address is checked, and the connection is
  pinned to a vetted address (TLS still verifies the certificate against the real hostname
  via SNI), which closes the DNS-rebinding window;
* redirects are never followed automatically — each hop is re-validated the same way;
* response bodies are size-capped while streaming.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.core.errors import BlockedDestination, LimitExceeded

Resolver = Callable[[str, int], Awaitable[list[str]]]

# Ranges blocked in addition to everything Python does not consider globally routable.
_EXTRA_BLOCKED = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16", "192.0.0.0/24", "198.18.0.0/15",
    "224.0.0.0/4", "240.0.0.0/4", "255.255.255.255/32",
    "::/128", "::1/128", "64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32",
    "fc00::/7", "fe80::/10", "ff00::/8", "fd00:ec2::254/128",
)]
_METADATA_HOSTS = {"metadata.google.internal", "metadata", "instance-data", "metadata.azure.com"}


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local:
        return False
    return not any(ip in net for net in _EXTRA_BLOCKED if net.version == ip.version)


@dataclass(frozen=True)
class HostPolicy:
    """Exact hosts plus optional suffixes (e.g. '.cdninstagram.com')."""
    exact: frozenset[str] = field(default_factory=frozenset)
    suffixes: tuple[str, ...] = ()

    def allows(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        if host in _METADATA_HOSTS:
            return False
        if host in self.exact:
            return True
        return any(host.endswith(s) and len(host) > len(s) for s in self.suffixes)

    @classmethod
    def of(cls, exact: Iterable[str] = (), suffixes: Iterable[str] = ()) -> HostPolicy:
        return cls(frozenset(h.lower() for h in exact), tuple(s.lower() for s in suffixes))


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in infos))


@dataclass
class _Target:
    url: str          # URL with IP literal substituted for the host
    host: str         # original hostname (Host header + SNI)


class SafeHttpClient:
    def __init__(self, policy: HostPolicy, *, timeout: float = 20.0, max_redirects: int = 3,
                 resolver: Resolver | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 user_agent: str = "MediaGate/1.0 (+https://github.com/your-org/mediagate)") -> None:
        self.policy = policy
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.resolver = resolver or system_resolver
        self.user_agent = user_agent
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport,
                                         trust_env=False)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> SafeHttpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def vet(self, url: str) -> _Target:
        """Validate a URL and return a pinned target. Raises BlockedDestination."""
        try:
            parts = urlsplit(url)
            port = parts.port or 443
        except ValueError as exc:
            raise BlockedDestination("Outbound URL is malformed.") from exc
        if parts.scheme != "https":
            raise BlockedDestination("Only https destinations are allowed.")
        if parts.username or parts.password:
            raise BlockedDestination("Credentials in outbound URLs are not allowed.")
        host = (parts.hostname or "").lower().rstrip(".")
        if not host or not host.isascii():
            raise BlockedDestination("Outbound host is invalid.")
        try:
            ipaddress.ip_address(host)
            raise BlockedDestination("IP-literal destinations are not allowed.")
        except ValueError:
            pass
        if not self.policy.allows(host):
            raise BlockedDestination("Destination host is not allowlisted.", details={"host": host})
        if port != 443:
            raise BlockedDestination("Non-standard ports are not allowed.")
        try:
            addrs = await self.resolver(host, port)
        except OSError as exc:
            raise BlockedDestination("Destination could not be resolved.") from exc
        if not addrs:
            raise BlockedDestination("Destination could not be resolved.")
        bad = [a for a in addrs if not is_public_ip(a)]
        if bad:
            # If *any* record points somewhere private, refuse — don't pick the "good" one.
            raise BlockedDestination("Destination resolves to a non-public address.")
        ip = addrs[0]
        netloc = f"[{ip}]" if ":" in ip else ip
        pinned = urlunsplit(("https", netloc, parts.path or "/", parts.query, ""))
        return _Target(url=pinned, host=host)

    def _build(self, method: str, target: _Target, headers: dict[str, str] | None,
               params: dict[str, Any] | None, data: Any, json: Any) -> httpx.Request:
        hdrs = {"User-Agent": self.user_agent, **(headers or {}), "Host": target.host}
        req = self._client.build_request(method, target.url, headers=hdrs, params=params, data=data, json=json)
        req.extensions["sni_hostname"] = target.host
        return req

    async def _send_following(self, method: str, url: str, *, headers: dict[str, str] | None = None,
                              params: dict[str, Any] | None = None, data: Any = None, json: Any = None,
                              stream: bool = False) -> httpx.Response:
        current = url
        for hop in range(self.max_redirects + 1):
            target = await self.vet(current)
            req = self._build(method, target, headers, params if hop == 0 else None,
                              data if hop == 0 else None, json if hop == 0 else None)
            resp = await self._client.send(req, stream=stream)
            if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                await resp.aclose()
                current = urljoin(current, resp.headers["location"])
                if resp.status_code == 303:
                    method = "GET"
                continue
            return resp
        raise BlockedDestination("Too many redirects.")

    async def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        resp = await self._send_following(method, url, **kw)
        await resp.aread()
        return resp

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw: Any) -> httpx.Response:
        return await self.request("POST", url, **kw)

    @asynccontextmanager
    async def stream(self, url: str, *, max_bytes: int, headers: dict[str, str] | None = None
                     ) -> AsyncIterator[tuple[httpx.Response, AsyncIterator[bytes]]]:
        """Stream a GET body, raising LimitExceeded once max_bytes is passed."""
        resp = await self._send_following("GET", url, headers=headers, stream=True)
        try:
            declared = resp.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise LimitExceeded("This file is larger than the allowed size.")

            async def body() -> AsyncIterator[bytes]:
                total = 0
                async for chunk in resp.aiter_bytes(64 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise LimitExceeded("This file is larger than the allowed size.")
                    yield chunk

            yield resp, body()
        finally:
            await resp.aclose()


# Purpose-specific allowlists ------------------------------------------------

API_HOSTS = HostPolicy.of(exact={
    "www.googleapis.com", "youtube.googleapis.com",
    "graph.instagram.com", "api.instagram.com",
    "api.x.com", "api.twitter.com",
})

# Media CDNs that official APIs hand back as file URLs. Never user-supplied.
MEDIA_HOSTS = HostPolicy.of(
    exact={"video.twimg.com", "pbs.twimg.com"},
    suffixes=(".cdninstagram.com", ".fbcdn.net"),
)
