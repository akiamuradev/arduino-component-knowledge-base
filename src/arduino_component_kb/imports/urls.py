"""Canonical URL and network-address policy for parser requests."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import SplitResult, quote, unquote, urlsplit, urlunsplit

from arduino_component_kb.imports.domain import SourcePolicyError

ALLOWED_SOURCE_HOSTS = frozenset({"arduino-tex.ru", "portal-pk.ru", "alexgyver.ru"})
_CONTROL = re.compile(r"[\x00-\x20\x7f]")
_ENCODED_SEPARATOR = re.compile(r"%(?:2f|5c)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ApprovedUrl:
    url: str
    host: str
    path_and_query: str


def approve_source_url(value: str) -> ApprovedUrl:
    """Accept only canonical HTTPS URLs on the exact approved hosts."""
    if not value or len(value) > 2_048 or _CONTROL.search(value):
        raise SourcePolicyError("source_url_invalid")
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or parsed.hostname is None:
        raise SourcePolicyError("source_url_must_use_https")
    if parsed.username is not None or parsed.password is not None:
        raise SourcePolicyError("source_url_userinfo_forbidden")
    try:
        port = parsed.port
        host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError) as error:
        raise SourcePolicyError("source_url_host_invalid") from error
    if port not in (None, 443):
        raise SourcePolicyError("source_url_port_forbidden")
    if host not in ALLOWED_SOURCE_HOSTS:
        raise SourcePolicyError("source_host_not_allowed")
    path = _canonical_path(parsed)
    query = parsed.query
    canonical = urlunsplit(("https", host, path, query, ""))
    path_and_query = path + (f"?{query}" if query else "")
    return ApprovedUrl(canonical, host, path_and_query)


def require_public_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Reject every address that is not globally routable, including mapped IPv4."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise SourcePolicyError("source_dns_address_invalid") from error
    mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    blocked = (
        not address.is_global
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )
    mapped_blocked = mapped is not None and (
        not mapped.is_global
        or mapped.is_loopback
        or mapped.is_private
        or mapped.is_link_local
        or mapped.is_multicast
        or mapped.is_reserved
        or mapped.is_unspecified
    )
    if blocked or mapped_blocked:
        raise SourcePolicyError("source_dns_address_forbidden")
    return address


def pinned_url(
    approved: ApprovedUrl, address: ipaddress.IPv4Address | ipaddress.IPv6Address
) -> str:
    """Build the connection URL while retaining the approved path and query."""
    authority = f"[{address}]" if isinstance(address, ipaddress.IPv6Address) else str(address)
    return f"https://{authority}{approved.path_and_query}"


def _canonical_path(parsed: SplitResult) -> str:
    if "\\" in parsed.path or _ENCODED_SEPARATOR.search(parsed.path):
        raise SourcePolicyError("source_url_path_separator_forbidden")
    try:
        decoded = unquote(parsed.path or "/", errors="strict")
    except UnicodeDecodeError as error:
        raise SourcePolicyError("source_url_path_invalid") from error
    segments: list[str] = []
    for segment in decoded.split("/"):
        if segment in {"", "."}:
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    normalized = "/" + "/".join(quote(segment, safe="!$&'()*+,;=:@-._~") for segment in segments)
    if decoded.endswith("/") and normalized != "/":
        normalized += "/"
    return normalized
