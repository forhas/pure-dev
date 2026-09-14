---
type: Epic
title: "[STO-1] Demo epic"
description: Fixture epic for knowledge.py harness tests
status: stable
epic: STO-1
generated: { by: notion-dev:epic-doc, at: 2026-09-14T00:00:00Z }
sources:
  - { id: epic, resource: "https://notion.so/STO-1", title: "[STO-1] Demo epic" }
---
# [STO-1] Demo epic
Epic: https://notion.so/STO-1 · Status: open · Updated: 2026-09-14

## Why
The knowledge bundle harness needs one epic-shaped fixture to exercise `check`, `touched`, and `migrate`.

## Goal
Ship a valid bundle small enough to hand-verify against the OKF v0.2 schema.

## Where we stand
Every fixture file validates against the shipped `.iwe/` schemas.

## Open threads
None — this is a static fixture, not a live epic.

## Decisions & constraints
- [Keep the cache](../decision/missing.md) — binds STO-2.

## Next
No further work; this file is regenerated only when the fixture contract changes.
