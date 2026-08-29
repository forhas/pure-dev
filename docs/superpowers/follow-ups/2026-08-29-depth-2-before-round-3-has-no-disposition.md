# Follow-up: a chain reaching `depth = 2` before round 3 has no valid disposition

**Filed:** 2026-08-29, from the review loop on PR #18 (`d1c9383`).
**Source finding:** codex `3887414362`, round 6, severity **P1 → `blocking`**.
**Why filed rather than fixed:** Rule 2's own induced cap. The finding itself sat at
`depth = 2` on a chain whose root was `blocking`, and that branch says *keep the fixes, file the
depth-2 finding*. Two repairs had already been made on that chain; a third is precisely what the
cap refuses. Fixing it anyway would have made the cap mean nothing.
**Ground cited:** **the induced cap itself** — not a blast-radius criterion. The work leaves the
PR because the chain was cut, not because of blast radius. **Marked `blocking`**: this is a
deferred known defect, not a nicety.

---

## The problem

Three rules interact, and for one reachable case they leave a finding with **no legal
disposition at all**.

**Rule 2 — the induced cap** (`plugins/quick-dev/skills/review-and-merge/SKILL.md`):

> **A finding at `depth ≥ 2` is never absorbed.**

**Rule 1's second `drop` ground**, added during PR #18 to give real-but-uncitable late findings
an honest outcome:

> **`drop` here has a second, distinct ground, and it must be stated as such.** A **late
> non-blocking** finding can be genuinely right … and then *no* blast-radius criterion is true
> and `file` has nothing honest to cite. `drop` it, with the rationale that **the ratchet judged
> it not worth another round** …

That ground is scoped to a **late** finding — Rule 1 governs "from round 3 onward". Rule 2's
non-blocking branch then points at it:

> - **non-blocking** → `drop` it on Rule 1's second ground, with the chain as its rationale.

### The reachable hole

A chain can reach `depth = 2` **before round 3**:

| round | event | depth |
|---|---|---|
| 0 | a pre-existing comment (step 2) raises a `blocking` finding | 0 |
| 1 | the reviewer finds a defect **in that fix** | 1 |
| 2 | the reviewer finds a **non-blocking** defect **in that repair** | **2** |

At round 2 that finding is:

- **not absorbable** — Rule 2 forbids it at `depth ≥ 2`;
- **not filable** — no blast-radius criterion is true (it is inside files the PR already
  changes, needs no new interface, settles no design question);
- **not droppable** — Rule 1's second ground requires round 3+, and the *first* ground
  ("theoretical or insignificant") would be a false statement about a real defect;
- **not declinable** — the decline path is for findings that are *wrong*, and this one is right.

The loop has no honest move. In practice an agent will improvise, and the two available
improvisations are both bad: fabricate a blast-radius criterion (which Rule 3 explicitly
forbids — "never cite a criterion that is not true just to have one to cite"), or drop it as
"theoretical" (which launders a real defect, the exact failure Rule 1's two-ground split exists
to prevent).

This is not hypothetical — step 2 routinely fixes pre-existing comments before round 1, so
chains that start at round 0 are the common case, not the exotic one.

## Why it happened, and the design tension to resolve

Two fixes made during PR #18 composed into a hole neither had alone:

- Round 1 (`bcc153d`) scoped Rule 1's new second ground to **non-blocking** findings, correctly
  — dropping a known *blocking* defect is not a trade this design should make.
- Round 5 (`240f8c6`) pointed Rule 2's uncitable case at that ground.

Neither edit was wrong in isolation. Their composition inherited the round-3 precondition into a
rule that is indexed by **depth**, not by round.

**The tension to settle:** Rule 1 is round-indexed (a *time* bound on absorbing) and Rule 2 is
depth-indexed (a *structural* bound on repairing). They currently share a disposition vocabulary
without sharing an index. Any fix has to decide whether the second `drop` ground belongs to
Rule 1 (and so carries its round-3 precondition wherever it is cited) or is a general-purpose
ground both rules may reach.

Two candidate directions, both defensible — pick deliberately rather than by convenience:

1. **Detach the ground from the round.** Restate it as a standalone disposition available to any
   rule that cuts work from the PR — "real, but the controls judged it not worth another round"
   — with Rule 1 and Rule 2 as its two callers. Simplest, and matches how it is already used.
   Risk: it weakens the ratchet's round-3 discipline if a round-1 finding can reach it.
2. **Give Rule 2 its own ground**, parallel to the "induced cap itself" ground already used for
   blocking depth-2 findings, so a non-blocking depth-2 finding at any round is dropped or filed
   citing the cap rather than the ratchet. Keeps the two rules' indices independent. Risk: two
   near-identical grounds that a reader must distinguish.

Recommendation: (2), because it preserves the property that Rule 1 never applies before round 3,
which the ratchet's whole cost argument depends on. But (1) is the smaller edit and the choice
is genuinely open — which is why this was filed rather than patched.

## Acceptance criteria

- [ ] A non-blocking finding at `depth ≥ 2` arriving at **round 1 or 2** has exactly one stated,
      honest disposition, and the text says what it is.
- [ ] Whichever direction is chosen, Rule 1's round-3 precondition and Rule 2's depth index stay
      consistent — no rule inherits the other's index by accident.
- [ ] The fix does not reintroduce a path where a **blocking** finding can be dropped; PR #18's
      round-5 fix (`240f8c6`) established that blocking depth-2 findings are filed citing the
      induced cap and marked `blocking` in `FILED`. That must still hold.
- [ ] Both Rule 2 branches (blocking-root and non-blocking-root) are covered — the
      non-blocking-root branch has the same defect in its depth-2 disposition sentence.
- [ ] `scripts/verify-convergence.sh` gains an assertion pinning the new disposition in both
      plugins.

## How to reproduce the reasoning

Walk the table above against the current text. The three relevant blocks in
`plugins/quick-dev/skills/review-and-merge/SKILL.md`, all inside `### Convergence controls`:

- `**Rule 1 — the severity ratchet.` … and the paragraph beginning
  `**\`drop\` here has a second, distinct ground`
- `**Rule 2 — the induced cap.` … and both `- **Root was ...` bullets

The chain that produced this finding, for reference — it is the loop demonstrating the defect on
itself: finding `3887314559` (round 1, `blocking`, depth 0) → `bcc153d` → finding `3887396496`
(round 5, depth 1) → `240f8c6` → finding `3887414362` (round 6, depth 2, this one).

Note that `bcc153d` is a **batched** commit carrying four findings — the very defect finding
`3887333951` identified and later fixed. So "the ledger entry that sha fixed" is genuinely
ambiguous at that link. It does not change the root severity here (the four were P1/P1/P2/P2,
and the combined-root rule takes the **maximum**, so the root is `blocking` either way), but a
reader re-deriving the chain should know the input was ambiguous even though the answer was
stable.

## Constraints for whoever picks this up

- **Two plugin copies diverge deliberately.** `plugins/quick-dev/skills/review-and-merge/SKILL.md`
  and `plugins/notion-dev/skills/review-and-merge/SKILL.md` are **not** interchangeable.
  **Never `cp` between them.** Apply each edit to each file at its own anchor.
- **`.claude/skills/review-and-merge/` is a verbatim mirror** of the quick-dev copy, enforced by
  `scripts/verify-mirror.sh` in CI. Re-sync with
  `cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/` and keep
  that directory's `README.md`.
- **There is no test framework.** `scripts/verify-*.sh` **are** the test suite, run by
  `.github/workflows/verify.yml`. Write the assertion first, watch it fail, then edit.
- **`grep -qF` is line-scoped.** A literal that wraps across two physical lines can never match —
  this cost three separate corrections during PR #18. Verify each literal sits on one line
  before committing; if it wraps, move the break, never weaken the assertion.
- **Locate edits by anchor text, never by line number.**
- Vocabulary is fixed: triage is exactly `absorb` / `file` / `drop`; severity is exactly
  `blocking` / `non-blocking`.
- Run the full sweep before every commit and require exit 0 — **check the exit status, not the
  printed output.** A loop that echoes `FAIL` but returns 0 let a red commit through during
  PR #18 (`105923d`, corrected in `2c98325`).
