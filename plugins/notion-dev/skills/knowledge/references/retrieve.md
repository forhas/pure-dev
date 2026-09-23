Read `common.md` once per invocation. Other operations are not prerequisites.

## `retrieve(<epic-id>, <ticket-title>?, <ticket-id>?)` → `KNOWLEDGE_CONTEXT` or `null`

Read-only. It writes nothing and runs before any worktree exists.

### Read-once

| fact | read from | never from |
|---|---|---|
| requirements | the ticket body, `fetchTicket` | bundle, brief |
| children statuses | `listEpicChildren` | bundle, brief (neither stores status) |
| epic identity (key, title, url) | `fetchTicket(<epic-id>)`, properties only | the Notion epic page body |
| why / where we stand / threads / decisions / next | the brief, as the root of the retrieve | Notion epic page |
| ruled-out approaches, gotchas, constraints | the retrieve result | a recursive grep, `index.md`, a second query |
| the merge's content | `git show <merge-sha>`, `gh pr view` | Notion |

### Steps

1. Reuse verified epic identity/metadata supplied from this same selection boundary; otherwise
   `fetchTicket(<epic-id>)` via `notion-dev:ticket-system`. Apply the epic predicate
   (`metadata.parentTaskProperty` empty **and** `metadata.epicMarkerProperty` true — the one
   `findEpics()` and `/notion-dev:ticket`'s epic guard apply). Not an epic → return `null`.
2. Reuse schedule's fetched bundle revision/root location when no intervening write or ref
   change occurred. Otherwise `git fetch origin`, then locate the root on `origin/<epicBranch>` with
   `git ls-tree -r --name-only origin/<epicBranch> -- <knowledge.dir>/epic/` filtered to
   `<KEY>-<n>-*.md`. Missing → bootstrap **in memory** exactly as `epic-doc` "Bootstrap"
   describes, its seed search now also covering `<knowledge.dir>/epic/`; return the brief alone
   with `BOOTSTRAP: true` and `SEED: <path>` or `SEED: notion`, and skip step 3. A failing
   fetch or an `ls-tree` error — no network, no such branch — is not "missing": it takes step 5's
   degrade path, since a bundle that cannot be reached must not be reported as absent.
3. One call, run from a temporary export of the bundle at `origin/<epicBranch>` so a stale local
   checkout never answers (`git archive origin/<epicBranch> <knowledge.dir> | tar -x -C <tmp>`,
   then run from `<tmp>/<knowledge.dir>`, and remove `<tmp>` once the call returns, whether it
   succeeded or not):

   ```
   iwe retrieve -k epic/<KEY>-<n>-<slug> --expand-references 1 \
     --lexical "<ticket title>" --filter 'status: stable' --max-tokens <knowledge.retrieveBudget> -f markdown
   ```

   The root is always first and never trimmed; the lexical seed is omitted when no ticket title
   is given (for example `/notion-dev:new-info`). Lean `/notion-dev:next-task` selects first and
   supplies the chosen ticket title, never an epic-only lexical seed. `deprecated` and `draft` concepts
   are excluded by the filter. Reference expansion is the only expansion this plugin relies on;
   inclusion expansion is never requested, so a concept is never pulled in whole by another.
4. Return `KNOWLEDGE_CONTEXT` — the retrieve output verbatim — plus the fields `epic-doc parse`
   returns (load `skills/epic-doc/references/parse.md`, not its writer or full drift audit): `EPIC_CONTEXT`,
   `NEXT`, `BLOCKED`, `STATUS`, `CHILDREN` (one `listEpicChildren(<epic-id>)` call, since no
   concept stores a live status; reuse a list read at this same selection boundary), `BOOTSTRAP`,
   `DRIFT` and `SEED`. Do not fetch every sibling body to audit scheduling during retrieval.
5. `iwe` missing or the call failing → read the root alone with
   `git show origin/<epicBranch>:<root path>` as `EPIC_CONTEXT`, return
   `KNOWLEDGE_CONTEXT: unavailable`, and record `partial:knowledge-retrieve` per
   `notion-dev:issue-log`. **The run continues** —
   a bundle that cannot be read costs context, not the ticket.

**The parse of the root.** `-f markdown` emits one fenced block per document, each opening with
a ```` ```markdown #<key> ```` line and carrying a YAML frontmatter block (`title`, `references`,
…) before the body, the seed document first:

````
```markdown #epic/STO-60-wallet-indexing
---
title: "[STO-60] Wallet Indexing"
references: [decision/offline-deploy, gotcha/cache-ttl]
---
# [STO-60] Wallet Indexing
…
```
````

`EPIC_CONTEXT` is that **first fenced document with its frontmatter stripped** — the brief as
`epic-doc` writes it, nothing more. `NEXT`, `BLOCKED` and `STATUS` are parsed out of it exactly
as `epic-doc read` step 3 parses them, which is all `epic-doc read` now is: a name for this parse
over a retrieve result. Callers treat the whole block as **background, not requirements**, exactly
as `EPIC_CONTEXT` is treated today; the ticket body remains the source of truth for what to build.

**Budget.** `retrieveBudget` bounds the bundle's share of a run's context. The root is ≤ 120 lines
by `epic-doc`'s rule; the remainder is the concepts one reference hop away plus the lexical seeds,
with the periphery trimmed first by iwe. Raising the budget is a config change, never an extra
call.
