---
name: input-source
description: Use when a notion-dev command needs to ingest raw requirement content from a configured source (prompt, existing-ticket, notion-page). Dispatches to the concrete source file based on the source name.
---

# input-source

Provides a uniform interface for ingesting requirement content into the workflow. Commands invoke this skill with a source name and a reference; this skill dispatches to the concrete source file in the same directory.

## Dispatch

The caller passes `(source, ref)`:
- `source = "prompt"` → follow `prompt.md`; `ref` is the raw text.
- `source = "existing-ticket"` → follow `existing-ticket.md`; `ref` is a ticket ID.
- `source = "notion-page"` → follow `notion-page.md`; `ref` is a Notion page URL or ID.

If `source` is not in the configured `inputSources` list, fail and tell the user to add it via `/notion-dev:init`.

## Output shape

Every source returns:

```
{
  "title":      "<short title suggestion>",
  "body":       "<markdown — Requirements, Acceptance Criteria, Context, Open Questions>",
  "sourceRef":  "<url or literal>",
  "confidence": "high" | "medium" | "low"
}
```

## Confidence

- `high` — goal, scope, and acceptance criteria are all clearly covered.
- `medium` — criteria exist but are vague or incomplete.
- `low` — sparse text (< ~100 chars), or missing acceptance criteria, or the source is a rough note.

The caller passes `confidence` to `notion-dev:ticket-interviewer`, which uses it to calibrate interview depth before the ticket is written.
