# Deepening

Deepen a cluster of shallow modules safely while preserving the CarCraft contracts. Use the vocabulary in [SKILL.md](SKILL.md): **module**, **interface**, **seam**, and **adapter**.

## Dependency categories

Classify each dependency before choosing a seam. Also identify the owning layer or frontend feature; dependency category never permits a forbidden import.

### 1. In-process

Use for pure domain computation and in-memory state, such as `PurchaseOrder` guards or payment amount calculations. Deepen directly and test through the new interface. Do not add an adapter.

### 2. Local-substitutable

Use for dependencies with a repository-approved local stand-in or test fixture, such as Redis, object storage, or a test database. Reuse the existing fixture or adapter; do not assume a new emulator. Keep this seam internal unless callers genuinely need to choose an implementation.

### 3. Remote but owned (Ports & Adapters)

Use for CarCraft-owned processes across a network or queue boundary. Define a port in the owning lower layer, keep orchestration in the deep module, and inject the transport adapter. For example, FastAPI publishes an event while event-worker owns ClickHouse writes; do not bypass that seam with direct DWH writes.

Describe the concrete production transport and existing test strategy. Do not invent HTTP, Kafka, or an in-memory adapter without codebase evidence.

### 4. True external (Mock)

Use for third-party systems such as ModulBank, ModulKassa, DaData, SMS, or S3-compatible storage. Put the provider-neutral port in `domain/services/` or another permitted owning layer, and the concrete adapter in `infrastructure/services/`. Test the module through a controlled fake or mock without moving provider details into the domain.

## Respect structural constraints

Before deepening backend code, trace the proposed import graph against `backend/pyproject.toml`:

- `domain` must not import application, infrastructure, presentation, database drivers, or web frameworks.
- `application` must not import presentation or ORM models.
- `presentation` must not import ORM models or repositories directly.
- infrastructure services and auth must not import ORM models; repositories own ORM access.
- domain, application, and infrastructure must not import FastAPI or Starlette.

Before deepening frontend code, read `frontend/AGENTS.md`, the governing feature code, and architecture tests:

- Preserve feature ownership and avoid imports from another feature's internals.
- Keep domain code out of root shared directories.
- Keep pages thin and use existing Composition API and Pinia patterns.
- Avoid compatibility shims and duplicate API abstractions.

Reject a deepening that merely moves coupling across a protected boundary.

## Seam discipline

- **One adapter means a hypothetical seam. Two justified adapters mean a real one.** A test double alone does not justify a new production abstraction when an existing repository or provider protocol already supplies the seam.
- **Internal seams vs external seams.** A deep module can have internal seams (private to its implementation, used by its own tests) as well as the external seam at its interface. Don't expose internal seams through the interface just because tests use them.
- **Prefer ownership over convenience.** Locate a seam where CarCraft's layer or feature owns the policy, not where the calling syntax happens to be easiest.

## Testing strategy: replace, don't layer

- Add tests at the deepened module's interface before removing old tests.
- Remove shallow-module tests only after the new tests preserve their meaningful behavioural coverage; retain contract, security, architecture, and regression tests.
- Write new tests at the deepened module's interface. The **interface is the test surface**.
- Tests assert on observable outcomes through the interface, not internal state.
- Tests should survive internal refactors — they describe behaviour, not implementation. If a test has to change when the implementation changes, it's testing past the interface.
- Run `uv run lint-imports` for backend seam changes and the relevant frontend architecture tests for feature-boundary changes, plus the checks required by the applicable `AGENTS.md`.
