# Review-loop convergence: stop the loop reviewing its own patches

**Date:** 2026-08-29
**Status:** Design approved; implementation plan pending.
**Scope:** `plugins/quick-dev/skills/review-and-merge`, `plugins/notion-dev/skills/review-and-merge`,
`.claude/skills/review-and-merge` (mirror), `scripts/verify-convergence.sh`

## Problem

Clients report that when the review loop applies a fix, the next reviewer round finds defects
*in that fix*, and the loop struggles to converge.

This is measurable, and it was measured. Every bot review round on this repository's own pull
requests — #4, #6, #7, #14, #16 — was correlated against the lines the loop's own fix commits
wrote. Methodology is in the appendix; it is reproducible from the GitHub API and `git`.

**37 reviewer rounds. 69 bot findings.**

| Metric | Value |
|---|---|
| Reviewer rounds on a substantial PR | **10–11** (#4: 10, #6: 10, #7: 11) |
| Rounds that returned zero findings | **0** |
| Findings arriving after round 1 | 56 |
| **Fix-induced** — within ±8 lines of text a prior fix in the same run wrote | **38 / 56 = 68%** |
| Latent — in original-diff code no fix ever touched | 18 / 56 = 32% |
| **Apply rate** — `Agreed and applied` vs. declined | **58 applied / 3 partial / 8 declined = 84%** |
| Severity decay across rounds | **none** — P1 findings still arriving at rounds 9 and 10 |

Two mechanisms produce this, and they need different remedies.

**Mechanism 1 — the loop reviews its own patches (68% of findings).** Every applied fix is
unreviewed code that enters the next round's review surface. PR #6 is the clearest case: twelve
findings across nine rounds, all inside `epic-update/SKILL.md:16–70` — the exact region each
fix rewrote. The measured **induction rate is 0.62 new findings per applied fix**.

That rate is subcritical, so the loop does converge — geometrically, with ratio 0.62. A round-1
batch of nine findings yields roughly 24 downstream findings, which is a ten-round tail. That
is exactly the observed length. **The loop is not diverging; it is converging too slowly to be
usable**, and at Copilot's observed 3–20 minute round-trip that reads to an operator as "it
never finishes."

**Mechanism 2 — the reviewer trickles (32%).** Codex emits one to four findings per call
regardless of how many exist in the diff. PR #7 round 11 flagged
`ticket-system/SKILL.md:419` — code untouched since round 1. Latent findings drip out over ten
round-trips instead of arriving in one, and each round-trip is another chance to induce more.

**The amplifier — the judgment bar is not firing.** `review-and-merge/SKILL.md` §2 states that
"a well-reasoned decline beats a low-confidence edit." The observed decline rate is **12%**, on
findings that are 70% second-tier severity. Near-blind application is what keeps induction fed.

### The finding that settles the design

Splitting findings by the round they arrived in, and by whether the loop caused them:

| | P1 induced | P1 latent | P2 induced | P2 latent |
|---|---|---|---|---|
| Rounds 1–2 | 2 | **5** | 1 | 9 |
| Rounds 3+ | **11** | **1** | 22 | 12 |

**Of the twelve P1 findings that arrived at round 3 or later, eleven were caused by the loop's
own fixes.** Across five pull requests, exactly one genuine high-severity finding surfaced
after round 2. Rounds 3 through 11 are almost entirely the loop cleaning up after itself, and
72% of everything they raise is self-inflicted.

### A claim this refutes

`docs/superpowers/specs/2026-08-28-convergence-design.md` §Problem states that "the
*within-ticket* loops converge" and that "the failure is entirely in *across-ticket* filing."
The first half is wrong. The within-ticket review loop is the same supercritical-branching
argument one level down, and the data above is the counter-evidence. That spec is amended by
this one; its across-ticket analysis stands.

### Corroboration already in the codebase

`quick-dev:develop` local mode (`develop/SKILL.md` Phase 4 step 3) already caps its review at
"at most 2 re-reviews total" and does not exhibit this behaviour. The GitHub-mode loop in
`review-and-merge` is the unbounded one. A bounded review budget is not a new idea in this
codebase; it is an existing one that was never applied to the loop that needed it.

## Approach

Three approaches were considered.

**A — bound the loop** (severity ratchet, induced-finding cap, verify-before-push).
**B — lower the induction rate at source** (minimal-patch rule, visible apply rate).
**C — a hard two-pass budget** (reviewer plus a local exhaustive sweep in round 1, one
confirmation round, merge).

**Chosen: A, with B's minimal-patch rule folded in.** A bounds the loop; B's rule lowers the
0.62 induction rate that makes the tail long in the first place. They attack different terms of
the same product and neither substitutes for the other.

C was rejected as the primary approach: it would have filed the genuine late P1 as follow-up
work, and for this repository — where pull requests are markdown instruction files — filing
prose-consistency items as tickets is worse than fixing them. C's round-1 exhaustion idea
remains a reasonable future option; it is listed under Not in scope.

B alone was rejected because it slows the tail rather than cutting it: at a plausible reduced
induction rate the loop still runs about six rounds, which does not solve the reported problem.

## Design

### 1. The findings ledger

The one new artifact. Per run, held in memory for the duration of the loop, one entry per
finding from any source — existing comments, reviewer rounds, local-reviewer findings,
completeness items:

| field | meaning |
|---|---|
| `id` | GitHub comment id, or a synthetic id for a body-level or local finding |
| `round` | the round it arrived in |
| `path`, `line` | location, against the HEAD the review was submitted on |
| `severity` | normalized: `blocking` or `non-blocking` |
| `disposition` | `applied` / `partial` / `declined` / `absorb` / `file` / `drop` |
| `depth` | induced-chain depth; see §2 |
| `fix_sha` | for applied findings, the commit that fixed it |

**Severity normalizes mechanically.** Codex `P0` and `P1`, and local-reviewer `Critical` and
`Required`, are `blocking`. Codex `P2` and below, and local-reviewer `Optional`, `Nit`, and
`FYI`, are `non-blocking`. Copilot emits no severity label at all — neither on inline comments
nor on `Suppressed comments` entries — so triage assigns one by judging the finding against the
`local-code-review` severity vocabulary, and records that it was judged rather than read.

The ledger is not persisted. It exists to make three rules decidable within a run and to
produce the report block in §7.

### 2. Induced-finding detection

One diff, no per-commit bookkeeping:

```bash
# the lines this loop itself has written, in current-HEAD coordinates
git diff --unified=0 "$R1_SHA"...HEAD
```

where `$R1_SHA` is the **first** reviewer review's own `commit_id` — the sha GitHub records the
review as having been submitted against — captured once, at round 1, and never refreshed. A
finding is **induced** if and only if its `(path, line)` falls inside — or within 5 lines of —
an added hunk of that diff.

Both sides are in current-HEAD coordinates, so line drift is a non-issue and no range table
needs maintaining across commits. This is deliberately simpler than tracking each fix commit's
hunks: a single diff against a single fixed baseline cannot go stale.

**Chain depth** is attributed with `git blame`:

```bash
git blame -L "$LINE","$LINE" --porcelain -- "$PATH"   # -> the commit that wrote that line
```

If that commit is not one of this run's fix commits, the finding is `depth = 0`. Otherwise it
is `depth(ledger entry fixed by that commit) + 1`.

### 3. Rule 1 — the severity ratchet

**From round 3 onward, only a `blocking` finding may be triaged `absorb`.**

An agreed non-blocking finding arriving at round 3 or later becomes `file` — citing a
blast-radius criterion, as `file` items already must — or `drop`, with a rationale. This uses
the existing triage vocabulary, the existing `ABSORBED` / `FILED` / `DROPPED` report lists, and
the existing Absorb gate. No new machinery.

Rounds 1 and 2 are unchanged: absorb-by-default for everything agreed, at any severity.

The ratchet does not weaken the decline path. A finding that is simply wrong is still
**declined** with technical reasoning, exactly as today — declining is not `drop`, and the
distinction in §2 of the skill ("a disagreed finding is already resolved and is not triaged")
is preserved.

**Measured cost:** one genuine latent P1 across five pull requests would become a `FILED` item
rather than an in-PR fix. It is recorded, tracked, and reviewable as its own change — not lost.
That is the entire downside of this rule.

### 4. Rule 2 — the induced cap

**A finding at `depth ≥ 2` is never absorbed.** A `depth = 1` finding — the first defect found
in a fix — is triaged normally, subject to the ratchet: the loop gets exactly one repair
attempt per chain. `depth ≥ 2` means the repair itself drew a finding, and that is where the
chain is cut. As with the ratchet, the decline path is untouched: a depth-2 finding that is
simply wrong is **declined**, not filed.

Two branches, decided by the severity of the chain's root:

- **Root was `non-blocking`** → revert the chain's fixes, and re-triage the *root* finding to
  `file` or `drop` with the chain recorded as its rationale. A cosmetic finding that has now
  cost three patches was not worth the first one.
- **Root was `blocking`** → keep the fixes; the underlying defect was real. `file` the depth-2
  finding, citing blast-radius criterion 3.

This rule, not the ratchet, is what handles the eleven induced P1s: they are `blocking`, so the
ratchet would still absorb them. The two rules are complementary — the ratchet removes the
non-blocking tail, the cap removes the self-inflicted chain at any severity.

### 5. Rule 3 — the minimal-patch rule

**A fix must be the smallest edit that resolves that finding.** Two tests, both checkable
against the diff the fix produces:

1. It touches no file the finding did not name. The one exception is a **stated repository
   invariant** requiring a paired edit — this repo's plugin-and-mirror duplication is the
   example — and the invariant must be *named* in the reply, not assumed.
2. It adds no rule, gate, config key, section, or public interface the finding did not ask for.

A fix failing either test is **not applied**. The finding is re-triaged `file` under
blast-radius criterion 1 (it reaches code this PR was not already changing) or 2 (it needs a
new interface, dependency, config key, or migration).

This is the rule that attacks the 0.62 induction rate at source rather than bounding its
consequences.

### 6. Rule 4 — verify before push

The reviewer loop's commit-and-push step runs the project's verification **before** pushing, and
retains the output as `VERIFY_OUTPUT`. On failure, the fix is corrected or reverted before the
push — never pushed and left for the next round to discover as red CI or as a new finding.

This also closes a stated gap. `review-and-merge/SKILL.md` §"The completeness verifier" records
that `VERIFY_OUTPUT` "is unset far more often than not" precisely because "the reviewer loop
never runs tests at all," forcing the Completeness gate to discover and run the test command
itself. After this rule, a reviewer-loop run that applied any fix arrives at the gate with
verification already in hand.

### 7. Reporting and enforcement

The final report gains a `CONVERGENCE` block, alongside the existing `COMPLETENESS-REPORT`:

```
CONVERGENCE:
ROUNDS: <n>
FINDINGS-TOTAL: <n>
ABSORBED: <n>  DECLINED: <n>  FILED: <n>  DROPPED: <n>
ABSORB-RATE: <pct>
INDUCED: <n> (<pct> of findings after round 1)
INDUCED-CHAINS-CUT: <n>
RATCHET-ENGAGED-AT-ROUND: <n | never>
```

Every key appears on every run; a key with nothing to report takes `0` or `never`, never
absence. This exists because the problem was invisible until it was measured: an `ABSORB-RATE`
near 88% — 61 of the 69 measured findings were acted on — is the signal that the judgment bar is
not firing, and a 68% induced rate was likewise discoverable only by correlating the API against
`git`, appearing nowhere in a run's own output. The four disposition counts partition the ledger
exhaustively because the Absorb gate forbids an outstanding `absorb` at merge, so `absorb` is
transient and never reported.

`scripts/verify-convergence.sh` gains a section asserting each rule is present in both plugins'
copies, in the same style as its existing sections — this repository ships markdown instruction
files, so those greps and diffs are the test suite.

### 8. Placement

Rules 1, 2, and 3 belong in the shared `## 2. Process existing review comments` triage block —
the "Triage is two-axis" section — so that the reviewer loop, the local fallback loop, and the
Completeness gate's triage all inherit them from one statement rather than three copies. Rule 4
belongs in each loop's commit-and-push step. The ledger and the induced-detection commands
belong in a new subsection under `## 4. Review loop`.

Files changed:

- `plugins/quick-dev/skills/review-and-merge/SKILL.md`
- `plugins/notion-dev/skills/review-and-merge/SKILL.md`
- `.claude/skills/review-and-merge/` — re-synced per its README's `cp -r` rule, verified by
  `scripts/verify-mirror.sh`
- `scripts/verify-convergence.sh` — new assertions
- `plugins/quick-dev/.claude-plugin/plugin.json`, `plugins/notion-dev/.claude-plugin/plugin.json` —
  version bumps (from `0.9.0` and `0.14.0`)
- `docs/superpowers/specs/2026-08-28-convergence-design.md` — correct the "within-ticket loops
  converge" claim, pointing at this document

`quick-dev:develop` needs no change. Its local mode is already bounded at two re-reviews, and
its GitHub mode delegates entirely to `review-and-merge`.

## Why this terminates

From round 3 onward, absorbable work is restricted to `blocking` findings. A blocking finding is
either **latent** — drawn from the finite, non-replenishing set of defects in the original diff,
empirically about one after round 2 — or **induced**, and every induced chain dies at depth 2 by
Rule 2. The absorbable set is therefore finite and strictly decreasing.

Once a round absorbs nothing, the loop's existing terminator fires unchanged: "do not re-trigger
when nothing changed." No new stopping condition is introduced, and `reviewsCap` returns to
being a runaway backstop rather than the operative stop — which is what its own documentation
already claims it is.

Aggregate effect on the measured data: of the 46 findings that arrived at round 3 or later, 34
are non-blocking and would have been filed or dropped rather than absorbed; of the remaining 12
blocking findings, 11 were induced and would have met the depth-2 cap, leaving one genuine
latent defect to absorb. A precise per-PR round-count replay is not
possible from the data, because round *N*'s findings depend on round *N−1*'s fixes and those
fixes would not have been made.

## Risks

- **A genuine late defect gets filed instead of fixed.** Measured at one occurrence across five
  pull requests. It becomes a tracked `FILED` item with a blast-radius criterion, not a silent
  omission — the same trade the 2026-08-28 spec already accepted for across-ticket work.
- **Severity judgment for Copilot findings is a judgment call**, because Copilot emits no
  severity. A triage that systematically over-rates findings as `blocking` weakens the ratchet.
  The `CONVERGENCE` block's absorb rate is the detector: a run whose rate stays near 88% is
  mis-rating.
- **`git blame` attribution can be wrong** when a fix rewrote a line another fix had already
  rewritten. The failure mode is a depth that is too low, which under-triggers the cap — it
  never falsely reverts work.
- **The minimal-patch rule can be over-applied**, converting reasonable fixes into filed
  tickets. `INDUCED-CHAINS-CUT` and the `FILED` count in the report are the signal; a run filing
  most of its findings is mis-calibrated in the other direction.

## Verification

This repository ships markdown, so verification is structural, per the existing convention in
`scripts/verify-convergence.sh`:

1. Each rule's defining sentence is present in both plugins' `review-and-merge/SKILL.md`.
2. The two `SKILL.md` copies stay in their existing intended relationship, and the `.claude`
   mirror is byte-identical to `plugins/quick-dev`'s copy — `scripts/verify-mirror.sh`.
3. The `CONVERGENCE` block's keys are all named in the skill.
4. Both plugin versions are strictly above their pre-change values.
5. `2026-08-28-convergence-design.md` no longer asserts the within-ticket loops converge.

The behavioural check is the next substantial pull request driven through the loop: its
`CONVERGENCE` block should report rounds in the low single digits, an apply rate well below 84%,
and a non-zero `RATCHET-ENGAGED-AT-ROUND` only when it genuinely ran past round 2.

## Not in scope

- **Round-1 exhaustion** (approach C's sweep — running a local exhaustive review alongside the
  first reviewer round to drain the 32% latent trickle in one round instead of ten). It costs an
  extra agent per run and is orthogonal to the rules here; it can be added later if the
  `CONVERGENCE` block shows latent trickle still dominating after these changes land.
- **Changing what the reviewers emit.** Codex's per-call finding limit and Copilot's
  suppressed-comments behaviour are not ours to alter.
- **The across-ticket filing analysis** in the 2026-08-28 spec, which stands unchanged.
- **`quick-dev:develop`'s local mode loop**, already bounded.

## Appendix: measurement methodology

Reproducible against any repository whose pull requests ran this loop.

1. For each pull request, fetch with `gh api --paginate --slurp`: `pulls/<n>/reviews`,
   `pulls/<n>/comments`, `issues/<n>/comments`, `pulls/<n>/commits`.
2. Keep reviews authored by `chatgpt-codex-connector[bot]`,
   `copilot-pull-request-reviewer[bot]`, or `Copilot`; order by `submitted_at`. Each is one
   round.
3. Attribute inline comments to a round by `pull_request_review_id`, never by author or
   timestamp — the skill's own rule, and it is load-bearing here too.
4. For round *N* > 1, take every commit dated between round 1's `submitted_at` and round *N*'s,
   and collect the added-line ranges from `git show --unified=0 --format= <sha>` by parsing
   `@@ … +start,count @@` under each `+++ b/<path>`.
5. A finding is **induced** if its `(path, line)` is within ±8 lines of any collected range,
   and **latent** otherwise. (The design in §2 uses a single baseline diff and ±5 lines; the
   analysis used per-commit ranges and ±8 because it had to tolerate line drift across ten
   rounds of history. The design does not, since it recomputes against current HEAD.)
6. Severity comes from the `badge/P<n>` image URL in codex finding bodies; Copilot findings
   carry none.
7. Disposition comes from the reply comments threaded under each finding
   (`in_reply_to_id`), matched against the skill's own mandated reply wordings — `Agreed and
   applied`, partial-agreement phrasing, or anything else.
