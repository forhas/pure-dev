# Dependency direction without a directional relation

**Date**: 2026-08-02
**Status**: Part 1 implemented, **on a rationale since proven wrong and corrected** — see "Falsification" below. Part 2 resolved: no code change needed.

> **The mechanism this document argues for is false.** Notion self-referential relations are
> directional. The prediction recorded below was tested and failed on its decisive point. The
> design outcome survives for a different, narrower reason. Read "Falsification" before treating
> anything above it as current.

## Origin

A client's `notion-dev-issues.md` recorded an `unexpected:dependsOnProperty` entry against notion-dev 0.9.0, at `/notion-dev:create-task` → Phase 3.2 Pass 2:

> **Expected**: a one-way self-referential relation, so writing a dependency from one page to another records only that direction.
> **Observed**: a self-referential relation on this backend is inherently symmetric — every write also created the reverse edge on the target page. Confirmed not to be a configuration detail: altering the column to a plain one-way relation left the behavior unchanged, and so did dropping and recreating it from scratch.
> **Effect**: dependency direction cannot be represented in this column at all; the relation edges were cleared and the ordering was written into the dependent tickets' bodies as an explicit blocked-by section instead. The adapter's `setDependencies` contract assumes a directional relation and has no fallback for this case.

The client's own workaround — clearing the edges and writing the order into the body — is the design this spec adopts.

## Mechanism

A Notion self-referential relation is symmetric exactly when both ends of an edge land in the *same* column. Notion's own directional self-relation, native Sub-items, avoids this by using **two** columns (`Parent item` + `Sub-item`). A single column cannot hold two directions.

This is consistent with both of the client's negative experiments: retyping to one-way and recreating from scratch each leave a single column, so neither could change the outcome.

**This mechanism is inferred, not verified.** Part 2 is gated on the test protocol below. Part 1 does not depend on it: the client's column is symmetric whatever the cause, and the adapter has no defined behavior for a symmetric column either way.

## Part 1 — Dependency direction (accepted)

### Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Where direction lives | The ticket body | Same pattern `refreshEpicTasks` already uses for `## Tasks`; no schema dependency, so it cannot degrade |
| Relation write | Removed entirely | The column cannot represent direction; on a symmetric column, writing it actively pollutes both pages with false reverse edges |
| Config surface | `dependsOnProperty` removed in full | With nothing reading it, the key, its init resolution block, and its signature row are all dead |

### `setDependencies(id, references)`

Becomes a body renderer and **the single owner of the `## Blocked by` section's format** — the same ownership rule `refreshEpicTasks` holds over `## Tasks`, for the same reason: `/notion-dev:create-task` must not be able to drift from it.

1. The `dependsOnProperty` absence guard is **deleted**. The operation no longer reads the live schema, so it has no degrade path and records no issue-log signature.
2. Reference resolution is **unchanged** — both the numeric/prefixed branch and the title branch, including the prefix-stripping rule and both raise messages. It now resolves to ticket records rather than page ids, because the render needs `key`, `title`, and `url`.
3. `upsertSection(id, "Blocked by", <rendered>)`. Replace semantics make re-running a mission idempotent rather than stacking duplicate sections.

### Render format

```
- [STO-67] Add Litecoin config schema · https://notion.so/…
- [STO-68] Implement LtcConnector · https://notion.so/…
```

Plain bullets — **no checkbox and no status**, deliberately diverging from `## Tasks`.

`refreshEpicTasks` can afford live statuses because it is re-run on every resolution (`/notion-dev:ticket` Phase 8, `/notion-dev:finalize` Phase 3) and points readers at a live column for truth. `## Blocked by` is written **once**, at Pass 2 of mission creation, and nothing refreshes it. A checkbox left unticked after its blocker ships asserts something false; no checkbox asserts nothing. URLs restore the navigability the relation column used to provide.

### Styling

`Styling conventions` → `Palette per section` gains a row: `Blocked by` · written by `/notion-dev:create-task` · heading `yellow` · no intro callout · no icon.

Yellow keeps it distinct from the orange spec sections and from blue `Tasks`. No callout follows the existing rule that structural cross-reference sections are self-explanatory.

### Removals

| Location | Removed |
|---|---|
| `skills/ticket-system/SKILL.md` | `dependsOnProperty` config bullet; relation language in the operations table |
| `schema/notion-dev.config.schema.json` | `dependsOnProperty` key |
| `commands/init.md` | the `dependsOnProperty` resolution block; the key in the omit-when-default list |
| `skills/issue-log/references/signatures.md` | `missing-property:dependsOnProperty` row |
| `skills/issue-log/SKILL.md` | `dependsOnProperty` from the `Context` permitted-keys whitelist |

Removing the signature row and its only call site **together** keeps the closure check (`signatures.md`, "Adding a signature" step 4) balanced — a registry row with no citing call site would fail it.

Deleting the init block also deletes its guardrail against binding a parent-like name to `dependsOnProperty`. That is safe: the guardrail existed to protect a slot that no longer exists, and `parentTaskProperty` resolves first and is untouched.

### Migration

Existing configs may still carry a `dependsOnProperty` key. It is ignored, not an error. Live `Depends on` columns are left exactly as they are — the plugin stops writing them but never clears them, since their contents may predate the plugin.

## Part 2 — Epic containment (pending verification)

### The predicted failure

`findEpics` step 2 selects pages where `epicMarkerProperty` is `true` **and their own `parentTaskProperty` is empty**. If a single-column self-relation is symmetric, an epic with children has its own `parentTaskProperty` populated with those children, so it fails that predicate.

**An epic would vanish from discovery the moment it gains its first child** — silently, not as an error or a degrade. `getEpicContext` step 2, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard share the predicate and would fail identically. `fetchTicket` step 4a would return a list of children where callers expect a single parent id.

`listEpicChildren` would still work, since its query — pages whose `parentTaskProperty` contains the epic — is satisfied either way. The breakage is asymmetric across operations, which is how it would stay hidden.

### Why the client did not hit this

`init.md` resolves `parentTaskProperty` **first**, preferring a parent-like name — in practice Notion's native Sub-items, a two-column construct and therefore directional. `dependsOnProperty` then took "any remaining self-referential relation," in practice a plain single-column relation.

If that holds, exposure depends on **how the column was created**: native Sub-items is safe; an API- or UI-created single-column self-relation is not. `init.md`'s "Create `Parent task` (Relation)" option takes the unsafe path while reassuring the user that "grouping and every plugin feature work identically" — a claim this spec puts in doubt.

### Test protocol

Scratch database, two rows `A` and `B`.

1. **One-way self-relation.** Add Relation `RelOneWay` → same DB, "Show on <DB>" **off**. Set `A.RelOneWay = B`. Open `B`: does `RelOneWay` contain `A`? *This is the decisive question.*
2. **Two-way self-relation.** Add `RelTwoWay` → same DB, "Show on <DB>" **on**. Note whether Notion creates a second column or reuses one. Set `A.RelTwoWay = B` and check where the reverse edge lands.
3. **Native Sub-items.** Enable Sub-items. Confirm it is exposed as two columns. Set `A.Sub-item = B`; check `B.Parent item = A` and that `B.Sub-item` is empty.
4. **API-created relation.** If possible, create the relation via the API rather than the UI — `/notion-dev:init`'s Create option on a scratch DB does this. An API `single_property` self-relation may behave differently from a UI toggle, and that is the branch `init.md` actually takes.

**Prediction, recorded before the test so it is falsifiable:** #1 symmetric, #2 two columns with a directional split, #3 directional.

If #1 comes back **directional**, the mechanism above is wrong, the client's database is misconfigured in some way their two experiments did not rule out, and Part 2 shrinks to a documentation fix. Part 1 stands unchanged in either case.

---

# Falsification

The test was run against the reporting client's own workspace on 2026-08-02. **Prediction #1 —
the decisive one, the one Part 2 was gated on — was wrong.**

| Test | Predicted | Observed |
|---|---|---|
| #1 one-way (`single_property`, API-created) | symmetric | **directional** — one column, no companion, `B.RelOneWay` null |
| #2 two-way (`dual_property`) | two columns, directional split | two columns, directional split |
| #3 native Sub-items | directional | directional (confirmed on live production data) |
| #4 API-created | — | same as #1; a self-relation genuinely cannot be declared at CREATE time |

Notion self-referential relations are **directional in both forms**. `single_property` writes one
edge and creates no reverse edge. `dual_property` splits the two directions across two columns. In
no case did a written edge appear in the same column on the target row.

## Part 2: resolved, no code change

`findEpics` is safe as written, confirmed on live data rather than by argument. Epic STO-333 has 11
real children; its own `Parent-task` is empty while `Sub-tasks` holds all 11. It remains visible to
the "parent is empty" predicate today.

This also validated `init.md`'s "Create `Parent task` (Relation)" prompt, which this spec had put in
doubt: an API-created relation *is* directional, exactly as that prompt promises.

Better still, the plugin wrote only each child's `Parent-task`; Notion filled the epic's `Sub-tasks`
companion itself. That is test #3 observed in production, not inferred.

## The real reason the relation stays unused

Two follow-up hypotheses were raised and **both were refuted** by a read-only diagnostic:

- *Symmetry* — refuted by tests #1 and #2 above.
- *Mis-binding to `Sub-tasks`* — refuted by config history. `dependsOnProperty` never appeared in
  any revision, so the default `"Depends on"` applied, and it matched a real standalone non-native
  column exactly. `Sub-tasks` was never a reachable candidate.

What survives is narrower and is now the canonical rationale in
`skills/ticket-system/SKILL.md` → `setDependencies`: **the adapter cannot tell a one-way relation
from a two-way one.** The MCP schema surface does not expose relation subtype. Bound to a
`dual_property` column, every write surfaces a reverse edge in a companion column the adapter never
names, reads, or controls — indistinguishable, to a caller reading the target page's property map,
from the relation being symmetric. That is a limit of the available surface, not a property of
Notion relations, and it is revisitable if the API ever exposes subtype.

The `## Blocked by` design outcome is unchanged. Only its justification is.

## Original root cause: inconclusive

The reported reverse edges were cleared by hand before any investigation, and `Depends on` is empty
across all 338 rows. One lead, recorded as a lead: the live `Depends on` column carries a
`propertyUrl`, which the scratch `single_property` column did not and both `dual_property` halves
did. That is consistent with `Depends on` being a two-way relation whose companion-column edges were
read as symmetry — but the MCP surface does not expose subtype, and a deleted companion would look
identical. Not testable read-only. Left unresolved rather than resolved to the tidier story.

## Separately found: the parent-name matching bug

`Parent-task` (hyphen) is Notion's native Sub-items name in this workspace. Init's parent-like scan
matched `"Parent task"` (space) by literal equality, so it matched nothing — and a failed match
binds nothing rather than mis-binding. The slot stayed unbound and epic containment was unavailable
for **eleven days**, with no wrong value anywhere to notice.

Fixed in the same change: parent-like names now match case-insensitively with `-`, `_`, and
whitespace treated as equivalent, and the sub-item half is explicitly excluded so a loose match can
never invert containment.

## What this episode should change

The mechanism was plausible, internally consistent, and wrong. It was argued from how Notion's
native Sub-items is *shaped* rather than from any observation of how relations *behave*, then
written into nine sites as settled fact before a single test had been run. Writing the prediction
down in advance is what made it cheap to correct — but predicting earlier would have been cheaper
than correcting later.
