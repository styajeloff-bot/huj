---
name: diagnosing-bugs
description: Evidence-first diagnosis loop for Carcraft bugs, flaky failures, incidents, and performance regressions. Use when the user asks to diagnose, debug, investigate, find a root cause, or reports behavior that is broken, failing, intermittent, or slow. Keep diagnosis-only requests read-only apart from disposable instrumentation; implement a fix only when the user also asks for a change.
---

# Diagnosing Bugs

A discipline for hard bugs. Skip a phase only when the available evidence makes the
reason explicit.

## Establish authority and scope

Before investigating:

1. Read the repository-root `AGENTS.md`.
2. Read every nearer `AGENTS.md` that governs the files or services in the
   suspected path, including the applicable backend layer instructions or
   `frontend/AGENTS.md`.
3. Read `docs/README.md`, use `docs/glossary.md` for domain language, and inspect
   relevant records in `docs/decisions/`.
4. Read the approved task plan when one exists. Treat it as the source for the
   agreed scope and seams.

Subject to higher-level platform policy, current explicit user instructions
override repository defaults for the task; applicable root and nested
`AGENTS.md` files then override this skill. Record an explicit exception rather
than silently broadening it. Do not use this skill to create branches, plans,
commits, merge requests, or merges outside the resulting authorized workflow.

Classify the request before changing anything:

- **Diagnosis only** — investigate and report the symptom, evidence, root cause,
  confidence, and recommended next step. Do not implement a fix, change
  production code, or leave tests/instrumentation behind. Prefer commands and
  disposable artifacts outside tracked files. Stop after the cause has been
  verified and cleanup is complete.
- **Diagnosis and fix** — run the same evidence-first process, then proceed to
  Phase 5 only after the cause is verified and the repository workflow permits
  implementation.

Do not silently broaden a diagnosis-only request into a fix.

## Phase 1 — Build a feedback loop

**This is the skill.** Everything else is mechanical. If you have a **tight** pass/fail signal for the bug — one that goes red on _this_ bug — you will find the cause; bisection, hypothesis-testing, and instrumentation all just consume it. If you don't have one, no amount of staring at code will save you.

Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**

### Ways to construct one — try them in roughly this order

1. **Focused existing test.** For FastAPI, prefer the narrowest
   `cd backend && uv run pytest -q tests/<file>.py -k <case>` invocation that
   reaches the symptom. For frontend architecture contracts, prefer
   `cd frontend && bunx vitest run tests/architecture/<file>.test.ts`.
2. **Failing regression test** at the approved public seam when implementation
   is authorized.
3. **HTTP replay** through Nginx/FastAPI using the canonical `/api/v1/...` path,
   captured request shape, and an assertion on status and response.
4. **Browser loop** for a Nuxt/Vue user flow, asserting the visible result and
   inspecting console and network traffic.
5. **Worker/event replay** for Kafka, ClickHouse, scheduled jobs, or webhook
   paths, preserving their actual ownership and authentication rules.
6. **CLI invocation** with a fixture input, diffing output against a known-good
   result.
7. **Throwaway harness.** Run the smallest service or public function with
   controlled dependencies.
8. **Property or stress loop.** Raise the reproduction rate of intermittent
   failures with seeded inputs, concurrency, or controlled timing.
9. **Bisection or differential loop.** Compare known states, versions, or
   configurations with one automated verdict.
10. **HITL script.** As a last resort, adapt
    [`scripts/hitl-loop.template.sh`](scripts/hitl-loop.template.sh) so the human
    steps and captured evidence remain structured.

Build the right feedback loop, and the bug is 90% fixed.

### Tighten the loop

Treat the loop as a product. Once you have _a_ loop, **tighten** it:

- Can I make it faster? (Cache setup, skip unrelated init, narrow the test scope.)
- Can I make the signal sharper? (Assert on the specific symptom, not "didn't crash".)
- Can I make it more deterministic? (Pin time, seed RNG, isolate filesystem, freeze network.)

A 30-second flaky loop is barely better than no loop; a 2-second deterministic one is tight — a debugging superpower.

### Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the trigger 100×, parallelise, add stress, narrow timing windows, inject sleeps. A 50%-flake bug is debuggable; 1% is not — keep raising the rate until it's debuggable.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for: (a) access to
the environment that reproduces it, (b) a captured artifact such as a sanitized
HAR, log dump, trace, or timestamped recording, or (c) permission to add
temporary instrumentation. Never expose tokens, cookies, personal data, or
secrets in captured evidence. Do **not** proceed to hypothesise without a loop.

### Completion criterion — a tight loop that goes red

Phase 1 is done when the loop is **tight** and **red-capable**: name **one
command**—a test invocation, script, or HTTP replay—that you have **already run
at least once**. Preserve the relevant, sanitized output. The command must be:

- [ ] **Red-capable** — it drives the actual bug code path and asserts the **user's exact symptom**, so it can go red on this bug and green once fixed. Not "runs without erroring" — it must be able to _catch this specific bug_.
- [ ] **Deterministic** — same verdict every run (flaky bugs: a pinned, high reproduction rate, per above).
- [ ] **Fast** — seconds, not minutes.
- [ ] **Agent-runnable** — you can run it unattended; a human in the loop only via `scripts/hitl-loop.template.sh`.

Read only enough code and documentation to locate and construct the loop. If you
catch yourself building a causal theory before this command exists, stop.
Jumping straight to a hypothesis is the failure this skill prevents. No
red-capable command, no Phase 2.

## Phase 2 — Reproduce + minimise

Run the loop. Watch it go red — the bug appears.

Confirm:

- [ ] The loop produces the failure mode the **user** described — not a different failure that happens to be nearby. Wrong bug = wrong fix.
- [ ] The failure is reproducible across multiple runs (or, for non-deterministic bugs, reproducible at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify the fix actually addresses it.

### Minimise

Once it's red, shrink the repro to the **smallest scenario that still goes red**. Cut inputs, callers, config, data, and steps **one at a time**, re-running the loop after each cut — keep only what's load-bearing for the failure.

Why bother: a minimal repro shrinks the hypothesis space in Phase 3 (fewer moving parts left to suspect) and becomes the clean regression test in Phase 5.

Done when **every remaining element is load-bearing** — removing any one of them makes the loop go green.

Do not proceed until you have reproduced **and** minimised.

## Phase 3 — Hypothesise

Generate **3–5 ranked hypotheses** before testing any of them. Single-hypothesis generation anchors on the first plausible idea.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe — discard or sharpen it.

Show the ranked list to the user before testing. They often have domain
knowledge that changes the ranking or evidence that rules an item out. Do not
block on this checkpoint; proceed with the stated ranking if no response is
available.

## Phase 4 — Instrument

Each probe must map to a specific prediction from Phase 3. **Change one variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the env supports it. One breakpoint beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

Tag every temporary debug log with a unique prefix, for example
`[DEBUG-a4f2]`. Remove it before finishing. Use the project logger
`"carcraft-backend"` for backend instrumentation and obtain configuration via
`infrastructure.settings.settings`; never read secrets directly from
`os.environ`.

**Perf branch.** For performance regressions, logs are usually wrong. Instead: establish a baseline measurement (timing harness, `performance.now()`, profiler, query plan), then bisect. Measure first, fix second.

At the end of this phase, state which hypothesis survived, the evidence that
falsified the alternatives, and the confidence level. For a diagnosis-only
request, clean up temporary artifacts and report here; do not continue to a fix.

## Phase 5 — Fix + regression test (only when authorized)

Enter this phase only when the user requested a fix and the applicable
`AGENTS.md` workflow and approved plan allow implementation.

Write the regression test **before the fix**, but only at a **correct, approved
seam**. Reuse seams already approved in the plan; do not ask the user to approve
them again unless evidence requires a material change.

A correct seam exercises the real bug pattern as it occurs at the call site. If
the only available seam is too shallow—for example, a unit test when the bug
requires the HTTP/auth/transaction chain—a test there gives false confidence.

**If no correct seam exists, that itself is the finding.** Note it. The codebase architecture is preventing the bug from being locked down. Flag this for the next phase.

If a correct seam exists:

1. Turn the minimised repro into a failing test at that seam.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 feedback loop against the original (un-minimised) scenario.
6. Run the focused checks and then the broader checks required by the
   applicable root and nested `AGENTS.md` files.

## Phase 6 — Cleanup + post-mortem

Required after an authorized fix:

- [ ] Original repro no longer reproduces (re-run the Phase 1 loop)
- [ ] Regression test passes (or absence of seam is documented)
- [ ] All `[DEBUG-...]` instrumentation removed (`grep` the prefix)
- [ ] Throwaway prototypes deleted (or moved to a clearly-marked debug location)
- [ ] The verified root cause and supporting evidence are captured in the task
      documentation and GitLab MR description required by the repository workflow
- [ ] All required backend/frontend, Docker, and log checks from the applicable
      `AGENTS.md` files pass

For diagnosis-only work, require instead:

- [ ] The exact symptom and reproducer are documented
- [ ] The root cause is supported by a successful falsifiable probe
- [ ] Confidence and unresolved uncertainty are explicit
- [ ] No fix or persistent repository change was made
- [ ] All temporary instrumentation and artifacts are removed

Then ask what would have prevented the bug. If the answer is an architectural
change—no useful test seam, tangled callers, or hidden coupling—record a
specific recommendation for a separate, approved change. Do not expand the
current task implicitly.
