# notion-page source

Read an arbitrary Notion page (not necessarily a ticket) as raw requirement content.

Use this when the user has a design doc, meeting notes, or spec page in Notion that should seed a ticket.

## Steps

1. Normalize `ref`:
   - If it looks like a Notion URL (any of `notion.so`, `www.notion.so`, `notion.com`, `app.notion.com` — e.g. `https://app.notion.com/p/...`), extract the page ID: the last 32-char hex segment in the path (typically after the final `-`), ignoring dashes.
   - If it's already a bare page ID (with or without dashes), use as-is.
2. Fetch the page via `mcp__notion__notion-fetch`.
3. Convert the page blocks to markdown:
   - Preserve heading levels, bulleted lists, numbered lists, todo checkboxes, code blocks, callouts, and toggle lists (render toggle content inline).
   - Match heading text ignoring trailing Notion attributes like `{color="..."}`.
4. Map the content into the output shape:
   - `title` — from the page's title (top of the page, or the property named `Name` / `Title` if the page belongs to a database).
   - `body` — the markdown content. If the page already uses `## Requirements` / `## Acceptance Criteria` headings, keep them. Otherwise, the entire content goes under a `## Context` section, and we rely on the caller to elaborate.
   - `sourceRef` — the Notion page URL.
   - `confidence`:
     - `"high"` — the page explicitly has Requirements + Acceptance Criteria sections with non-empty content.
     - `"medium"` — the page has a clear structure with goals stated, but no checklist.
     - `"low"` — the page is freeform notes, a meeting transcript, or a draft.
5. Return the structured result.

## Edge cases

- Page not found (deleted or no access) → raise a clear error. Suggest the user check that the Notion MCP integration has access to the page's parent.
- Page is huge (> 100 blocks) → include only the first ~100 blocks and mention the truncation in `body` as a `> **Note**: source page truncated — review original.`
- Page is itself a ticket in the configured database → suggest the user use `existing-ticket:<id>` instead for cleaner roundtripping.
