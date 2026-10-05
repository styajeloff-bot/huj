# When to Mock

Prefer real domain and application behavior. Mock, fake, or override at
**system boundaries**:

- External providers such as ModulBank, ModulKassa, SMS, DaData, S3, and 1C
- Kafka/ClickHouse edges when the test does not own those services
- Time, randomness, and scheduling
- Filesystem or network access
- The database only when persistence is not part of the behavior; otherwise use
  the test database

Avoid mocking:

- Domain entities, value objects, and business guards
- Private methods or internal call chains
- Pydantic schemas and serialization
- Internal functions only to assert call counts or ordering

An application handler may currently import a repository or infrastructure
service directly. If that boundary would make a test slow or non-deterministic,
patch the symbol as imported by the handler, return the same dictionary contract
as the real repository, and assert the handler's public result or domain error.
Do not make the mock interaction itself the behavior under test.

For FastAPI route tests, prefer `app.dependency_overrides`, `httpx.AsyncClient`,
and the test database over mocking router internals. For Nuxt/Vue, stub `$fetch`
or an external browser boundary, not a composable's internal helpers.

## Designing for Mockability

At system boundaries, design interfaces that are easy to mock:

**1. Use dependency injection**

Pass external dependencies in rather than creating them internally:

```python
from decimal import Decimal
from typing import Protocol


class PaymentGateway(Protocol):
    async def charge(self, amount: Decimal) -> str: ...


async def collect_payment(amount: Decimal, gateway: PaymentGateway) -> str:
    return await gateway.charge(amount)
```

Keep provider interfaces in the layer allowed by the applicable backend
`AGENTS.md`. Read runtime configuration through
`infrastructure.settings.settings`, never directly from `os.environ`.

**2. Prefer operation-specific interfaces over generic fetchers**

```typescript
interface CompanyLookup {
  searchByInn(inn: string): Promise<CompanyInfo>
}
```

Operation-specific boundaries provide:

- Each mock returns one specific shape
- No conditional logic in test setup
- Easier to see which endpoints a test exercises
- Type safety per endpoint

Do not proliferate frontend API client classes to achieve this. Follow
`frontend/AGENTS.md`: use the established `$fetch` convention and isolate only
the external request boundary needed by the test.
