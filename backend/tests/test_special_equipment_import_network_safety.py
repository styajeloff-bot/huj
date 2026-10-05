from __future__ import annotations

import socket
from typing import Any

import pytest

from domain.special_equipment_import import ImportContractError, is_forbidden_ip
from infrastructure.services import special_equipment_import_images as import_images


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "198.18.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_image_import_rejects_every_non_global_address(address: str) -> None:
    assert is_forbidden_ip(address) is True


@pytest.mark.parametrize("address", ["8.8.8.8", "2001:4860:4860::8888"])
def test_image_import_allows_global_addresses(address: str) -> None:
    assert is_forbidden_ip(address) is False


@pytest.mark.asyncio
async def test_dns_resolution_blocks_cgnat_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def cgnat_dns(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.64.0.1", 443))]

    monkeypatch.setattr(import_images.socket, "getaddrinfo", cgnat_dns)

    with pytest.raises(ImportContractError, match="IMAGE_SSRF_ADDRESS_BLOCKED"):
        await import_images._resolve_public_addresses(
            "https://media.example.test/image.png"
        )
