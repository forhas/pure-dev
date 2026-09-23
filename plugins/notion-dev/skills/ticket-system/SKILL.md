---
name: ticket-system
description: Use when a notion-dev command needs to read or write a ticket in the configured Notion ticket database. Implements the logical ticket operations (fetchTicket, createTicket, updateStatus, …) over the Notion MCP, driven by .claude/notion-dev.config.json.
---

# ticket-system

Provides the ticket operations for the notion-dev commands over the configured Notion database. Commands invoke this skill by naming an operation; this file defines the operation contract and how each operation is fulfilled with the Notion MCP (`mcp__notion__*` tools).

If `.claude/notion-dev.config.json` is missing or has no `ticketSystem.databaseId`, fail clearly and tell the user to run `/notion-dev:init`. Resolve the config path against the **primary checkout**: use the caller's recorded `$REPO_ROOT` when provided, else the first path listed by `git worktree list` — never `git rev-parse --show-toplevel`, which returns the *worktree* root when run inside one. Callers often invoke this skill from inside a ticket worktree, which may not contain the config file.

## Operation routing

Load `references/config.md` once before the first call. Cache resolved read-only config/schema
by primary-config hash and provider schema identity within this invocation only; revalidate
on drift/error. Live page identity, status, ownership and pre-write content are NEVER cached.
Use the operation's specific reference, not the whole operations catalog. Additional return
shape details for uncommon callers live in `references/operations.md` (on demand).

| Operation | Reference |
|---|---|
| fetchTicket | `references/fetch-ticket.md` |
| findEpics | `references/find-epics.md` |
| getEpicContext | `references/epic-context.md` |
| listEpicChildren | `references/list-children.md` |
| updateTicket / updateStatus / setPullRequest / postComment / upsertSection / appendToSection / refreshAcceptanceCriteria | `references/write-ops.md` |
| createTicket / createEpic / resolveAssignee / setDependencies / setParent / refreshEpicTasks / getSelectOptions / addSelectOption | `references/create-ops.md` |

Read `references/query.md` before a data-source query (not needed for a direct page fetch).
Read `references/config-write.md` and `references/styling.md` before writes; reads do not load
writing/creation manuals. The complete source comes from fetchTicket, never a status query.
For shared title-prefix/marker rules, read only the `Title prefix` and `Marker usability rule`
sections in `references/create-ops.md` when needed; do not load its unrelated creation procedures.

## ID normalization

Callers may pass an `id` as a **logical key** — `STO-285`, `STO285`, or `285`. Normalize by stripping the configured `project.key` prefix and any separator, then parsing the remainder as an integer, then resolving it through the `idProperty` lookup. A **Notion page id or page URL** is also accepted, resolving the page directly.

**The value read back off the page needs the same normalization**, and this is not symmetry for
its own sake. A `unique_id` column carries its own prefix, and the two MCP access paths disagree
about whether they apply it: `notion-fetch` returns the property as the *prefixed string*
(`"userDefined:ID": "PDS-1"`), while `notion-query-data-sources` returns the bare integer (`1`) —
verified against a live database. So `fetchTicket` normalizes whatever it read — strip a leading
`<live unique_id prefix>` or `<KEY>` and any separator, then parse the remainder as an integer —
before putting it in `metadata` as the `idProperty` value. Every caller that says "the numeric
`<id>`" (`/notion-dev:ticket` Phase 1.1 derives branch, worktree and file names from it) depends
on that value already being numeric; taken unnormalized it yields `ticket/PDS-PDS-1-<slug>`.

A `number` ID column is unaffected — it has no prefix to strip — and the normalization is a
no-op there.

## Project scoping guardrail

When `staticProperties` is configured, those same properties act as a **fetch-side scope check**: a DB shared across projects will have tickets from other projects, and every per-ID operation starts from `fetchTicket`. After resolving a page, compare each `[name, expected]` in `staticProperties` against the fetched page's value for that property:

- **Match** (or property absent from the live DB) → proceed silently.
- **Mismatch** → abort with: *"`<PREFIX>-<id>` has `<prop>`=`<actual>`; this project is pinned to `<prop>`=`<expected>`. Refusing to operate on a ticket from a different project."* Record `abort:project-scope` per `notion-dev:issue-log`.

This is a hard abort — crossing project boundaries is always a user error in a multi-project DB setup. The guardrail applies to `fetchTicket` (and therefore to every operation that reaches a page through it: `updateTicket`, `updateStatus`, `setPullRequest`, `upsertSection`, `postComment`). `createTicket` is unaffected — it sets the pinned values, it doesn't verify them.

When `staticProperties` is empty or absent, the check is skipped — single-project DBs behave as before.

## MCP unavailability

There is no useful CLI fallback for Notion. If the MCP is unreachable, fail with: *"Notion MCP is unavailable. Re-check `.mcp.json`, confirm the `notion` server is listed, and retry."* Record `mcp-unavailable:notion` per `notion-dev:issue-log`.
