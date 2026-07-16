"""Source allowlist, URL canonicalization, and address policy tests."""

from __future__ import annotations

import pytest

from arduino_component_kb.imports.domain import SourcePolicyError
from arduino_component_kb.imports.urls import (
    ALLOWED_SOURCE_HOSTS,
    approve_source_url,
    require_public_address,
)


def test_exact_allowlist_and_canonical_fragment_removal() -> None:
    assert ALLOWED_SOURCE_HOSTS == {"arduino-tex.ru", "portal-pk.ru", "alexgyver.ru"}
    approved = approve_source_url("HTTPS://ARDUINO-TEX.RU:443/news/229/item.html#ignored")
    assert approved.url == "https://arduino-tex.ru/news/229/item.html"
    assert approved.host == "arduino-tex.ru"


@pytest.mark.parametrize(
    "value",
    [
        "http://arduino-tex.ru/news/1/item.html",
        "https://www.arduino-tex.ru/news/1/item.html",
        "https://arduino-tex.ru.evil.invalid/news/1/item.html",
        "https://user@arduino-tex.ru/news/1/item.html",
        "https://arduino-tex.ru:8443/news/1/item.html",
        "https://127.0.0.1/news/1/item.html",
        "file://arduino-tex.ru/etc/passwd",
        "gopher://arduino-tex.ru/news/1/item.html",
        "https://user:password@arduino-tex.ru/news/1/item.html",
    ],
)
def test_source_url_policy_fails_closed(value: str) -> None:
    with pytest.raises(SourcePolicyError):
        approve_source_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://arduino-tex.ru/news%2f229/article.html",
        "https://arduino-tex.ru/news%5C229/article.html",
        "https://arduino-tex.ru/news\\229/article.html",
    ],
)
def test_ambiguous_path_separators_are_rejected(value: str) -> None:
    with pytest.raises(SourcePolicyError, match="source_url_path_separator_forbidden"):
        approve_source_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_non_global_network_ranges_are_rejected(value: str) -> None:
    with pytest.raises(SourcePolicyError, match="source_dns_address_forbidden"):
        require_public_address(value)


def test_global_network_address_is_accepted() -> None:
    assert str(require_public_address("93.184.216.34")) == "93.184.216.34"
