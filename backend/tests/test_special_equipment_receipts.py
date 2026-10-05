"""Receipt ingestion security and special-equipment persistence tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest

from application import special_equipment_commerce as commerce
from infrastructure.services import payment_gateway, special_equipment_receipts
from infrastructure.services.payment_models import ModulkassaWebhookPayload
from presentation.routers import payments as payments_router
from tests.fakes.object_storage import FakeObjectStorage


async def _allow_public_dns(url: str) -> tuple[str, tuple[str, ...]]:
    hostname = urlsplit(url).hostname
    assert hostname is not None
    return hostname, ("93.184.216.34",)


@pytest.mark.asyncio
async def test_receipt_pdf_is_stored_under_deterministic_private_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid4()
    pdf = b"%PDF-1.7\nreceipt"
    storage = FakeObjectStorage("https://s3.invalid/private")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://93.184.216.34/r/42")
        assert request.headers["host"] == "receipts.example.test"
        assert request.extensions["sni_hostname"] == "receipts.example.test"
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf; charset=binary"},
            content=pdf,
        )

    monkeypatch.setattr(
        special_equipment_receipts,
        "_resolve_public_addresses",
        _allow_public_dns,
    )
    key = await special_equipment_receipts.ingest_receipt_pdf(
        payment_id=payment_id,
        source_url="https://receipts.example.test/r/42",
        storage=storage,
        allowed_hosts=frozenset({"receipts.example.test"}),
        transport=httpx.MockTransport(handler),
    )

    assert key == f"special-equipment/receipts/{payment_id}/receipt.pdf"
    assert storage.items[key].data == pdf
    assert storage.items[key].content_type == "application/pdf"
    assert "s3.invalid" not in key


@pytest.mark.asyncio
async def test_receipt_download_repins_each_redirect_hop_for_ipv4_and_ipv6(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_urls: list[str] = []
    requests: list[tuple[str, str, str]] = []

    async def resolve(url: str) -> tuple[str, tuple[str, ...]]:
        resolved_urls.append(url)
        hostname = urlsplit(url).hostname
        assert hostname is not None
        if hostname == "receipts.example.test":
            return hostname, ("93.184.216.34",)
        return hostname, ("2606:2800:220:1:248:1893:25c8:1946",)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                str(request.url),
                request.headers["host"],
                request.extensions["sni_hostname"],
            )
        )
        if request.url.host == "93.184.216.34":
            return httpx.Response(
                302,
                headers={
                    "Location": "https://cdn.example.test/final.pdf?token=opaque"
                },
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF-1.7\nredirected",
        )

    monkeypatch.setattr(
        special_equipment_receipts,
        "_resolve_public_addresses",
        resolve,
    )
    body = await special_equipment_receipts.fetch_receipt_pdf(
        "https://receipts.example.test/start",
        allowed_hosts=frozenset(
            {"receipts.example.test", "cdn.example.test"}
        ),
        transport=httpx.MockTransport(handler),
    )

    assert body == b"%PDF-1.7\nredirected"
    assert resolved_urls == [
        "https://receipts.example.test/start",
        "https://cdn.example.test/final.pdf?token=opaque",
    ]
    assert requests == [
        (
            "https://93.184.216.34/start",
            "receipts.example.test",
            "receipts.example.test",
        ),
        (
            "https://[2606:2800:220:1:248:1893:25c8:1946]/final.pdf?token=opaque",
            "cdn.example.test",
            "cdn.example.test",
        ),
    ]


@pytest.mark.asyncio
async def test_receipt_client_disables_proxy_and_connection_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    class Response:
        is_redirect = False
        status_code = 200

        def __init__(self) -> None:
            self.headers = {"content-type": "application/pdf"}

        async def aiter_bytes(self, _size: int) -> AsyncIterator[bytes]:
            yield b"%PDF-1.7\npinned"

    class Stream:
        async def __aenter__(self) -> Response:
            return Response()

        async def __aexit__(self, *_args: Any) -> None:
            return None

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            calls["client"] = kwargs

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: Any) -> Stream:
            calls["request"] = (method, url, kwargs)
            return Stream()

    async def resolve(_url: str) -> tuple[str, tuple[str, ...]]:
        return "receipts.example.test", ("93.184.216.34",)

    transport = httpx.MockTransport(
        lambda _request: pytest.fail("fake client owns the request")
    )
    monkeypatch.setattr(special_equipment_receipts.httpx, "AsyncClient", Client)
    monkeypatch.setattr(
        special_equipment_receipts,
        "_resolve_public_addresses",
        resolve,
    )

    body = await special_equipment_receipts.fetch_receipt_pdf(
        "https://receipts.example.test/receipt.pdf",
        allowed_hosts=frozenset({"receipts.example.test"}),
        transport=transport,
    )

    assert body == b"%PDF-1.7\npinned"
    assert calls["client"]["trust_env"] is False
    assert calls["client"]["follow_redirects"] is False
    assert calls["client"]["transport"] is transport
    assert calls["client"]["limits"].max_keepalive_connections == 0
    method, url, request = calls["request"]
    assert (method, url) == ("GET", "https://93.184.216.34/receipt.pdf")
    assert request["headers"]["Host"] == "receipts.example.test"
    assert request["extensions"] == {"sni_hostname": "receipts.example.test"}


@pytest.mark.asyncio
async def test_receipt_ingestion_replay_does_not_refetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid4()
    key = special_equipment_receipts.receipt_storage_key(payment_id)
    storage = FakeObjectStorage()
    await storage.put(key, b"%PDF-1.7\nexisting", "application/pdf")

    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        pytest.fail("idempotent replay must not perform provider I/O")

    monkeypatch.setattr(
        special_equipment_receipts,
        "_resolve_public_addresses",
        _allow_public_dns,
    )
    replayed_key = await special_equipment_receipts.ingest_receipt_pdf(
        payment_id=payment_id,
        source_url="https://receipts.example.test/replayed",
        storage=storage,
        allowed_hosts=frozenset({"receipts.example.test"}),
        transport=httpx.MockTransport(unexpected_request),
    )

    assert replayed_key == key
    assert storage.items[key].data == b"%PDF-1.7\nexisting"


@pytest.mark.asyncio
async def test_receipt_download_blocks_private_dns_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def private_dns(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        return [(2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(special_equipment_receipts.socket, "getaddrinfo", private_dns)

    with pytest.raises(
        special_equipment_receipts.ReceiptIngestionError,
        match="RECEIPT_SSRF_ADDRESS_BLOCKED",
    ):
        await special_equipment_receipts.fetch_receipt_pdf(
            "https://internal.example.test/receipt.pdf",
            allowed_hosts=frozenset({"internal.example.test"}),
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    headers={"Content-Type": "application/pdf"},
                    content=b"%PDF-1.7",
                )
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "body", "max_bytes", "expected_code"),
    [
        ("text/html", b"%PDF-1.7", 1024, "RECEIPT_CONTENT_TYPE_INVALID"),
        ("application/pdf", b"not-a-pdf", 1024, "RECEIPT_PDF_MAGIC_INVALID"),
        ("application/pdf", b"%PDF-1.7-too-large", 8, "RECEIPT_SIZE_EXCEEDED"),
    ],
)
async def test_receipt_download_rejects_invalid_content_and_size(
    monkeypatch: pytest.MonkeyPatch,
    content_type: str,
    body: bytes,
    max_bytes: int,
    expected_code: str,
) -> None:
    monkeypatch.setattr(
        special_equipment_receipts,
        "_resolve_public_addresses",
        _allow_public_dns,
    )
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"Content-Type": content_type},
            content=body,
        )
    )

    with pytest.raises(
        special_equipment_receipts.ReceiptIngestionError,
        match=expected_code,
    ):
        await special_equipment_receipts.fetch_receipt_pdf(
            "https://receipts.example.test/receipt.pdf",
            allowed_hosts=frozenset({"receipts.example.test"}),
            transport=transport,
            max_bytes=max_bytes,
        )


class _FakeSession:
    def __init__(self, active: list[int]) -> None:
        self.active = active

    async def __aenter__(self) -> _FakeSession:
        self.active[0] += 1
        return self

    async def __aexit__(self, *_args: Any) -> None:
        self.active[0] -= 1

    async def commit(self) -> None:
        return None


class _FakeSessionFactory:
    def __init__(self, active: list[int]) -> None:
        self.active = active

    def __call__(self) -> AbstractAsyncContextManager[_FakeSession]:
        return _FakeSession(self.active)


@pytest.mark.asyncio
async def test_receipt_key_persists_after_network_outside_db_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid4()
    payment: dict[str, Any] = {
        "id": payment_id,
        "fiscal_status": "completed",
        "fiscal_receipt_id": "fiscal-42",
        "receipt_storage_key": None,
    }
    active_sessions = [0]
    updates: list[dict[str, Any]] = []

    async def get_payment(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return dict(payment)

    async def update_payment(
        _session: Any,
        _payment_id: Any,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        updates.append(dict(changes))
        payment.update(changes)
        return dict(payment)

    async def ingest(**_kwargs: Any) -> str:
        assert active_sessions[0] == 0
        return special_equipment_receipts.receipt_storage_key(payment_id)

    monkeypatch.setattr(
        payment_gateway,
        "AsyncSessionLocal",
        _FakeSessionFactory(active_sessions),
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_repo,
        "get_payment",
        get_payment,
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_repo,
        "update_payment",
        update_payment,
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_receipts,
        "ingest_receipt_pdf",
        ingest,
    )
    monkeypatch.setattr(payment_gateway, "get_object_storage", object)

    success = await payment_gateway._receipt_ingestion_attempt(
        payment_id,
        "https://receipts.example.test/r/42",
        0,
    )

    assert success is True
    assert payment["receipt_storage_key"] == (
        f"special-equipment/receipts/{payment_id}/receipt.pdf"
    )
    assert updates[-1]["receipt_ingestion_status"] == "completed"
    assert "fiscal_status" not in updates[-1]


@pytest.mark.asyncio
async def test_receipt_failure_is_retryable_without_reverting_fiscal_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid4()
    payment: dict[str, Any] = {
        "id": payment_id,
        "fiscal_status": "completed",
        "fiscal_receipt_id": "fiscal-42",
        "receipt_storage_key": None,
    }
    active_sessions = [0]
    updates: list[dict[str, Any]] = []

    async def get_payment(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return dict(payment)

    async def update_payment(
        _session: Any,
        _payment_id: Any,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        updates.append(dict(changes))
        payment.update(changes)
        return dict(payment)

    async def fail_ingest(**_kwargs: Any) -> str:
        assert active_sessions[0] == 0
        raise special_equipment_receipts.ReceiptIngestionError(
            "RECEIPT_CONTENT_TYPE_INVALID"
        )

    monkeypatch.setattr(
        payment_gateway,
        "AsyncSessionLocal",
        _FakeSessionFactory(active_sessions),
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_repo,
        "get_payment",
        get_payment,
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_repo,
        "update_payment",
        update_payment,
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_receipts,
        "ingest_receipt_pdf",
        fail_ingest,
    )
    monkeypatch.setattr(payment_gateway, "get_object_storage", object)

    success = await payment_gateway._receipt_ingestion_attempt(
        payment_id,
        "https://receipts.example.test/r/42",
        0,
    )

    assert success is False
    assert payment["fiscal_status"] == "completed"
    assert payment["receipt_ingestion_status"] == "failed"
    assert payment["receipt_ingestion_error_code"] == (
        "RECEIPT_CONTENT_TYPE_INVALID"
    )
    assert payment["receipt_ingestion_next_retry_at"] > datetime.now(UTC)
    assert all("fiscal_status" not in update for update in updates)


@pytest.mark.asyncio
async def test_fiscal_callback_keeps_provider_url_ephemeral_and_replay_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid4()
    payment: dict[str, Any] = {
        "id": payment_id,
        "fiscal_receipt_id": "fiscal-42",
        "receipt_storage_key": None,
    }
    updates: list[dict[str, Any]] = []

    async def no_legacy_payment(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def get_special_payment(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return dict(payment)

    async def update_payment(
        _session: Any,
        _payment_id: Any,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        updates.append(dict(changes))
        payment.update(changes)
        return dict(payment)

    monkeypatch.setattr(
        payment_gateway.repo,
        "get_payment_by_fiscal_receipt_id",
        no_legacy_payment,
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_repo,
        "get_payment_by_fiscal_receipt_id",
        get_special_payment,
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_repo,
        "update_payment",
        update_payment,
    )
    callback = ModulkassaWebhookPayload.model_validate(
        {
            "id": "fiscal-42",
            "status": "COMPLETED",
            "ofdReceiptUrl": "https://provider.example.test/private/42.pdf",
            "secretProviderField": "must-not-persist",
        }
    )

    jobs = await payment_gateway.handle_fiscal_callback(callback, object())  # type: ignore[arg-type]

    assert jobs == [
        (payment_id, "https://provider.example.test/private/42.pdf")
    ]
    assert updates[-1]["fiscal_response"] == {
        "id": "fiscal-42",
        "status": "COMPLETED",
    }
    assert "provider.example.test" not in repr(updates[-1])
    assert "secretProviderField" not in repr(updates[-1])

    payment["receipt_ingestion_status"] = "processing"
    in_flight_replay_jobs = await payment_gateway.handle_fiscal_callback(
        callback,
        object(),  # type: ignore[arg-type]
    )
    assert in_flight_replay_jobs == []
    assert updates[-1]["receipt_ingestion_status"] == "processing"

    payment["receipt_storage_key"] = (
        f"special-equipment/receipts/{payment_id}/receipt.pdf"
    )
    replay_jobs = await payment_gateway.handle_fiscal_callback(
        callback,
        object(),  # type: ignore[arg-type]
    )
    assert replay_jobs == []
    assert updates[-1]["receipt_ingestion_status"] == "completed"


@pytest.mark.asyncio
async def test_fiscal_webhook_schedules_receipt_only_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid4()
    source_url = "https://provider.example.test/private/42.pdf"
    committed = False
    scheduled: list[tuple[Any, Any]] = []

    class Request:
        async def json(self) -> dict[str, str]:
            return {"id": "fiscal-42", "status": "COMPLETED"}

    class Session:
        async def commit(self) -> None:
            nonlocal committed
            committed = True

        async def rollback(self) -> None:
            pytest.fail("successful callback must not roll back")

    async def handle(*_args: Any, **_kwargs: Any) -> list[tuple[Any, Any]]:
        return [(payment_id, source_url)]

    def start(received_payment_id: Any, received_url: Any) -> None:
        assert committed is True
        scheduled.append((received_payment_id, received_url))

    monkeypatch.setattr(
        payments_router.payment_gateway,
        "handle_fiscal_callback",
        handle,
    )
    monkeypatch.setattr(
        payments_router.payment_gateway,
        "start_special_equipment_receipt_task",
        start,
    )

    response = await payments_router.webhook_modulkassa(
        Request(),  # type: ignore[arg-type]
        Session(),  # type: ignore[arg-type]
    )

    assert response.status_code == 200
    assert scheduled == [(payment_id, source_url)]


@pytest.mark.asyncio
async def test_payment_status_exposes_only_fastapi_receipt_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    order_id = uuid4()
    payment_id = uuid4()

    async def get_order(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": order_id, "user_id": user_id}

    async def get_payment(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": payment_id,
            "purchase_order_id": order_id,
            "status": "completed",
            "fiscal_status": "completed",
            "receipt_storage_key": (
                f"special-equipment/receipts/{payment_id}/receipt.pdf"
            ),
            "receipt_provider_url": "https://provider.invalid/private.pdf",
            "expires_at": None,
            "paid_at": datetime.now(UTC),
        }

    monkeypatch.setattr(commerce.repo, "get_order", get_order)
    monkeypatch.setattr(commerce.repo, "get_payment", get_payment)

    result = await commerce.get_payment_status(
        user_id,
        order_id,
        payment_id,
        object(),  # type: ignore[arg-type]
    )

    assert result["receipt_content_url"] == (
        f"/api/v1/special-equipment/purchase-orders/{order_id}"
        f"/payments/{payment_id}/receipt/content"
    )
    assert "provider.invalid" not in repr(result)
    assert "special-equipment/receipts" not in repr(result)
