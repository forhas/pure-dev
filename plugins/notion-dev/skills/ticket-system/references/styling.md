# ticket-system — styling conventions

Read before writing page content. The palette, dividers, callouts and rich-content
rules every write path renders through. Referenced from `../SKILL.md`.

## Styling conventions

Tickets are first-class user-facing documents. The adapter applies a fixed visual palette when writing known sections so the three logical zones — **spec** (from `/notion-dev:create-task`), **resolution** (from `/notion-dev:ticket`), and **shipping** (from `/notion-dev:finalize`) — are immediately distinguishable at a glance. Callers pass plain content; the adapter renders it into styled Notion blocks.

### Palette per section

| Heading | Written by | Heading color | Intro callout | Icon |
|---|---|---|---|---|
| `Requirements` | `/notion-dev:create-task` | `orange` | `orange_background` | 📋 |
| `Acceptance Criteria` | `/notion-dev:create-task` | `orange` | — | — |
| `Context` | `/notion-dev:create-task` | `gray` | — | — |
| `Open Questions` | `/notion-dev:create-task` | `red` | `red_background` | ❓ |
| `Source` | `/notion-dev:create-task` | `gray` | — | — |
| `Blocked by` | `/notion-dev:create-task` Pass 2, via `setDependencies` | `yellow` | — | — |
| `Implementation` | `/notion-dev:ticket` | `blue` | `blue_background` | 🔨 |
| `Merged` | `/notion-dev:finalize` | `green` | `green_background` | ✅ |
| `Overview` | `createEpic` | `gray` | — | — |
| `Tasks` | `createEpic` (empty at creation), create-task Pass 1.5 (populated when a mission is filed), and epic refresh (`/notion-dev:ticket` Phase 8, `/notion-dev:finalize` Phase 3) | `blue` | — | — |
| `Resolution Log` | epic update (same) | `purple` | — | — |
| `Notes` | `/notion-dev:new-info` | `gray` | — | — |

Unknown section names (including user-added ones) render with no color and no callout — the plugin only styles sections it owns. Match section names case-insensitively on base text; don't restyle sections a user has manually recolored (see "Heading attribute preservation" below).

The last four sections appear on **epic pages only**. None takes an intro callout — they are self-explanatory, and a callout on every one would be noise. `Tasks` renders as to-do blocks (same convention as `Acceptance Criteria`). The zone-divider rule below applies to `Implementation` / `Merged` on ticket pages only; epic pages use the per-entry divider described under `appendToSection`.

`Blocked by` is the one spec-zone section not written at creation — `setDependencies` adds it in Pass 2, once every mission ticket exists and can be resolved. It therefore lands at the end of the spec zone, which is where it belongs: nothing from a later zone has been written yet at Pass 2. It takes no callout for the same reason `Tasks` doesn't, and unlike `Tasks` it does **not** render as to-do blocks — see `setDependencies` for why.

### Zone dividers

Before writing `## Implementation` or `## Merged`, insert a `divider` block **if the immediately preceding block on the page isn't already a divider**. This carves the page into three visual zones:

```
[Requirements · Acceptance Criteria · Context · Open Questions · Source]
───────────── divider ─────────────
[Implementation]
───────────── divider ─────────────
[Merged]
```

Dividers are idempotent — never add a second one.

### Intro callouts

For sections in the palette marked with a callout color, render it as the first block under the heading with the section's icon and background color:

- **Requirements** — one-sentence distillation of the goal (fallback: `"What this ticket covers."`).
- **Open Questions** — literal: `"Unresolved before implementation — resolve these before running /notion-dev:ticket."`
- **Implementation** — status line, e.g. `"Status: PR open · <PR URL>"` or `"Status: Plan authored"`.
- **Merged** — shipping summary, e.g. `"Shipped <YYYY-MM-DD> · <commit-hash> · merged to <base>"`.

Callouts are regenerated on each write — the upsert replaces the whole section body, so old callout text never lingers.

### Rich content inside sections

After the callout (if any), render section body:

- **Requirements / Context / Source** — paragraphs and bulleted lists. No checkboxes.
- **Acceptance Criteria** — always a **to-do list** (`- [ ]` → Notion to-do blocks). Never plain bullets; the checkability is the point.
- **Open Questions** — bulleted list; consider using **red** inline text for the actual question and neutral for surrounding framing.
- **Implementation** — a labeled block for `Plan`, `Implementation`, `Files Changed`, `PR`, `Branch`, `Notes`. Render labels as bold (`**Plan**`) followed by the value. For `Files Changed`, group by directory as a nested bulleted list. For `PR` and `Branch`, render as code-formatted text so they copy cleanly.
- **Merged** — mixed render: a 2-column (Field / Value) Notion **table** for the scalar fields in the order they appear in the content dict (e.g. `PR`, `Merge commit`, `Merge strategy`, `Base branch`, `Merged at`), followed by **labeled list sections** for narrative/list fields (`Review resolution` as bullets, `Absorbed` as a bulleted list, `Deferred follow-ups` as a bulleted list with linked ticket IDs where present, `Dropped` as a bulleted list with each item's rationale). The adapter decides per-field which side of the split a value goes:
  - **scalar** (string, URL, timestamp, short identifier) → table row.
  - **list or multi-line markdown** → labeled section below the table.
  
  Example rendering:
  ```
  🟢 ## Merged
  ┌────────────────┬──────────────────────────────┐
  │ PR             │ <PR URL>                     │
  │ Merge commit   │ `abc123def`                  │
  │ Merge strategy │ squash                       │
  │ Base branch    │ master                       │
  │ Merged at      │ 2026-04-24T14:32:00Z         │
  └────────────────┴──────────────────────────────┘
  
  **Review resolution**
  • Applied 4 comments across auth/session handling.
  • Absorbed 1 finding; deferred 1 as follow-up (see STO-42).
  • Disagreed on naming suggestion; left a reply.

  **Absorbed**
  • Tightened the token TTL check the reviewer flagged (same file as the fix).

  **Deferred follow-ups**
  • STO-42 — refactor session token storage (criterion 3: a storage refactor would
    obscure this one-line fix)

  **Dropped**
  • Rename `sess` to `session` throughout — cosmetic churn, declined under the judgment bar.
  ```

### Heading attribute preservation

When `updateTicket`'s body merge re-writes an existing section, **read the existing heading's trailing attribute block** (e.g. `{color="orange"}`) and preserve it verbatim in the rewritten heading. Do not override a user's manual color choice. Only when the existing heading has no attribute should the adapter apply the canonical palette color from the table above.

