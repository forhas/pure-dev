# Problem statement: tasks finish with gaps and caveats

**Date:** 2026-08-28
**Status:** Problem statement only — not a design. Input to a future brainstorm.
**Scope:** `plugins/notion-dev`, `plugins/quick-dev`
**Related:** `2026-08-28-convergence-design.md` (the same leak, a different exit)

## Why this document exists

Clients report that a resolved ticket routinely ships with gaps or caveats attached: work the ticket said it would do that it did not do, and limitations disclosed in prose that nobody tracks.

The convergence change (`2026-08-28-convergence-design.md`) closed the exit where escaping work became **new tickets**. It did not close two other exits. This document records them while the evidence is fresh, so a future session can brainstorm a fix from data rather than from recollection.

**The session that produced the convergence change is itself the primary evidence.** It shipped a pull request containing a `## Known gaps` section, and those gaps were closed only because a human noticed and asked. Every instance cited below is drawn from that session rather than hypothesised.

## Root cause 1 — the acceptance criteria are never checked

`## Acceptance Criteria` is a first-class section of every ticket. It is:

- produced by `notion-dev:ticket-interviewer` (`SKILL.md:129`),
- rendered into Notion as **to-do blocks** — `ticket-system/SKILL.md:201` states it is "always a **to-do list** (`- [ ]` → Notion to-do blocks). Never plain bullets",
- carved per-task when a mission is split (`task-breakdown/SKILL.md:96`),
- passed into planning (`commands/ticket.md:156`).

Then nothing reads it again. No step in `/notion-dev:ticket`, `/notion-dev:finalize`, or `notion-dev:review-and-merge` evaluates whether the criteria are satisfied, ticks the boxes, or gates on them. `updateStatus(id, "implemented")` is triggered by **a merged PR**, not by met criteria.

So the ticket states its own definition of done, in explicitly checkable form, and the flow marks it done without ever consulting it. The checkboxes remain unticked in Notion permanently.

This is the single most likely source of the reported symptom: the criteria said X, the PR delivered most of X, and nothing compared the two.

**Note the shape.** A close-time gate — each criterion met, or explicitly re-triaged with a recorded reason — is structurally the same as the `absorb` merge gate the convergence change already ships. That symmetry is an argument for the design fitting cleanly rather than bolting on, and the existing gate is a working precedent to copy from.

**The genuinely hard part, and the reason this needs a brainstorm rather than an edit:** what does "criterion met" mean for a criterion that is not mechanically verifiable? Some are testable (`Three tests pass under npm run test:unit`). Others are judgments (`the error message is actionable`). A design that only handles the testable ones will quietly pass the rest, which recreates the current failure with more ceremony.

## Root cause 2 — self-declared caveats are an ungated third exit

The `absorb` / `file` / `drop` triage governs **review findings** — items raised by `plan-review` or by the code-review loop. It never sees a limitation that the *author* writes into the deliverable itself.

Phrases like "known gap", "not mitigated", "partially", "future work", "does not currently", "out of scope for now" enter as prose in a spec, plan, PR body, or skill file. No gate tests them. They are neither absorbed nor filed nor dropped — they are simply *stated*, and stating them is treated as sufficient.

### Three instances from the convergence session

1. **A mitigation claimed but never built.** The convergence spec's risk table stated that "the ledger can count reclassifications per run; a high rate is the signal the test is miscalibrated." No counter existed. The row read as a discharged risk. Caught only by the final whole-branch review reading the claim skeptically; later corrected to "Partially mitigated", then actually built.

2. **A false durability claim papering over a gap.** `quick-dev/skills/develop/SKILL.md` described the run's ephemeral chat report as `FILED` items' "only durable destination." A chat report is not durable at all. The sentence made a missing destination read like a present one.

3. **A `## Known gaps` section that nothing required to be empty.** The PR body listed two unresolved gaps. Nothing in the flow treated a non-empty gaps list as a merge concern. They were closed only because a human asked.

All three were caught by a reviewer reading prose adversarially. That is luck, not mechanism — and it does not scale to clients who are not running a whole-branch review on every change.

### Why the existing triage does not reach these

The rubric triages "work the plan could reasonably defer" — items a *reviewer* identifies. A caveat the author writes is not a review finding, is not a plan task, and never enters the vocabulary. The merge gate then has nothing to hold, because nothing was ever labeled.

## What a fix probably looks like

Deliberately not designed here. Sketching only enough to show the problem is tractable:

- **For root cause 1:** a close-time acceptance-criteria gate, mirroring the `absorb` merge gate. Each criterion is met, or re-triaged with a recorded reason. Ticking the Notion to-do blocks is the natural durable artifact, and `ticket-system` already renders them as real to-do blocks, so the write path exists.
- **For root cause 2:** extend the existing triage to self-declared limitations. A scan of the deliverable's own text for limitation language, with each hit labeled `absorb` / `file` / `drop` like any review finding — so a caveat cannot merely be written, and an `absorb` one must be done before merge.

Both reuse machinery the convergence change already ships. Neither is a mechanical edit.

## Explicitly not claimed

- That these are the only two causes. They are the two this session produced hard evidence for.
- That root cause 2's fix can be purely mechanical. Detecting limitation language by keyword will both over- and under-match; whether that is acceptable is a design question.
- That every caveat is a defect. Some limitations are correct and worth stating. The defect is that stating one currently *ends* the conversation instead of *starting* a triage.

## Suggested next step

A brainstorm session taking this document as input, treating root cause 1 first — it is the larger source of the reported symptom, its fix has a working precedent to copy, and it is independently useful even if root cause 2 is never addressed.
