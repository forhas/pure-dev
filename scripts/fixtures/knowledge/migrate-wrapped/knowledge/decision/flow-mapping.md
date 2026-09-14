---
type: Decision
title: "Wrapped frontmatter survives the migration"
description: "A dropped key used to leave its wrapped continuation line behind as orphaned YAML."
status: current
ticket: STO-9
reconciled: { at: 2026-09-07T19:35:00Z, by: knowledge-curate/opus-5,
              against: [pr-82, repo-deploy-script] }
verified:
  by: human:yogev
  at: 2026-09-07T00:00:00Z
generated: { by: knowledge-capture/opus-5, at: 2026-09-01T00:00:00Z }
sources:
  - id: ticket
    resource: "https://notion.so/STO-9"
    title: "[STO-9] Demo epic"
---
# Wrapped frontmatter survives the migration
`reconciled` wraps its flow mapping over two lines and `verified` nests a block mapping
under it. Dropping either of them one physical line at a time orphaned the continuation
and left the document with no parseable frontmatter at all.

## Reconciliation notes
- 2026-09-05: confirmed against the ticket that the decision still holds.
