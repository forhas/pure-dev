---
type: Ticket
title: Migrate STO-10
description: Old-format ticket used to exercise the migrate transform.
status: current
stale_after: 2026-01-01
verified: { by: x, at: y }
reconciled: { at: z }
generated: { by: smart-contracts:capture, at: 2026-09-01T00:00:00Z }
ticket: STO-10
---
# Problem
The old bundle format used `status: current` and tracked staleness fields the plugin no longer needs.

# Decision
Migrate the frontmatter to OKF v0.2 and drop the staleness-tracking fields.

# Ruled out
Keeping the fields for backward compatibility — nothing reads them anymore.

## Reconciliation notes
- 2026-09-05: confirmed against the ticket that the decision still holds.
