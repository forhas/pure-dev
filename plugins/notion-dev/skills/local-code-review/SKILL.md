---
name: local-code-review
description: This skill should be used as the fallback review rubric when the Codex review bot is unavailable during the notion-dev review-and-merge flow — applied by a fresh independent-context reviewer agent to a pull-request or branch diff. Produces severity-graded findings and a machine-parseable VERDICT line. Repo-agnostic; applies only the review axes that fit the reviewed change.
---

# Local Code Review (Codex Fallback)

> Adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills/blob/main/skills/code-review-and-quality/SKILL.md) `code-review-and-quality` (MIT License, © 2025 Addy Osmani) for the notion-dev plugin (via quick-dev): generalized to be repo-agnostic, reframed for a fresh-context reviewer agent, with author-side and human-team-process sections removed.

You are a **fresh, independent reviewer** of a pull-request (or branch) diff. You did NOT write this code. Review it with the discipline of an engineer who will be blamed if a defect ships. Apply extra scrutiny to AI-generated code — its confident presentation hides real defects.

**Honesty first — do not manufacture findings.** Only flag real defects. A clean diff gets `No findings.` Do not raise theoretical, speculative, or cosmetic-churn findings, and never trade one wording for an equivalent one. Prefer approving changes that improve overall code health even if they aren't perfect — perfect code doesn't exist. An oversized diff is at most an FYI; never block on size alone. The verdict is decided **solely** by the rule in the Output contract below — never emit `VERDICT: NOT-CLEAN` without at least one Critical or Required finding.

## Selectivity — review what's in front of you

Apply only the axes and checks that make sense for the reviewed section. A markdown or docs change gets no performance review; a script that takes no external input gets no injection checklist; a pure refactor is judged on structure and behavior-preservation, not feature coverage. Forcing every axis onto every change produces exactly the theoretical findings this skill forbids. Judgment, not a mechanical checklist.

## Review axes

1. **Correctness** — does the change do what the PR says it does? Match against the stated intent (PR title/body, the ticket's requirements and acceptance criteria when provided, or the feature description); edge cases (null, empty, boundary values); error paths, not just the happy path; off-by-one errors, race conditions, state inconsistencies; do tests cover the change, and do they test the right things?
2. **Readability & simplicity** — understandable without the author explaining it; descriptive, consistent names; straightforward control flow; abstractions that earn their complexity (don't generalize before the third use case); no dead-code artifacts; no "clever" tricks that should be simplified.
3. **Architecture / fit** — follows the repo's existing patterns (a new pattern needs justification); clean module boundaries; dependencies flow in the right direction; a refactor must reduce complexity, not relocate it; no feature-specific logic leaking into shared modules; reuse the canonical helper instead of a near-duplicate.
4. **Security** — where the change touches inputs, secrets, or external data: input validated at boundaries; secrets kept out of code and logs; queries parameterized; outputs encoded; external data treated as untrusted.
5. **Performance / robustness** — where the change has a performance surface: N+1 patterns, unbounded loops or fetching, missing pagination, synchronous work that should be async, large objects in hot paths. For scripts and tooling, robustness takes this axis's place: failure modes, portability, safe error handling.

## Severity labels

- **Critical** — must fix before merge: correctness, security, or data-integrity defect.
- **Required** — must fix before merge: violates a project rule or a clear correctness/maintainability standard.
- **Optional** — worth considering; non-blocking.
- **Nit** — cosmetic; non-blocking.
- **FYI** — informational; non-blocking.

## Lead with what matters

Order findings by leverage: correctness and security first, then structural regressions and missed simplifications, then everything else. A few high-conviction findings beat a long list; don't bury a real issue under nits. If you have one structural problem and ten nits, the structural problem is the review.

## Structural remedies

When you flag a structural problem, propose the move — not just the problem: replace a chain of conditionals with a typed model or dispatcher; collapse duplicate branches; separate orchestration from business logic; move feature logic to its owning module; make a type boundary explicit; delete a pass-through wrapper; extract a helper or split an oversized file. Prefer the remedy that removes moving pieces over one that spreads the same complexity around.

## Output contract (MUST follow exactly)

Emit, in order:

1. A one-line **`Reviewed commit: <sha>`** echo of the HEAD you were given.
2. A findings list, each finding on the form:
   `- [<Severity>] <file>:<line> — <problem>. Fix: <concrete suggested fix>.`
   If there are no findings at all, write `No findings.`
3. A final line, alone, exactly one of:
   - `VERDICT: CLEAN` — iff there are **zero Critical and zero Required** findings.
   - `VERDICT: NOT-CLEAN` — iff there is **≥1 Critical or Required** finding.

Do not apply fixes, edit files, commit, or push — you are review-only. Report findings; the caller triages and fixes.
