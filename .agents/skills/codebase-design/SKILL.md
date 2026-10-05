---
name: codebase-design
description: Design or improve deep modules in CarCraft while preserving its FastAPI layer contracts, Nuxt feature boundaries, domain vocabulary, and architecture decisions. Use when choosing an interface or seam, deepening shallow code, improving testability or locality, or comparing architectural alternatives.
---

# Codebase Design

Design **deep modules**: put substantial behaviour behind a small interface at a clean seam, then test through that interface. Aim for leverage for callers, locality for maintainers, and testability.

## Establish project constraints first

Before proposing a design:

1. Read the root `AGENTS.md` and every nested `AGENTS.md` that governs the affected files.
2. For backend work, inspect the active `import-linter` contracts in `backend/pyproject.toml`.
3. Read `docs/glossary.md` for business vocabulary.
4. Read the relevant maps in `docs/architecture/` and accepted decisions in `docs/decisions/`.
5. Inspect the current callers and tests. Treat code as evidence, but do not use existing accidental coupling to override explicit project contracts.

Subject to higher-level platform policy, current explicit user instructions
override repository defaults for the task. Record any such exception instead of
silently generalizing it. Otherwise reject a proposal that violates an
applicable `AGENTS.md`, `import-linter` contract, architecture test, or accepted
ADR, even if it would make a module deeper. If repository documents conflict,
follow the closest applicable `AGENTS.md` and flag the discrepancy.

## Glossary

Use these design terms consistently. Keep CarCraft business terms exactly as defined in `docs/glossary.md`; for example, distinguish a **Leasing Application**, **Purchase Order**, **Payment**, **Company**, **Dealer**, and **Distributor**.

**Module** — anything with an interface and an implementation: a function, class, package, feature, or tier-spanning slice. Use framework terms such as Vue component, Pinia store, or infrastructure service when referring to that concrete artifact; use **module** when discussing its design.

**Interface** — everything a caller must know to use the module correctly: type signatures, invariants, ordering constraints, error modes, required configuration, and relevant performance characteristics. Do not reduce it to a Python protocol, TypeScript type, or HTTP API alone.

**Implementation** — what's inside a module, its body of code. Distinct from **Adapter**: a thing can be a small adapter with a large implementation (a Postgres repo) or a large adapter with a small implementation (an in-memory fake). Reach for "adapter" when the seam is the topic; "implementation" otherwise.

**Depth** — leverage at the interface: the amount of behaviour a caller (or test) can exercise per unit of interface they have to learn. A module is **deep** when a large amount of behaviour sits behind a small interface, **shallow** when the interface is nearly as complex as the implementation.

**Seam** _(Michael Feathers)_ — a place where behaviour can change without editing the caller; the location at which a module's interface lives. Choose the seam separately from choosing its implementation. Do not use “boundary” as a synonym because it is overloaded in DDD.

**Adapter** — a concrete thing that satisfies an interface at a seam. Describes *role* (what slot it fills), not substance (what's inside).

**Leverage** — what callers get from depth: more capability per unit of interface they learn. One implementation pays back across N call sites and M tests.

**Locality** — what maintainers get from depth: change, bugs, knowledge, and verification concentrate in one place rather than spreading across callers. Fix once, fixed everywhere.

## Deep vs shallow

**Deep module** = small interface + lots of implementation:

```
┌─────────────────────┐
│   Small Interface   │  ← Few methods, simple params
├─────────────────────┤
│                     │
│  Deep Implementation│  ← Complex logic hidden
│                     │
└─────────────────────┘
```

**Shallow module** = large interface + little implementation (avoid):

```
┌─────────────────────────────────┐
│       Large Interface           │  ← Many methods, complex params
├─────────────────────────────────┤
│  Thin Implementation            │  ← Just passes through
└─────────────────────────────────┘
```

When designing an interface, ask:

- Can I reduce the number of methods?
- Can I simplify the parameters?
- Can I hide more complexity inside?

## Principles

- **Depth is a property of the interface, not the implementation.** A deep module can be internally composed of small, mockable, swappable parts — they just aren't part of the interface. A module can have **internal seams** (private to its implementation, used by its own tests) as well as the **external seam** at its interface.
- **The deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam. If you want to test *past* the interface, the module is probably the wrong shape.
- **One adapter means a hypothetical seam. Two justified adapters mean a real one.** Do not introduce a port only to make mocking possible. Prefer existing CarCraft seams and add a new one when production behaviour genuinely varies or an external dependency must be isolated.
- **Architecture contracts outrank local convenience.** Depth never justifies a forbidden import, ORM leakage, HTTP concerns in lower layers, or a cross-feature internal import.

## CarCraft seam placement

### Backend: Python 3.12 and FastAPI

Keep the enforced dependency direction in `backend/pyproject.toml`:

- Keep `domain/` pure: no I/O, FastAPI, SQLAlchemy, or other application layers.
- Put use-case orchestration in `application/commands/` or `application/queries/`; delegate business guards to domain entities.
- Keep HTTP schemas, role dependencies, response metadata, commits, and HTTP error mapping in `presentation/`.
- Define ORM models in `infrastructure/models/`. Keep ORM access and queries in
  `infrastructure/repositories/`, and return dictionaries rather than ORM
  objects across the repository seam.
- Put external adapters and settings in `infrastructure/`; read configuration through `infrastructure.settings.settings`.
- Preserve event-worker ownership of ClickHouse writes. FastAPI may only read through the approved read-only infrastructure.

Prefer an existing domain `Protocol` for a true external dependency. For
example, `CompanyLookupProvider` keeps DaData details behind the established
domain seam while the application handler owns input policy:

```python
async def handle_search_company(
    query: SearchCompanyQuery,
    provider: CompanyLookupProvider,
) -> list[CompanyInfo]:
    text = query.query.strip()
    if len(text) < 2:
        return []
    return await provider.search(text, query.limit)
```

Do not move this orchestration into a FastAPI router, make a domain entity
perform I/O, or expose a SQLAlchemy model through the interface. A new port
such as a payment gateway requires a separately approved architecture change;
do not present a proposed seam as an existing contract.

### Frontend: Nuxt 3 and Vue 3

- Place domain modules under `frontend/features/<domain>/`.
- Keep pages as thin routing shells and root components/composables/stores for genuinely shared or cross-cutting concerns.
- Do not import another feature's internals. Consume its intentional public surface or move genuinely shared behaviour to an approved shared location.
- Use Vue Composition API, Pinia, and the repository's established `$fetch` conventions. Do not introduce another state or API-client abstraction merely to create a seam.
- Preserve opaque UUID strings and backend response contracts.

Inject or pass an existing feature dependency when it makes behaviour independently testable:

```typescript
export function usePurchaseCheckout(api: PurchaseApi) {
  async function submit(orderId: string): Promise<PurchaseOrder> {
    return await api.submit(orderId)
  }

  return { submit }
}
```

Keep the composable's interface smaller than the workflow it hides. Do not expose transport details or store internals unless callers need them.

## Evaluate a proposal

Require each proposal to state:

1. The module, its callers, and the seam.
2. The complete interface: types, invariants, errors, ordering, and effects.
3. What complexity the implementation hides.
4. Which `AGENTS.md`, `import-linter` contracts, architecture tests, and ADRs constrain it.
5. How callers and tests exercise the same observable behaviour.
6. Which old paths can be removed instead of layered under compatibility wrappers.

## Relationships

- A **Module** has exactly one **Interface** (the surface it presents to callers and tests).
- **Depth** is a property of a **Module**, measured against its **Interface**.
- A **Seam** is where a **Module**'s **Interface** lives.
- An **Adapter** sits at a **Seam** and satisfies the **Interface**.
- **Depth** produces **Leverage** for callers and **Locality** for maintainers.

## Rejected framings

- **Depth as ratio of implementation-lines to interface-lines** (Ousterhout): rewards padding the implementation. We use depth-as-leverage instead.
- **"Interface" as the TypeScript `interface` keyword or a class's public methods**: too narrow — interface here includes every fact a caller must know.
- **"Boundary"**: overloaded with DDD's bounded context. Say **seam** or **interface**.

## Going deeper

- **Deepening a cluster given its dependencies** — see [DEEPENING.md](DEEPENING.md): dependency categories, seam discipline, and replace-don't-layer testing.
- **Exploring alternative interfaces** — see [DESIGN-IT-TWICE.md](DESIGN-IT-TWICE.md): use the available sub-agent mechanism to design several distinct interfaces, then compare depth, locality, seam placement, and project-contract compliance.
