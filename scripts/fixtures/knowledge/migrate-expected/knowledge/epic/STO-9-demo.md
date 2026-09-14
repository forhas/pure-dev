---
type: Epic
title: "[STO-9] Demo epic"
description: "Prove that `migrate` adds OKF frontmatter when moving a brief into the bundle."
status: stable
epic: STO-9
generated: { by: notion-dev:migrate, at: "1970-01-01T00:00:00Z" }
sources:
  - { id: epic, resource: "https://notion.so/STO-9", title: "[STO-9] Demo epic" }
---
# [STO-9] Demo epic
Epic: https://notion.so/STO-9 · Status: open · Updated: 2026-09-01

## Why
The migrate fixture needs a pre-OKF epic brief with no frontmatter to move into `epic/`.
See the [seed](../../docs/STO-9-seed.md) and [guide](/docs/guide.md) plan for the background this epic grew out of.

## Goal
Prove that `migrate` adds OKF frontmatter when moving a brief into the bundle.

## Where we stand
The brief lives at `docs/epics/STO-9-demo.md`, outside the knowledge bundle.

## Open threads
None.

## Decisions & constraints
None yet.

## Next
Run `migrate --apply` and confirm the brief lands at `epic/STO-9-demo.md`.
