---
type: Ticket
title: Migrate STO-10
description: Old-format ticket used to exercise the migrate transform.
status: draft
generated: { by: smart-contracts:capture, at: 2026-09-01T00:00:00Z }
ticket: STO-10
sources:
  - { id: migrated, resource: ticket/STO-10.md }
---
# Problem
The old bundle format used `status: current` and tracked staleness fields the plugin no longer needs.

# Decision
Migrate the frontmatter to OKF v0.2 and drop the staleness-tracking fields.

# Ruled out
Keeping the fields for backward compatibility — nothing reads them anymore.

## Updates
- 2026-09-05: confirmed against the ticket that the decision still holds.
