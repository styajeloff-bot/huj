# Design It Twice

Use this process when the user wants alternatives for a chosen deepening candidate or when a high-impact seam has several plausible shapes. Based on “Design It Twice” (Ousterhout): compare meaningfully different interfaces before committing.

Use the vocabulary in [SKILL.md](SKILL.md): **module**, **interface**, **seam**, **adapter**, **leverage**, and **locality**. Use CarCraft domain terms from `docs/glossary.md`.

## Process

### 1. Frame the problem space

Inspect the candidate, its callers, tests, and governing project material:

- root and relevant nested `AGENTS.md`;
- active `backend/pyproject.toml` import contracts for backend work;
- `docs/glossary.md`;
- relevant `docs/architecture/` maps and accepted `docs/decisions/`;
- relevant frontend architecture tests for frontend work.

Then state:

- the CarCraft capability and business entities involved;
- the constraints every interface must satisfy;
- the dependencies and their categories from [DEEPENING.md](DEEPENING.md);
- a small illustrative Python/FastAPI or Vue/Nuxt sketch that grounds the problem without presenting a preferred design.

Share this framing with the user, then continue unless a material product decision is missing.

### 2. Spawn sub-agents

Use the available Codex sub-agent or delegation mechanism. Run up to three read-only design tasks in parallel when capacity permits; do not assume a particular vendor-specific tool name. If fewer slots are available, obtain the same independent alternatives sequentially.

Give each sub-agent the same evidence paths and a separate technical brief containing the coupling details, dependency categories, intended behaviour behind the seam, and explicit instruction not to edit files. Require it to read the governing `AGENTS.md`, `backend/pyproject.toml` when relevant, `docs/glossary.md`, and relevant architecture decisions.

Assign different constraints:

- **Minimal interface:** aim for one to three entry points and maximize leverage.
- **Common caller:** make the dominant CarCraft use case trivial without hiding required invariants.
- **Extension pressure:** support the evidenced near-term variants while resisting speculative flexibility.
- **Ports and adapters, if applicable:** isolate an owned remote or true external dependency without violating layer contracts.

Each sub-agent outputs:

1. The complete interface: types, methods, parameters, invariants, ordering, effects, and error modes.
2. A concise caller example in the affected stack.
3. What the implementation hides behind the seam.
4. Dependency and adapter strategy.
5. The resulting import graph or feature dependency direction.
6. Compliance with the applicable `AGENTS.md`, `import-linter` contracts, architecture tests, and ADRs.
7. Trade-offs in depth, locality, and migration risk.

### 3. Present and compare

Present each design separately, then compare:

- **depth** and caller leverage;
- **locality** of policy and change;
- seam placement and dependency direction;
- fit with CarCraft vocabulary and accepted decisions;
- test surface and migration cost;
- compliance with automated architecture checks.

Recommend one design and explain why. Propose a hybrid only when it is simpler than its sources. Reject alternatives that violate project contracts instead of presenting them as viable options.
