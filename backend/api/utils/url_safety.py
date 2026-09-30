"""URL validation for media imports (SSRF protection).

A URL is accepted only if:
  * scheme is http/https, no embedded credentials, default port only;
  * the host is (a subdomain of) an allow-listed import domain;
  * every IP address the host resolves to is public (not private, loopback,
    link-local, multicast, reserved or unspecified).
"""

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from api.core.exceptions import ImportRejectedError

Resolver = Callable[[str], Iterable[str]]


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return list({info[4][0] for info in infos})


def host_matches_allowlist(host: str, allowed_domains: Iterable[str]) -> bool:
    host = host.lower().rstrip(".")
    for domain in allowed_domains:
        domain = domain.lower().strip().lstrip(".").rstrip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            return True
    return False


def is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    )


def validate_import_url(
    url: str,
    allowed_domains: Iterable[str],
    resolver: Resolver | None = None,
) -> str:
    allowed_domains = list(allowed_domains)
    if not url or len(url) > 2048:
        raise ImportRejectedError("URL is empty or too long")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise ImportRejectedError("URL is malformed") from exc

    if parts.scheme not in ("http", "https"):
        raise ImportRejectedError("Only http and https URLs can be imported")
    if parts.username or parts.password:
        raise ImportRejectedError("URLs with embedded credentials are not allowed")
    host = (parts.hostname or "").lower()
    if not host:
        raise ImportRejectedError("URL has no host")
    if port is not None and port not in (80, 443):
        raise ImportRejectedError("Non-standard ports are not allowed")

    # Literal IP hosts are never on the allowlist, but reject explicitly for a clear message.
    try:
        ipaddress.ip_address(host.strip("[]"))
        raise ImportRejectedError("IP address hosts are not allowed; use a supported site URL")
    except ValueError:
        pass

    if not host_matches_allowlist(host, allowed_domains):
        raise ImportRejectedError(
            f"'{host}' is not a supported import source",
            details={"allowed_domains": allowed_domains},
        )

    resolve = resolver or _default_resolver
    try:
        addresses = list(resolve(host))
    except (OSError, UnicodeError) as exc:
        raise ImportRejectedError(f"Could not resolve host '{host}'") from exc
    if not addresses:
        raise ImportRejectedError(f"Could not resolve host '{host}'")
    for address in addresses:
        if not is_public_ip(address):
            raise ImportRejectedError("URL resolves to a private or reserved network address")

    return parts.geturl()
