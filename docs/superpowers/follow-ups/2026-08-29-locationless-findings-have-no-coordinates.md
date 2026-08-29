# Follow-up: a finding with no location has no `induced` status and no `depth`

**Filed:** 2026-08-29, from the review loop on PR #18 (`d1c9383`).
**Source finding:** codex `3887355900`, round 3, severity **P2 → `non-blocking`**.
**Why filed rather than fixed:** Rule 1's severity ratchet. It arrived at round 3, and from
round 3 onward only a `blocking` finding may be triaged `absorb`. Re-grading it upward to keep
absorbing is the one move the skill names as defeating Rule 1, so it was filed instead.
**Blast-radius criterion cited:** **3** — it needs a design decision the run's acceptance
criteria do not settle.

---

## The problem

`review-and-merge`'s convergence controls classify every finding on two derived properties:

- **`induced`** — does the finding point at code this run's own fixes wrote?
- **`depth`** — how many repair attempts deep into a chain is it?

Both are computed from a `(path, line)` pair and a commit sha. Current text, in
`plugins/quick-dev/skills/review-and-merge/SKILL.md` under `**Induced findings.**`:

```bash
R1_SHA=$(git rev-parse HEAD)   # captured at the start of the run, before ## 2 pushes anything
git diff --unified=0 "$R1_SHA".."$REVIEW_SHA"
```

> A finding is `induced` **iff** its `(path, line)` falls inside — or within 5 lines of — an
> added hunk … of that diff.

and under `**Chain depth**`:

```bash
git blame -L "<line>,<line>" --porcelain "$REVIEW_SHA" -- "<path>"
```

**Some findings have neither input.** The same skill explicitly routes these through the same
rules:

1. **Copilot body-only findings.** The reviewer profile states Copilot "frequently generates
   zero inline comments, withholding low-confidence findings into a
   `<details><summary>Suppressed comments (N)</summary>` block in the body instead, so the body
   is a first-class finding source." Those entries carry a `**<path>:<line>**` header in prose,
   but they are not inline comments and have no review-attached position.
2. **Human PR-level comments arriving mid-loop.** `## 4` says these are "handled per step-2
   rules". A human comment has no `(path, line)` at all, and belongs to no review object, so
   `$REVIEW_SHA` is undefined for it.
3. **Completeness-gate items.** Exempt from Rule 1 by an explicit carve-out, but Rules 2, 3 and
   4 still reach them, and a `not-met` criterion has no location either.

For all three, `$REVIEW_SHA` is undefined, the diff cannot be computed, and `git blame -L`
has no line to blame. So `induced` and `depth` are undecidable, which means:

- **Rule 2 cannot fire on them.** A chain rooted in a locationless finding is invisible to the
  induced cap, so the loop can repair it indefinitely — exactly the runaway the cap exists to
  stop.
- **The `CONVERGENCE` block's `INDUCED` count silently excludes them**, understating the metric
  that the whole design is calibrated against.

## The design decision this needs (why it is criterion 3, not a wording fix)

The obvious half of the answer is easy: a finding with no location is `depth = 0` and never
`induced`. The part that is genuinely unsettled is **whether such a finding can be a chain
root**, and what happens to its descendants.

Concretely: a human comments "add tests". The loop writes a new test file. Round N+1 finds a
defect *in that new file*. That defect:

- **is** `induced` by the mechanical test — the lines are in `R1_SHA..$REVIEW_SHA`;
- blames to a fix commit whose ledger entry is the locationless human finding;
- therefore takes `depth = depth(root) + 1 = 1`;
- and Rule 2's branch selection depends on the **root's severity** — which for a human finding
  is *judged*, not read, under the "anything that carries no severity label gets a judged one"
  rule.

So a locationless finding can be a chain root even though it can never be a chain *descendant*.
That asymmetry needs stating deliberately rather than falling out of an implementation. Decide
and document at least:

1. Is `depth = 0` / `induced = false` correct for a locationless finding, or should it be a
   distinct third state (`unlocatable`) so the `CONVERGENCE` block can report it rather than
   silently folding it into "not induced"?
2. May a locationless finding be a chain **root**? (Recommendation: yes — its *fix* has a
   location even though it does not.)
3. When it is a root, what `$REVIEW_SHA` do its descendants use? (Its fix commit's sha is the
   natural answer, but say so.)
4. Does the `**<path>:<line>**` header inside a Copilot `Suppressed comments` entry count as a
   location? It is parseable prose, not API-supplied position, and it is relative to the
   review's commit. Deciding "yes, parse it" would recover induced/depth for the single largest
   class of locationless findings.

## Acceptance criteria

- [ ] The `### Convergence controls` section states what `induced` and `depth` are for a finding
      carrying no `(path, line)`, and for a finding belonging to no review object.
- [ ] The four questions above are each answered in the text, not left implicit.
- [ ] Rule 2's chain-root handling covers the locationless-root case explicitly.
- [ ] The `CONVERGENCE` block's `INDUCED` line either counts these or discloses that it cannot,
      per the block's own "never absence" rule.
- [ ] `scripts/verify-convergence.sh` gains an assertion pinning the new rule in both plugins.

## Constraints for whoever picks this up

- **Two plugin copies diverge deliberately.** `plugins/quick-dev/skills/review-and-merge/SKILL.md`
  and `plugins/notion-dev/skills/review-and-merge/SKILL.md` are **not** interchangeable — they
  differ on reviewer config, merge strategy, and verification mechanism (`verify.steps` vs
  discovery). **Never `cp` between them.** Apply each edit to each file at its own anchor.
- **`.claude/skills/review-and-merge/` is a verbatim mirror** of the quick-dev copy, enforced by
  `scripts/verify-mirror.sh` in CI. Re-sync with
  `cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/` and keep
  that directory's `README.md`, which has no plugin counterpart.
- **There is no test framework.** `scripts/verify-*.sh` **are** the test suite, run by
  `.github/workflows/verify.yml`. Write the assertion first, watch it fail, then edit.
- **`grep -qF` is line-scoped.** An assertion literal that wraps across two physical lines can
  never match. This bit three separate times during PR #18. Check every literal lands on one
  line before committing; if it wraps, move the line break — never weaken the assertion.
- **Locate edits by anchor text, never by line number.** Line numbers in this document will go
  stale; the quoted anchors will not.
- Vocabulary is fixed: triage is exactly `absorb` / `file` / `drop`; severity is exactly
  `blocking` / `non-blocking`. Do not invent synonyms — the harness asserts against them.

## Adjacent cleanup, if you are already in this paragraph

The `**Induced findings.**` block accumulated a redundant tail across PR #18's rounds. It now
reads, in sequence: "No per-commit range table is needed either. Do not substitute a per-commit
walk: a single diff against a single fixed baseline cannot go stale, and one rebuilt each round
can." The second sentence restates the first and refers to a "fixed baseline" phrasing that the
`$REVIEW_SHA` change superseded. Worth tightening while you are editing the same paragraph —
but it is cosmetic, so it does not justify its own change.
