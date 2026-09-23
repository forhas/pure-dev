Use the shared guards in `../SKILL.md` and `config.md`. Before any data-source query read `query.md`; before resolving a page read `fetch-ticket.md`.

## getEpicContext(epicId, currentTicketId)

Read-only. Assembles the bounded Notion-side context block that `notion-dev:epic-doc` distills into an epic's brief when none exists yet (its bootstrap path) — superseded by `notion-dev:knowledge` `retrieve` for every context read; only `notion-dev:epic-doc`'s Notion-source bootstrap still calls it. `currentTicketId` is the id of the ticket being started — the same `id` `/notion-dev:ticket` Phase 1.1 resolved via its own `fetchTicket(id)` call; passed explicitly so this operation never depends on being invoked in any particular sequence. **The sole owner of what "epic context" means and how much of it is included** — callers must never assemble this themselves or parse `## Resolution Log` directly; that format belongs to `epic-update`, and a second copy of the parser in a command file is how the two drift apart.

1. If `epicId` is empty, return `null`. Not a warning — this is the normal case for most tickets, which have no epic. If instead `epicMarkerProperty` is **unusable** on the live DB — absent, **or present but not a Checkbox** — also return `null`, per the **"Marker usability rule"** under "Epic containers". A wrong-typed marker leaves epic identity just as unverifiable as a missing one; the rule requires the two to be indistinguishable in behavior, and neither may fall through to step 2's fetch to be silently swallowed by that step's `false`-collapsing validation.

   Neither unusable cause is routine, but **neither is recorded here** — this operation is the rule's named non-recorder. `fetchTicket` step 4a owns `missing-property:epicMarkerProperty` and `wrong-type:epicMarkerProperty` for every path that flows through it, and this is one: it already observed and recorded whichever cause applies the moment it read the property for any ticket, including the caller's own `fetchTicket(currentTicketId)` call that resolved `currentTicketId` before this operation was ever invoked. Recording again here would give one condition two owners, exactly the pattern that kept reopening this bug. `/notion-dev:ticket <existing-child-ticket>` can reach this operation directly, without ever calling either direct-schema recorder (`findEpics` or `createEpic`) — but it always does so only after its own `fetchTicket(currentTicketId)` call, which is where these two causes are actually observed and recorded.
2. `fetchTicket(epicId)` → epic identity (`key`, `title`, `url`), `body`, and its own `metadata.parentTaskProperty` / `metadata.epicMarkerProperty`. **Validate before proceeding**: if the fetched page's own `parentTaskProperty` is non-empty, or its `epicMarkerProperty` is not `true` (`false` whether because the box is unchecked, the property is absent from the live DB, or it is present but not a Checkbox — `fetchTicket` collapses all three to the same default; see "Property type handling"), this is not a structurally valid epic — return `null`, the same signal as step 1's "no epic" case, and do nothing further. This is the same predicate `findEpics()`, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply; enforcing it here, inside the adapter, means every caller — present or future — inherits it rather than having to re-check at each call site. Without it, a `parentTaskProperty` value that merely points at an ordinary Notion Sub-items parent (not an epic) would be handed back as if it were one: a nonexistent `## Overview`, the parent's other children mislabeled as "siblings," and none of it flagged as anything other than epic context.
3. **Overview.** Extract the `## Overview` section verbatim from `body`. Omit the heading and body entirely from the output when the section is absent.
4. **Sibling status.** Call `listEpicChildren(epicId)` — a **live** call, never derived from the epic body's `## Tasks` section. That section is documented as "Snapshot as of the last resolution" and is only refreshed when a child resolves, so it is stale by construction; handing a starting ticket stale sibling status would be worse than handing it none. Render one line per child: `[{key}] {title} — {status}`. Mark the entry whose `id` equals `currentTicketId` with a trailing ` (this ticket)` so the reader can locate itself among its siblings. When `currentTicketId` matches no entry — e.g. the parent relation was just set but the epic's child query has not yet picked it up — mark nothing and continue; this is not an error.
5. **Recent resolution history.** Parse `## Resolution Log` from `body` into its `### [<KEY>-<n>] resolved — <datetime>` entries, in document order. **Tolerate the backslash-escaped bracket form** (`### \[<KEY>-<n>\] resolved`) exactly as the title-prefix detection does — see "Title prefix" for the canonical rule and what an unescaped parse costs `epic-update`'s idempotency check. `appendToSection` always appends at the end, so the **last 3** entries in document order are the most recent 3 resolutions — take those. When more than 3 entries exist, prepend a line stating how many older entries were omitted, so the reader knows there is more history and where to find it (the epic `url` from step 2).
6. Assemble and return one markdown block, in this order — identity, `## Overview` (when present), sibling status, recent resolution history:

```
## Epic context: [<KEY>-<n>] <epic title>
<epic url>

## Overview
<verbatim epic overview text>

### Siblings
- [<KEY>-67] Fix stale index — Implemented
- [<KEY>-68] Add cache metrics — In Progress (this ticket)
- [<KEY>-69] Backfill historic wallets — Backlog

### Recent resolution history
…2 older entries omitted — see the epic page for full history.
### [<KEY>-65] resolved — 2026-07-30 14:02 UTC
**Summary** — ...
### [<KEY>-66] resolved — 2026-07-31 09:15 UTC
**Summary** — ...
```

**Background, not requirements.** This block is context for the caller's reasoning, never a source of tasks or acceptance criteria — a resolution-log entry can describe an approach the current ticket now contradicts. Callers are responsible for stating that framing wherever they hand this block onward; see `/notion-dev:ticket` Phase 1.1.
