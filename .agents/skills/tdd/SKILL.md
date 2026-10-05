---
name: tdd
description: Test-driven development for Carcraft's Python/FastAPI backend and Vue/Nuxt frontend. Use when the user asks to implement or fix behavior test-first, mentions red-green or TDD, or requests unit, integration, architecture, or regression tests. Reuse test seams already approved in the task plan instead of asking for approval again.
---

# Test-Driven Development

Use a red → green loop that produces behavior tests worth keeping.

## Establish project context

Before writing a test:

1. Read the repository-root `AGENTS.md` and every nearer `AGENTS.md` governing
   the code under test.
2. Read the approved task plan when one exists.
3. Use `docs/glossary.md` for domain vocabulary, `docs/README.md` to locate
   architecture and testing documentation, and relevant records in
   `docs/decisions/` for established constraints.

Subject to higher-level platform policy, current explicit user instructions
override repository defaults for the task; applicable root and nested
`AGENTS.md` files then override this skill. Record an explicit exception instead
of silently generalizing it. This skill does not replace the resulting branch,
planning, verification, documentation, or GitLab MR workflow.

## What a good test is

Verify behavior through a public interface, not implementation details. Make
each test read like a specification in the vocabulary used by
`docs/glossary.md`. Keep expected results independent from the implementation so
the test can disagree with broken code and survive internal refactoring.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Seams — where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

Test only at agreed seams:

- If the approved task plan already names the interfaces, test levels, files, or
  seams, use them without asking again.
- If the plan leaves a material choice open, state the proposed seam and ask
  only for the missing decision.
- If investigation proves an approved seam cannot exercise the behavior, show
  the evidence and obtain approval before changing it.

Choose the narrowest seam that proves the behavior:

- **Backend domain rule:** a public entity/value/service method with no I/O.
- **Backend use case:** an application command/query handler, keeping domain
  rules in the domain layer and repository/provider effects at their boundary.
- **HTTP contract:** the FastAPI endpoint through `httpx.AsyncClient` when the
  behavior includes auth, validation, status codes, cookies, serialization, or
  transaction ownership.
- **Persistence contract:** a repository against the test database when SQL,
  constraints, ORM mapping, or a migration is the behavior.
- **Frontend contract:** an existing Vitest architecture test for source and
  module invariants; a component/user-flow seam when suitable test support
  exists. Always perform the manual browser verification required by
  `frontend/AGENTS.md`.

Respect Carcraft boundaries: UUID entity IDs remain opaque, domain code performs
no I/O, repositories return dictionaries rather than ORM objects, routers own
commits, and ClickHouse writes belong to `event-worker`.

## Anti-patterns

- **Implementation-coupled** — mocks internal collaborators, tests private methods, or verifies through a side channel (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological** — the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code. Expected values must come from an independent source of truth — a known-good literal, a worked example, the spec.
- **Horizontal slicing** — writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior: you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you commit to test structure before understanding the implementation. Work in **vertical slices** instead — one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.
- **Wrong-layer assertions** — testing HTTP behavior through a domain method, or
  domain behavior only through a broad browser flow. Put each assertion at the
  layer that owns the contract.

## Rules of the loop

1. **Red.** Write one test at the approved seam. Run the narrowest command and
   verify it fails for the intended missing or broken behavior, not because of
   setup, imports, or an unrelated error.
2. **Green.** Add only enough implementation to satisfy that test while
   respecting the applicable layer rules. Run the same command and verify it
   passes.
3. **Repeat vertically.** Let each completed slice inform the next test. Do not
   write the full test suite ahead of the implementation.
4. **Review.** Remove duplication and improve names only after green. Keep
   broader refactoring out of the implementation cycle unless it is separately
   approved.
5. **Verify.** Run the focused suite, then every test, lint, type, Docker,
   browser, and log check required by the applicable `AGENTS.md` files.

For backend work, start focused with:

```bash
cd backend
uv run pytest -q tests/<file>.py -k <case>
```

Before completion, run the full backend checks specified by the root
`AGENTS.md`. For frontend architecture contracts, start focused with:

```bash
cd frontend
bunx vitest run tests/architecture/<file>.test.ts
```

Then run `bun run test:arch`, verify the changed flow in the browser, and avoid
introducing TypeScript errors as required by `frontend/AGENTS.md`.
