# ticket-system — write operations

Read before the first write. `updateTicket`, `updateStatus`, `setPullRequest`, `postComment`,
`upsertSection`, `refreshAcceptanceCriteria`, `appendToSection`. Referenced from `../SKILL.md`.

## updateTicket(id, patch)

`patch` may contain `title`, `body`, or `type` — any subset.

1. `fetchTicket(id)` → `pageId` and the current page content.
2. For each provided field:
   - `title` → strip any matching prefix from the incoming value (see "Title prefix"), then write `[<KEY>-<n>] <stripped>` to the page's title-typed property (whatever its name on the live DB) via `mcp__notion__notion-update-page`.
   - `type` → update the `typeProperty` if the database has one. Translate the logical key through `typeMap` and write as scalar (Select) or single-item list (Multi-Select) to match the live property type. Ignore when `typeProperty` is absent from the live DB.
   - `body` → **heading-scoped merge**, not wholesale replacement:
     1. Parse the existing page blocks and the new `body` markdown into `## <heading>` sections.
     2. For each `## <heading>` present in the **new** body: replace that section's children on the page. **Preserve the existing heading's trailing attribute block** (`{color="..."}`) verbatim — don't overwrite a user's manual color choice. If the existing heading has no attribute, apply the palette color from the Styling conventions table.
     3. Re-render the section's children with the Styling conventions applied (intro callouts, to-do blocks for Acceptance Criteria, etc.).
     4. For each `## <heading>` present **only** on the existing page: preserve it unchanged (content AND heading attributes).
     5. This guarantees that plugin-managed sections written by other commands — `## Implementation` (from `/notion-dev:ticket`), `## Merged` (from `/notion-dev:finalize`), and any future named sections added via `upsertSection` — are never wiped by a later `create-task` elaboration or any other call that supplies a partial body.

2a. **Prefix backfill.** Even when `patch` contains no `title`, inspect the live title. If it has no prefix, or a prefix whose number does not match this page's ID, rewrite it to `[<KEY>-<n>] <existing title, stripped>`. This is what lets `/notion-dev:create-task existing-ticket:<id>` repair a legacy title with no change to that command.

3. Return `{ id, url: pageUrl }`.

## updateStatus(id, logicalStatus)

1. Resolve the Notion option name from `statusMap[logicalStatus]` with the defaults above.
2. `fetchTicket(id)` to get the `pageId`.
3. Call `mcp__notion__notion-update-page` setting the `statusProperty` select to the resolved option.

## setPullRequest(id, url)

1. `fetchTicket(id)` to resolve `pageId`.
2. If the live DB has a property named by `prProperty` AND that property is a URL type, call `mcp__notion__notion-update-page` to set it to `url`.
3. If the property is absent or not URL-typed, log one warning (`"prProperty '<name>' not found on DB; skipping PR property write"`) and return — do not raise. Record `missing-property:prProperty` when the property is absent, or `wrong-type:prProperty` when it exists but is not a URL property, per `notion-dev:issue-log`. The PR URL is still recorded in the `## Implementation` section body by `/notion-dev:ticket`.

## postComment(id, text)

1. `fetchTicket(id)` to resolve `pageId`.
2. Call `mcp__notion__notion-create-comment` on the page with `text`.

## upsertSection(id, sectionName, content)

Writes (or overwrites) a single named section on the ticket page body.

`content` is either:
- A dict of labeled entries — rendered as labeled paragraphs or bulleted sub-sections under the heading.
- A markdown string — rendered verbatim under the heading.

Example dict:
```
{
  "Plan": "Short summary of the approach.",
  "PR": "<url>",
  "Files Changed": ["apps/api/...", ...],
  "Notes": "<markdown>"
}
```

Steps:
1. `fetchTicket(id)` → `pageId`.
2. Scan the page for an existing `## <sectionName>` heading (match base heading text, **ignoring** Notion trailing attributes like `{color="..."}`).
3. Resolve styling (see Styling conventions):
   - If `sectionName` is a palette entry (`Implementation`, `Merged`, `Overview`, `Tasks`), apply its heading color and prepend its intro callout (`Overview` and `Tasks` take none, per the palette table).
   - Render the content body following the palette's rich-content rules (labeled fields for Implementation; table for Merged).
   - If writing `Implementation` or `Merged`, ensure a `divider` block sits immediately before the heading — insert one if the preceding block isn't already a divider.
4. If the section already exists, call `mcp__notion__notion-update-page` to **replace** its children (from the heading down to the next top-level heading or end of page). Preserve the existing heading's trailing attribute block verbatim. Do not duplicate the heading. The divider, if present, is preserved; if absent, insert one.
5. If the section does not exist, append the blocks at the end of the page (divider, heading, callout, body).

Different section names (e.g. `"Implementation"` and `"Merged"`) coexist — `upsertSection` only touches the named section. Dividers between them are idempotent: each write checks for an adjacent divider before inserting one.

## refreshAcceptanceCriteria(id, verdicts)

Re-renders the ticket's `## Acceptance Criteria` section as to-do blocks, ticking each box that its verdict marks `met`. **The single owner of the `Acceptance Criteria` section's format** after creation — `/notion-dev:ticket` Phase 8 and `/notion-dev:finalize` Phase 3 both write it, and without one owner they drift apart exactly as `refreshEpicTasks` exists to prevent for `## Tasks`.

`verdicts` is an ordered list matching the caller's criteria file line-for-line: `{ criterion, verdict }` with `verdict` ∈ `met` | `not-met` | `unverified`.

1. `fetchTicket(id)` → `pageId`. If the page has no `## Acceptance Criteria` section, return without writing. A ticket may legitimately have none (`/notion-dev:finalize` accepts any PR), and inventing the section here would fabricate a definition of done.
2. Render one Notion to-do block per entry, in the given order:

```
- [x] Three tests pass under `npm run test:unit`
- [ ] The error message names the offending field
```

   The box is ticked when and only when `verdict` is `met`. Both `not-met` and `unverified` render unticked — they are different states, but neither is met, and the distinction is carried by the `Completeness` record in `## Implementation`, which is where a rationale can actually be read.
3. **Take each criterion's text verbatim from `verdicts[].criterion`, which the caller sourced from the criteria file — never from the verifier's summary or any paraphrase of it.** `upsertSection` replaces a section's children wholesale, so a paraphrase anywhere on this path would silently rewrite the ticket's own definition of done. That is the worst available failure in a change whose entire purpose is to stop "done" being quietly altered.
4. `upsertSection(id, "Acceptance Criteria", <rendered blocks>)`.

Safe to call repeatedly: the rendering is a pure function of `verdicts`, and `upsertSection` replaces only up to the next top-level heading, so `## Implementation` and `## Merged` below are never touched.

## appendToSection(id, sectionName, content)

The **append-only** counterpart to `upsertSection`. Where `upsertSection` replaces a section's children, this adds to the end of them. Use it wherever history must accumulate rather than be overwritten.

1. `fetchTicket(id)` → `pageId`.
2. Scan the page for an existing `## <sectionName>` heading — match base heading text, **ignoring** trailing Notion attributes like `{color="..."}`.
3. **Section absent** → append the heading at the end of the page, applying the palette color from the Styling conventions table, then write `content`'s blocks beneath it.
4. **Section present** → append `content`'s blocks immediately before the next top-level (`##`) heading, or at end of page when it is the last section. Existing children are never read back, rewritten, or reordered — that is the whole point of this operation.

`content` is markdown, rendered with the same block conventions `upsertSection` uses.

**Epic-page callers prepend their own divider.** The callers that accumulate dated entries on an epic page — `epic-update`'s `Resolution Log`, `/notion-dev:new-info`'s `Notes` — pass a `divider` block ahead of each entry, so entries stay visually separate as the section grows. That is the per-entry divider the Styling conventions refer to; this operation writes the blocks it is given and adds no divider of its own.

