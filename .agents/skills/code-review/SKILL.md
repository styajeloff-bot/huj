---
name: code-review
description: "Review Carcraft Lead Generator changes along two independent axes: repository Standards and the originating Spec. Use for branch, GitLab merge request, committed-diff, or work-in-progress reviews, including requests to review changes since a commit, branch, or tag. Default the fixed point to origin/test unless the user explicitly supplies another ref. Keep the review read-only and report Standards and Spec findings separately."
---

# Review code on two independent axes

Compare the requested change with a fixed point and produce two reports:

- **Standards** — whether the diff follows Carcraft's documented engineering rules.
- **Spec** — whether the diff implements the originating requirement completely and only.

Keep the axes independent so a strong result on one cannot hide a failure on the other. Perform
the entire workflow read-only: do not edit files, run fix-mode commands, create or update tasks,
switch branches, commit, push, create or change merge requests, or merge anything.

## 1. Pin the review scope

Use the fixed point explicitly supplied by the user. Otherwise use `origin/test`; do not ask merely
because the user omitted a fixed point.

Resolve the ref with `git rev-parse --verify <fixed-point>` and determine the merge base with
`git merge-base <fixed-point> HEAD`. Do not fetch or mutate refs as part of the review. If the
available ref is missing or ambiguous, report the blocker and ask for a resolvable fixed point.

Match the diff to the requested scope:

- For a branch, commit, or GitLab MR review, inspect `git diff --find-renames
  <fixed-point>...HEAD`.
- For work in progress, diff the working tree against the resolved merge base so committed, staged,
  and unstaged tracked changes are included. List untracked files with
  `git ls-files --others --exclude-standard` and inspect relevant untracked contents separately.

Capture once and give both reviewers the exact diff command, merge base, changed-file list, and
`git log <fixed-point>..HEAD --oneline`. Stop early if the resolved review scope is empty.

## 2. Find the authoritative spec

Search in this order and record which source won:

1. **Explicit source.** Use any path or link supplied by the user, including Bitrix, a document, or
   a GitLab MR. Read it through an available read-only connector, browser session, or local file.
2. **Carcraft task material.** Infer the task ID and branch slug from the current branch, then search
   Bitrix links and approved plans or requirement documents under `docs/` that match that ID or
   slug. Prefer an approved plan and its linked original requirement over incidental notes. Typical
   evidence of approval includes explicit wording such as `План согласован`; completed plans may
   use a status such as `Статус: реализован`.
3. **GitLab and commits.** Read the current branch's GitLab MR description and linked material, when
   available, then inspect commit messages and trailers for requirements or links.

Use `docs/README.md` to navigate project documentation instead of assuming a parallel documentation
layout. Treat `docs/glossary.md` as the terminology authority when the requirement uses ambiguous
Carcraft domain language.

Do not install or depend on a preconfigured issue-tracker workflow or helper document. Do not
create or modify a Bitrix task or GitLab MR while resolving the spec.

If sources disagree, give the Spec reviewer all authoritative candidates and label the conflict.
If no authoritative spec can be read after the search, still run the Spec reviewer and require it
to report `No authoritative spec available`; it must not invent requirements from the diff.

## 3. Find applicable standards

Always include the repository-root `AGENTS.md`. For every changed file, walk from the repository
root to its directory and include each nested `AGENTS.md` on that path; the closest applicable file
adds to or overrides broader rules for that path.

Use `docs/README.md` to select only relevant project documentation, for example architecture,
cross-cutting contracts, decisions, inventory, or runbooks affected by the changed paths and
behaviour. Include `docs/glossary.md` when domain terms are involved. Do not treat unrelated docs
as standards.

Record current explicit user instructions and owner-approved exceptions in the
authoritative spec. Subject to higher-level platform policy, they override
repository defaults for the reviewed task. Do not report a documented,
explicitly approved exception as a standards violation; instead verify that
the diff stays within the stated exception.

Apply the following smell baseline even when project documentation is silent. Project rules win
over this baseline. Treat every smell as a judgement call, never a hard violation, and omit checks
that repository tooling already enforces:

- **Mysterious Name** — a name does not reveal what it does or holds. Rename it; if no honest name
  emerges, clarify the design.
- **Duplicated Code** — the same logic shape appears in multiple changed locations. Extract and
  reuse the shared shape.
- **Feature Envy** — code reaches into another object's data more than its own. Move the behaviour
  toward the data it uses.
- **Data Clumps** — the same fields or parameters repeatedly travel together. Introduce one
  cohesive type.
- **Primitive Obsession** — a primitive stands in for a domain concept. Give the concept a small
  explicit type.
- **Repeated Switches** — equivalent condition cascades recur for the same discriminator. Centralize
  the dispatch or use polymorphism.
- **Shotgun Surgery** — one logical change requires scattered edits. Gather the changing behaviour
  behind one module boundary.
- **Divergent Change** — one module changes for unrelated reasons. Split responsibilities.
- **Speculative Generality** — abstractions or hooks serve no current requirement. Remove or inline
  them until a real need exists.
- **Message Chains** — callers navigate long object chains. Hide the navigation behind a cohesive
  method.
- **Middle Man** — a layer mostly delegates without adding policy. Call the real collaborator
  directly.
- **Refused Bequest** — a subtype ignores much of its inherited contract. Prefer composition or a
  narrower abstraction.

## 4. Run two reviewers in parallel

Use the available subagent mechanism to start exactly two independent reviewers: one Standards
reviewer and one Spec reviewer. Start both before waiting for either result. Do not use
provider-specific tool names, model names, or subagent types in the workflow. Do not share one
reviewer's findings with the other.

If independent parallel subagents are unavailable, stop and state that the requested two-axis
review cannot be performed independently; do not silently substitute a sequential self-review.

Give both reviewers these constraints:

- Work read-only and inspect only the supplied scope.
- Do not edit, format, test with write-producing commands, checkout, commit, push, or mutate any
  Bitrix/GitLab resource.
- Report only actionable findings caused by the reviewed diff.
- Cite file and line or hunk for code claims; distinguish evidence from inference.
- Return no more than 400 words.

Give the **Standards reviewer**:

- The exact diff command, merge base, changed files, and commit list.
- The applicable root and nested `AGENTS.md` paths.
- The selected relevant documentation paths.
- The current explicit user instructions and owner-approved exceptions recorded
  in the authoritative spec.
- The full smell baseline above.
- This brief: report documented-standard violations with the exact source and rule; report smells
  separately by name as judgement calls. Let explicit user instructions
  override repository defaults for this task, let project rules override the
  smell baseline, and skip anything existing tooling enforces.

Give the **Spec reviewer**:

- The same diff scope and commit context.
- The selected spec source or sources, including any conflicts or access limitation.
- This brief: report missing or partial requirements, incorrect implementations, and unrequested
  scope. Quote or precisely cite the governing requirement for each finding. If no authoritative
  spec is available, report that fact without deriving a spec from the implementation.

## 5. Aggregate without cross-ranking

Present the reviewers' results under separate `## Standards` and `## Spec` headings. Lightly clean
formatting and remove duplicates within an axis, but do not merge, trade off, or rerank findings
between axes.

Within each axis, show actionable findings first and include severity when the evidence supports
it. State explicitly when an axis has no findings or when Spec could not be evaluated.

End with one line giving the finding count and worst issue independently for each axis. Do not
choose a single overall winner or verdict across both axes.
