---
type: Decision
title: Keep the cache
description: Cache stays positive-only; no negative caching.
status: stable
epic: STO-1
applies_to: ["src/cache/**"]
generated: { by: notion-dev:knowledge, at: 2026-09-14T00:00:00Z }
sources:
  - { id: ticket, resource: "https://notion.so/STO-2", title: "[STO-2] Cache design" }
---
# Keep the cache
The cache stays positive-only: it never records negative lookups.
