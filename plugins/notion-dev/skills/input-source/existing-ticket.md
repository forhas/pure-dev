# existing-ticket source

Fetch an existing ticket from the configured ticket system and return its content as structured input.

Use this when the user wants to elaborate on a ticket that already exists but is thin or needs refinement before implementation.

## Steps

1. Normalize `ref` to a numeric ticket id (strip any `<PREFIX>-` prefix and separators).
2. Invoke the `notion-dev:ticket-system` skill, operation `fetchTicket(id)`. You get `{ title, body, status, url, metadata }`.
3. Structure the body into the output shape:
   - `title` — from the ticket's title.
   - `body` — the ticket body, normalized to use the standard sections (`## Requirements`, `## Acceptance Criteria`, `## Context`, `## Open Questions`). If the existing content doesn't match this shape, do a best-effort re-section but don't drop information — preserve any extra content under a `## Notes` heading.
   - `sourceRef` — the ticket URL.
   - `confidence`:
     - `"high"` — the body already has Requirements + Acceptance Criteria, both non-empty.
     - `"medium"` — one of those exists but not the other, or they're vague.
     - `"low"` — body is essentially just a title restatement or a one-liner.
4. Return the structured result.

The caller (typically `/notion-dev:create-task`) passes `confidence` to `notion-dev:ticket-interviewer`, which uses it to calibrate interview depth.

## Edge cases

- Ticket not found → raise a clear error; do not silently create a new one.
- Ticket is in a terminal status (e.g. `Done`, `Delivered`) → warn the user and ask via `AskUserQuestion` whether to proceed with elaboration anyway.
