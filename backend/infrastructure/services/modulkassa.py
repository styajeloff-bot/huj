"""ModulKassa fiscal receipt service."""
import datetime
import logging
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from domain.values import PaymentMethod
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


def callback_auth_required() -> bool:
    """Require the app secret when configured or on secure deployments."""

    secure_external_callback = (
        settings.cookie_secure
        and settings.modulkassa_callback_url.startswith("https://")
    )
    return bool(
        settings.modulkassa_callback_token
        or settings.modulkassa_callback_token_required
        or secure_external_callback
    )


def callback_url() -> str:
    """Return the provider callback URL with an app-controlled secret."""

    configured_url = settings.modulkassa_callback_url
    token = settings.modulkassa_callback_token
    if callback_auth_required() and not token:
        raise RuntimeError("ModulKassa callback token is not configured")
    if not token:
        return configured_url
    parts = urlsplit(configured_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["token"] = token
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


async def create_receipt(receipt_data: dict[str, Any]) -> dict[str, Any]:
    url = f"{settings.modulkassa_api_url}/retail-point/{settings.modulkassa_retail_point_id}/doc"
    logger.info("ModulKassa: creating receipt %s", receipt_data.get("id"))
    async with httpx.AsyncClient(
        timeout=settings.modulkassa_create_receipt_timeout
    ) as client:
        resp = await client.post(
            url,
            json=receipt_data,
            auth=(settings.modulkassa_login, settings.modulkassa_password),
        )
        resp.raise_for_status()
        logger.info(
            "ModulKassa: receipt %s created, status %s",
            receipt_data.get("id"),
            resp.status_code,
        )
        result: dict[str, Any] = resp.json()
        return result


async def check_receipt_status(receipt_id: str) -> dict[str, Any]:
    url = (
        f"{settings.modulkassa_api_url}/retail-point/{settings.modulkassa_retail_point_id}"
        f"/doc/{receipt_id}/status"
    )
    async with httpx.AsyncClient(
        timeout=settings.modulkassa_check_status_timeout
    ) as client:
        resp = await client.get(url, auth=(settings.modulkassa_login, settings.modulkassa_password))
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result


def build_receipt_payload(
    payment: dict[str, Any] | Any,
    order: dict[str, Any] | Any,
    scenario: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build fiscal receipt payload for ModulKassa."""
    if extra is None:
        extra = {}

    receipt_id = f"{payment['id']}-{int(time.time() * 1000)}"
    vehicle_description = (
        f"{order.get('mark_name', '')} {order.get('model_name', '')}".strip()
    )
    vin_suffix = f", VIN: {order['vin']}" if order.get("vin") else ""

    base = {
        "id": receipt_id,
        "docNum": f"CARCRAFT-{payment['id']}",
        "docType": "SALE",
        "checkoutDateTime": datetime.datetime.now(datetime.UTC).isoformat(),
        "email": extra.get("email"),
        "phone": extra.get("phone"),
        "printReceipt": False,
        "cashierName": settings.modulkassa_cashier_name,
        "cashierPosition": settings.modulkassa_cashier_position,
        "responseURL": callback_url(),
        "taxMode": "COMMON",
        "clientName": extra.get("clientName"),
    }

    amount = float(payment["amount"])
    payment_type_str = (
        "CASHLESS" if payment.get("payment_method") == PaymentMethod.SBP else "CARD"
    )

    if scenario == "full_payment":
        return {
            **base,
            "inventPositions": [
                {
                    "name": f"Автомобиль {vehicle_description}{vin_suffix}",
                    "price": amount,
                    "quantity": 1,
                    "measure": "pcs",
                    "vatTag": 1113,
                    "paymentObject": "commodity",
                    "paymentMethod": "full_payment",
                    "discSum": 0,
                }
            ],
            "moneyPositions": [{"paymentType": payment_type_str, "sum": amount}],
        }
    if scenario == "advance":
        return {
            **base,
            "inventPositions": [
                {
                    "name": f"Аванс за автомобиль {vehicle_description}{vin_suffix}",
                    "price": amount,
                    "quantity": 1,
                    "measure": "pcs",
                    "vatTag": 1113,
                    "paymentObject": "payment",
                    "paymentMethod": "advance",
                    "discSum": 0,
                }
            ],
            "moneyPositions": [{"paymentType": payment_type_str, "sum": amount}],
        }
    if scenario == "final_after_advance":
        advance_amount = float(extra.get("advanceAmount", 0))
        total_price = float(order["total_price"])
        return {
            **base,
            "inventPositions": [
                {
                    "name": f"Автомобиль {vehicle_description}{vin_suffix}",
                    "price": total_price,
                    "quantity": 1,
                    "measure": "pcs",
                    "vatTag": 1113,
                    "paymentObject": "commodity",
                    "paymentMethod": "full_payment",
                    "discSum": 0,
                }
            ],
            "moneyPositions": [
                {"paymentType": "PREPAID", "sum": advance_amount},
                {"paymentType": payment_type_str, "sum": amount},
            ],
        }
    raise ValueError(f"Unknown fiscal scenario: {scenario}")
