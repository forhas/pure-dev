## The file

**Path:** `<knowledge.dir>/epic/<KEY>-<n>-<slug>.md`. `knowledge.dir` comes from `.claude/notion-dev.config.json` (default `knowledge`). `<KEY>-<n>` is the epic's ticket key; `<slug>` is the epic title kebab-cased exactly as `/notion-dev:ticket` Phase 2.1 slugs a branch (lowercase, non-alphanumerics → `-`, collapse repeats, trim, 40 characters). The H1 carries the exact epic title. **Lookup is always `<KEY>-<n>-*.md`, never by slug**, so a title change in Notion cannot orphan the file.

**Branch.** The brief lives on the branch pull requests merge into — `git.prTargetBranch`, falling back to `git.baseBranch` — called `<epicBranch>` below. `read` and `record` use that one branch for every read and every commit; a brief read from one branch and written to another is stale on the next run, and `/notion-dev:next-task` would bootstrap a second, divergent copy.

**Template.** Frontmatter (the epic root concept, OKF v0.2) plus six mandatory sections, always in this order, and one optional `## Release obligations` section placed before `## Next`:

```
---
type: Epic
title: "[STO-60] Wallet Indexing"
description: "<the Goal in one line>"
status: stable
epic: STO-60
generated: { by: notion-dev:epic-doc, at: 2026-09-13T00:00:00Z }
sources:
  - { id: epic, resource: "<notion url>", title: "[STO-60] Wallet Indexing" }
---
# [STO-60] Wallet Indexing
Epic: <notion url> · Status: open | closed · Updated: 2026-09-13 after [STO-67]
Seeded from docs/STO-67-release-plan.md (last at a1b2c3d) · 2026-09-13

## Why
<2-4 sentences: the motivation — from the Notion Overview or the seed>

## Goal
<1-3 sentences: what "done" means for the epic>
Done when:
- [STO-70] resolved
- [STO-71] verdict recorded
- external: customer confirms v1.4.2 fixes the report — open

## Where we stand
<3-6 sentences: what has landed, what changed the picture recently>

## Open threads
- **Waiting on customer logs** for v1.4.2 deployed 2026-07-20 — blocks STO-22, STO-23.
  Unblocked by: logs attached to STO-22.
- **Caveat** — the cache TTL chosen in STO-67 assumes ≤10k wallets; revisit in STO-71.

## Decisions & constraints
- <epic-level facts a ticket needs: versions, environments, agreed approaches, rejected
  approaches with why>

## Release obligations
- [STO-67] wire error code 4012 added — sign-off: yes — gate: none — released: no
- commitment: retry fix for the customer — for: v1.5 — ticket: [STO-70] — released: no

## Next
1. **[STO-70] Backfill historic wallets** — unblocked; depends on nothing open. Why now: …
2. [STO-71] Cache metrics — after STO-70 (reads its index).
In progress: [STO-72] Backfill v2 — since 2026-09-15
Blocked: STO-22, STO-23 (see Open threads).
```

**Every dynamic frontmatter value is written as a double-quoted YAML string with `"` and `\` escaped — a JSON string literal**: the title, the description, the Notion URL, and the source title. A title carrying a quote, or a Goal that begins `Target: deploy`, would otherwise break the block and fail every later `check`; `migrate` serializes the same four values the same way.

**The title is quoted.** Left unquoted, `[STO-60] Wallet Indexing` opens a YAML flow sequence
and then trails a scalar, so the document has no parseable frontmatter at all and `check` reports
every required property missing — which makes the next `capture` write nothing. The quoted form
above is the only one to write, and `sources[].title` is quoted for the same reason.

**The brief carries an `index.md` bullet.** It is the bundle's root concept and it is
`status: stable`, so `scripts/knowledge.py check` requires one bullet in `<knowledge.dir>/index.md`
resolving to it — and a failing `check` makes `notion-dev:knowledge` `capture` write nothing on
every later merge. So every operation here that writes the brief — `record`, `record --bootstrap`
and `note --apply` — first ensures that bullet exists: when no bullet in `index.md` resolves to
`<brief path>`, add `- [<epic title>](epic/<KEY>-<n>-<slug>.md) — <the Goal in one line>` under
the `# epic/` section, creating that section at the top of the file when it is absent. Nothing
else in `index.md` is touched, and `<knowledge.dir>/index.md` joins the commit's pathspec so the
bullet lands in the same commit as the brief. When the bullet is already there, this writes
nothing.

The `Seeded from` line exists only on a brief distilled from a pre-existing hand-written plan (see "Bootstrap" below). A bullet under `## Decisions & constraints` or `## Open threads` may link a concept plus one clause instead of stating the fact in prose (`- [Offline deploy](../decision/offline-deploy.md) — binds STO-70.`); `record` and `note` write the link form whenever a concept for the fact exists, and the prose form otherwise.

**`Done when:` decides closure.** The optional list under `## Goal` names each child ticket with
its required state (`resolved`, or `verdict recorded` for a build-or-drop decision — both read
the live resolved set) or a named external condition marked `met`/`open` by a human.
`knowledge.py epic-goal` evaluates it; an unknown ticket or an unparsed item is never met. When
it holds the epic is **goal-complete** and the `## Next` body is, instead of a numbered list,
the goal-met line and a `Re-home:` list of every other open child, one per line — a claimed one included, so
it matches `epic-goal`'s close-time re-home batch:

```
goal met — propose closing the epic; re-home the open children
Re-home:
- [STO-73] Connection audit
- [STO-74] Stale JSDoc
```

Without the list, closure falls back to every child resolved. `bootstrap` and `record` derive
the list from the Overview's stated outcome or the seed's explicit goal; never invent one from
the current child count — an epic with no stated finish line keeps the fallback.

**`## Release obligations` is one ledger** (`references/boundaries.md`): every merged-but-
unreleased obligation as `- [<KEY>-<n>] <obligation> — sign-off: yes|no — gate: <gate|none> —
released: yes|no`, and every deliverable promised to someone as `- commitment: <deliverable> —
for: <whom or release> — ticket: [<KEY>-<n>] — released: yes|no`. Sign-off is requested once per
release from this list. A released item is removed at the next `record`.

**Rules of content.**

- **Every `## Open threads` bullet names what it blocks or which ticket it informs**, and — for a wait on someone else — what would clear it (`Unblocked by:`). A bullet that names neither is not a thread and is not written.
- **No ticket history, no status table.** Notion is the ledger. The brief holds only what Notion cannot say: why, where we stand, what is waiting on whom, and what is next.
- **`## Next` is an ordered recommendation, not a task list.** When proven eligible, item 1 is the single most recommended **unblocked** ticket with its reason. Unread/stale dependencies instead say `dependency check pending`, including item 1 when none is proven ready; never fetch every sibling just to remove that label. Further items state known waits or pending checks. The trailing `Blocked:` line names every unresolved child held by an open thread. When the epic is closed, the section reads `epic complete`.
- **The three lists of `## Next` partition the unresolved children with no overlap**: the numbered
  list (runnable now or after a listed dependency), `In progress:` (claimed — every child whose
  live status is `statusMap.inProgress`, comma-separated in numeric-id order, each
  `[<KEY>-<n>] <title> — since <YYYY-MM-DD>`, the date the line first named the key), and
  `Blocked:` (held by an open thread). A child in none of the three is a defect `refresh`
  repairs, never a warning. An in-progress child that a thread also names is `In progress:` —
  the claim wins. Item 1 is never in progress. A stopped run is one thread bullet,
  `- **[<KEY>-<n>] stopped at <phase>** — <cause>; worktree at <path>. Unblocked by: /notion-dev:ticket <KEY>-<n> (resumes).`,
  and its key is `Blocked:` until a `start` removes the bullet.
- **Budget: `convergence.briefBudget` lines (default 150).** Over it, `record` prunes before it adds: settled decisions and constraints move to knowledge concepts and are linked from the brief, not restated in it. It never prunes a thread that still names an unresolved ticket, a `Done when:` item or an unreleased obligation. `epic-goal` reports `brief.over_budget`.
- **Human edits are first-class.** A person may edit the file (for example, "logs arrived — STO-22 unblocked") and commit it. `record` applies a diff evidenced by its inputs and preserves every line it has no evidence to change.
