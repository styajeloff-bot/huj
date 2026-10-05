# Good and Bad Tests

## Good Tests

Test through a public interface and use an independently known result.

```python
from decimal import Decimal

from domain.entities.purchase_order import PurchaseOrder


def test_vehicle_reservation_money_rounds_half_up() -> None:
    payment, paid, remaining, status, payment_type = (
        PurchaseOrder.compute_amounts(
            "reservation",
            Decimal("100.05"),
            True,
            10,
        )
    )

    assert payment == Decimal("10.01")
    assert paid == Decimal("0.00")
    assert remaining == Decimal("100.05")
    assert status == "reserved"
    assert payment_type == "reservation"
```

Characteristics:

- Tests behavior users/callers care about
- Uses public API only
- Survives internal refactors
- Describes WHAT, not HOW
- One logical assertion per test

## Bad Tests

**Implementation-detail tests:** avoid asserting how an internal collaborator was
called when the owned behavior is the result.

```python
# BAD: This freezes an internal call graph but proves no purchase behavior.
await handle_purchase(command, session)
repository.create_payment.assert_awaited_once()
```

Red flags:

- Mocking internal collaborators
- Testing private methods
- Asserting on call counts/order
- Test breaks when refactoring without behavior change
- Test name describes HOW not WHAT
- Verifying through external means instead of interface

```python
# BAD: bypasses the HTTP contract to inspect storage.
response = await client.post("/api/v1/purchases", json=payload, headers=auth)
row = await session.scalar(select(PurchaseOrderModel))
assert row is not None

# GOOD: observes the API contract through the same public surface.
created = await client.post("/api/v1/purchases", json=payload, headers=auth)
listed = await client.get("/api/v1/purchases", headers=auth)
assert created.status_code == 201
created_id = created.json()["orders"][0]["id"]
assert created_id in {order["id"] for order in listed.json()["orders"]}
```

Direct database assertions are appropriate when the approved seam is the
repository or migration itself. They are a side channel when the approved seam
is an HTTP use case.

**Tautological tests:** derive expected values from the specification, not by
repeating the implementation.

```python
# BAD: recalculates the expected value with the same formula.
items = [Decimal("10"), Decimal("5")]
expected = sum(items)
assert calculate_total(items) == expected

# GOOD: uses an independent literal from the worked example.
assert calculate_total([Decimal("10"), Decimal("5")]) == Decimal("15")
```

For frontend architecture tests, assert the actual invariant rather than a
fragile text fragment where possible. Parse TypeScript/Vue source when the
contract concerns types or syntax; use a component or browser seam when the
contract concerns visible behavior.
