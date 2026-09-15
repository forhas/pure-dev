---
type: Epic
title: "[STO-60] Wallet Indexing"
description: "Index every wallet once."
status: stable
epic: STO-60
generated: { by: notion-dev:epic-doc, at: 2026-09-13T00:00:00Z }
sources:
  - { id: epic, resource: "https://notion.so/STO-60", title: "[STO-60] Wallet Indexing" }
---
# [STO-60] Wallet Indexing
Epic: https://notion.so/STO-60 · Status: open · Updated: 2026-09-14 after [STO-70]

## Why
Wallets are indexed twice today.

## Goal
Index every wallet once.

## Where we stand
STO-70 landed the backfill.

## Open threads
- **Waiting on customer logs** for v1.4.2 — blocks STO-22. Unblocked by: logs attached to STO-22.

## Decisions & constraints
- Cache TTL is 60s.

## Next
1. **[STO-70] Backfill** — first in phase order.
2. [STO-71] Cache metrics — after STO-70
Blocked: STO-22 (see Open threads).
