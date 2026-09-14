# [STO-9] Demo epic
Epic: https://notion.so/STO-9 · Status: open · Updated: 2026-09-01

## Why
The migrate fixture needs a pre-OKF epic brief with no frontmatter to move into `epic/`.
See the [seed](../STO-9-seed.md) plan for the background this epic grew out of.

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
