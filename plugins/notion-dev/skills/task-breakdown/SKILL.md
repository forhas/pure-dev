---
name: task-breakdown
description: Use after /notion-dev:ticket-interviewer produces a well-elaborated draft, to decide whether it should become a single ticket or a mission (multi-task breakdown with Epic / Phase / Step / Depends-on). Backend-agnostic — performs structural analysis only; does not touch any ticket system.
---

# task-breakdown

Decides, after the interviewer is done, whether a request is best represented as **one** ticket or **many** related tickets sharing a mission.

The skill is pure analysis. It does no I/O, reads no configuration, calls no adapters. Its output is a plan the caller (`/notion-dev:create-task`) uses to drive creation.

## Input contract

```
{
  title:      string,
  body:       string (markdown — Requirements / Acceptance Criteria / Context / Open Questions / Source),
  sourceRef:  string,
  type?:      "Feature" | "Bug" | "Improvement" | "Research"
}
```

## Output contract — discriminated union

```
// Single-ticket result
{
  kind:  "single",
  title: string,
  body:  string,
  type?: string
}

// Mission result
{
  kind:  "mission",
  epic:  string,                       // proposed Epic name; caller reconciles against live options
  tasks: [
    {
      title:       string,
      body:        string,              // same shape as input body (Requirements / Acceptance Criteria / …)
      type?:       string,
      phase?:      string,              // e.g. "Phase 1: Research & Design" — omit when unstructured
      step?:       number,              // sequence within the Phase — omit when order is irrelevant
      dependsOn?:  string[]             // sibling task titles only. Never self-references. Never cross-mission.
    },
    …
  ]
}
```

## Decision rules

Default stance: **`single`**. Evidence is required to split. Splitting decisions lifted from BC-Gateway's Minimal-Sufficient-Structure checkpoint — the same heuristics that have been battle-tested in practice.

### When to return `single`

- The source describes one coherent deliverable. Multiple bullets, sections, or discussion points are **not** a sufficient reason to split — if they form one end-to-end change, keep them in one task.
- Fewer than 3 independently-deliverable units.
- The same feature discussed from different angles (API + UI + config) — if they ship together, one task.
- No blocking dependencies between conceivable sub-parts.

### When to return `mission`

Any one of these justifies a split:

- Work naturally separates into **≥3 independently deliverable units** that could be reviewed/merged separately.
- **≥2 units with explicit blocking dependencies** (unit B literally cannot start before unit A's output exists).
- A single task would touch **>8 files** or become impossible to review as one PR.
- Different units affect **substantially different domains or components** and would be worked on by different contributors.

### Structural tagging — thresholds within mission

When returning `mission`, apply these rules to decide which optional fields to populate on each task:

- **Epic** — always present on a mission result (a mission without a shared initiative wouldn't be a mission). Propose a name derived from the source title or theme. The caller will reconcile against existing DB options.
- **Phase** — only when the mission's tasks naturally group into **sequential implementation stages** (e.g. Research → Implementation → Validation). If the tasks are parallelizable or don't share a stage-gate pattern, omit `phase` entirely from every task.
- **Step** — only when **≥2 sibling tasks exist within the same Phase** AND execution order within the phase matters. Use integer steps (1, 2, 3…); leave float precision for future inserts.
- **DependsOn** — only for **true blocking dependencies**. Do not use for soft preferences, logical sequencing already expressed by Phase/Step, or "it'd be nicer to do A first."

If any structural field doesn't apply to a task, **omit it**. Never emit `phase: null` or `dependsOn: []`.

### NOT sufficient reasons to split (explicit anti-patterns)

- The source mentions multiple bullets, sections, or ideas.
- The DB supports epics/phases/steps/dependencies (availability is not a mandate).
- Several files are involved in one feature.
- Tests/config/docs could be listed separately but belong with implementation.
- You want to show thoroughness — fewer, richer tasks are always better than many shallow ones.

## Task content for `mission` results

Each task's `body` must be self-contained — an implementer reading only that task's body should understand the work without the source. Derive from the input body by:

1. Carving the input `## Requirements` into per-task requirements (each task gets its slice).
2. Carving `## Acceptance Criteria` similarly — each task's AC checklist only covers that task's slice.
3. Copying the full `## Context` into every task (context applies to all).
4. Distributing `## Open Questions` to the task(s) they affect; questions that span multiple tasks go on the earliest-in-dependency one.
5. Preserving `## Source` verbatim on every task (same provenance).

Task titles should be **action-oriented** and **scoped** — `"Add /balance/:chain endpoint"` not `"Backend work"`.

## Worked examples

### Example A — single

Input:
> title: "Write a unit test for the auth flow"
> body: `## Requirements\n- Cover login, refresh, and logout happy paths\n- Mock the JWT signer\n## Acceptance Criteria\n- [ ] Three tests pass under `npm run test:unit`\n…`

Output:
```
{ kind: "single", title: "Write a unit test for the auth flow", body: <as-is>, type: "Improvement" }
```

Reason: one coherent deliverable (a unit-test file), no blockers between happy paths, <8 files.

### Example B — mission with Phase/Step/Deps

Input describes "Add Litecoin support" — the source implies: (1) add a config schema for LTC, (2) add an `LtcConnector` class, (3) wire into existing provider failover, (4) write e2e tests.

Output:
```
{
  kind: "mission",
  epic: "Litecoin Multi-Chain Support",
  tasks: [
    { title: "[CFG][Feature] Add Litecoin config schema", body: …, type: "Feature",
      phase: "Phase 1: Foundation", step: 1 },
    { title: "[CORE][Feature] Implement LtcConnector", body: …, type: "Feature",
      phase: "Phase 2: Implementation", step: 1,
      dependsOn: ["[CFG][Feature] Add Litecoin config schema"] },
    { title: "[CORE][Feature] Wire Litecoin into provider failover", body: …, type: "Feature",
      phase: "Phase 2: Implementation", step: 2,
      dependsOn: ["[CORE][Feature] Implement LtcConnector"] },
    { title: "[TEST][Feature] E2E tests for Litecoin withdrawal and balance", body: …, type: "Feature",
      phase: "Phase 3: Validation", step: 1,
      dependsOn: ["[CORE][Feature] Wire Litecoin into provider failover"] }
  ]
}
```

Reasons: 4 independently reviewable deliverables, clear sequential stages (Foundation → Implementation → Validation), explicit blockers between tasks.

### Example C — mission without Phase/Step

Three unrelated-but-grouped bug fixes under one initiative:

Output:
```
{
  kind: "mission",
  epic: "Q2 Stability Pass",
  tasks: [
    { title: "[API][Bug] Fix 500 on /balance when chain missing", body: …, type: "Bug" },
    { title: "[CORE][Bug] Correct LTC fee rounding", body: …, type: "Bug" },
    { title: "[API][Bug] Handle empty payload in POST /withdraw", body: …, type: "Bug" }
  ]
}
```

No `phase`, no `step`, no `dependsOn` — all three are independent bug fixes. Epic gives them a shared tag; nothing more.
