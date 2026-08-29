# Review-Loop Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `review-and-merge`'s reviewer loop from spending eight extra rounds reviewing its own patches, by bounding what it may absorb after round 2 and cutting self-inflicted fix chains at depth 2.

**Architecture:** All changes are prose in two `review-and-merge/SKILL.md` copies plus a byte-identical mirror. A new **Convergence controls** subsection lands in `## 2. Process existing review comments` — the shared triage block both review loops and the Completeness gate already inherit from — carrying a findings ledger, induced-finding detection, and four rules. A `CONVERGENCE` block is added to the final report. `scripts/verify-convergence.sh` gains a matching section.

**Tech Stack:** Markdown instruction files; `bash` + `grep`/`diff` harnesses in `scripts/`; `gh` CLI and `git` in the documented procedures. There is no package manager and no test framework — `scripts/verify-*.sh` **are** the test suite, discovered and run by `.github/workflows/verify.yml`.

**Spec:** `docs/superpowers/specs/2026-08-29-review-loop-convergence-design.md`

## Global Constraints

- **The two plugin copies are not interchangeable.** `plugins/quick-dev/skills/review-and-merge/SKILL.md` (559 lines) and `plugins/notion-dev/skills/review-and-merge/SKILL.md` (579 lines) diverge deliberately — reviewer config, merge strategy, `verify.steps` vs. discovery. **Never `cp` between plugins.** Every edit is applied to each file separately, at that file's own anchor.
- **`.claude/skills/review-and-merge/` is a verbatim mirror of the quick-dev copy** and must be re-synced in the same commit: `cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/` then `./scripts/verify-mirror.sh`. Keep `.claude/skills/review-and-merge/README.md`, which has no plugin counterpart.
- **Triage vocabulary is fixed at exactly `absorb` / `file` / `drop`.** `scripts/verify-convergence.sh` already asserts no copy invents a synonym (`fold in`, `inline it`). Do not introduce one.
- **Severity vocabulary is fixed at exactly `blocking` / `non-blocking`** for the normalized axis, and `Critical` / `Required` / `Optional` / `Nit` / `FYI` for `local-code-review`'s own labels. Do not invent a third spelling.
- **Pre-change versions:** `plugins/quick-dev/.claude-plugin/plugin.json` is `0.9.0`; `plugins/notion-dev/.claude-plugin/plugin.json` is `0.14.0`. Both must end strictly above those.
- **Run `./scripts/verify-convergence.sh` and `./scripts/verify-mirror.sh` before every commit.** Both must print `ALL CHECKS PASSED` / exit 0.
- **Deliberate deviation from spec §8.** The spec places the ledger and induced-detection commands "under `## 4. Review loop`" and the rules in `## 2`. This plan puts **all** of it in the `## 2` triage block, as one `### Convergence controls` subsection. Rule 2 depends on chain depth, so splitting them would force `## 2` to forward-reference `## 4`, and the spec's own stated intent is "one statement rather than three copies." Same content, one home.
- **Harness structure.** Task 1 creates the `== review-loop convergence ==` section as a `for P in "$ND" "$QD"; do … done` loop. Every later task appends its shared assertions **immediately before that `done`**; plugin-specific assertions go **after** it. Never reopen or re-close the loop.
- Every `git commit` message ends with the line `Claude-Session: https://claude.ai/code/session_0165fEU2CPd9nwq2NsSGTTQN`.

---

### Task 1: Convergence controls scaffold — ledger, severity normalization, induced detection

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md` (insert after line 103, the paragraph ending `and the round cap is the backstop.`)
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md` (insert after line 118, the same paragraph)
- Modify: `.claude/skills/review-and-merge/SKILL.md` (via mirror sync)
- Test: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: the `### Convergence controls` heading and the terms every later task anchors on — `The findings ledger`, the `blocking` / `non-blocking` severity axis, `$R1_SHA`, `induced`, and `depth`. Tasks 2–4 append their rules **inside this subsection, in order, after the chain-depth paragraph**. Task 6 reads the ledger fields to build the report block.

- [ ] **Step 1: Write the failing assertions**

Append this section to `scripts/verify-convergence.sh`, immediately **before** the final `echo` / `if [ "$fails" -eq 0 ]` summary block:

```bash
echo "== review-loop convergence =="
for P in "$ND" "$QD"; do
  S=$P/skills/review-and-merge/SKILL.md
  n=$(basename "$P")
  assert_has "$n r&m has the convergence controls" "$S" '### Convergence controls'
  assert_has "$n r&m has the findings ledger"      "$S" '**The findings ledger.**'
  assert_has "$n r&m normalizes severity"          "$S" 'normalizes mechanically'
  assert_has "$n r&m names both severity values"   "$S" '`non-blocking`'
  assert_has "$n r&m pins the induced baseline"    "$S" 'R1_SHA'
  assert_has "$n r&m defines chain depth"          "$S" 'git blame -L'
done
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: the new `== review-loop convergence ==` section prints `FAIL` for all 12 checks (6 per plugin), and the script exits non-zero with `12 CHECK(S) FAILED`.

- [ ] **Step 3: Insert the subsection into the quick-dev copy**

In `plugins/quick-dev/skills/review-and-merge/SKILL.md`, insert the following **immediately after** line 103 (`round-capped loop, and the round cap is the backstop.`) and **before** line 105 (`For **each unresolved** thread …`), separated by a blank line on each side:

````markdown
### Convergence controls

Measured across 37 reviewer rounds on this plugin's own pull requests: **68% of every finding
raised after round 1 landed inside lines the loop's own fixes had just written**, the apply rate
was 84%, and 11 of the 12 highest-severity findings arriving at round 3 or later were caused by
the loop itself. Rounds 3 onward were almost entirely the loop cleaning up after its own
patches. The controls below exist to stop that, and they bind **every** finding from every
source — existing comments here, reviewer rounds, local-reviewer findings, and the Completeness
gate's items. The measurement is in
`docs/superpowers/specs/2026-08-29-review-loop-convergence-design.md`.

**The findings ledger.** Keep one in-memory record per finding for the life of the run. It is
never written to disk and never committed; it exists to make the rules below decidable and to
produce the `CONVERGENCE` block in the final report.

| field | value |
|---|---|
| `id` | the GitHub comment id; for a body-level or local-reviewer finding, any stable synthetic id |
| `round` | the round it arrived in — `0` for comments that predate the first trigger |
| `path`, `line` | its location, as the review reported it |
| `severity` | **normalized** to `blocking` or `non-blocking` — see below |
| `disposition` | `applied` / `partial` / `declined` / `absorb` / `file` / `drop` |
| `depth` | induced-chain depth — see below |
| `fix_sha` | for an applied finding, the commit that fixed it |

**Severity normalizes mechanically.** Codex `P0` and `P1` — read from the `badge/P<n>` image URL
in the finding body — and local-reviewer `Critical` and `Required` are **`blocking`**. Codex
`P2` and below, and local-reviewer `Optional`, `Nit`, and `FYI`, are **`non-blocking`**.
**Copilot emits no severity at all** — not on inline comments, not on `Suppressed comments`
entries — so assign one by judging the finding against the `quick-dev:local-code-review`
severity vocabulary, and record in the ledger that it was judged rather than read. Over-rating
Copilot findings as `blocking` is the one way to defeat Rule 1, and the report's apply rate is
what makes that visible.

**Induced findings.** A finding is **induced** when it points at code this run's own fixes
wrote. Capture the baseline **once**, at the first reviewer response of the run — that review's
own `commit_id`, the sha GitHub records it as submitted against — and never refresh it:

```bash
R1_SHA=$(gh api "repos/{owner}/{repo}/pulls/<pr>/reviews/<first-review-id>" | jq -r .commit_id)
# the lines this loop itself has written, in current-HEAD coordinates
git diff --unified=0 "$R1_SHA"...HEAD
```

A finding is `induced` **iff** its `(path, line)` falls inside — or within 5 lines of — an added
hunk (`@@ … +start,count @@` under a `+++ b/<path>`) of that diff. Both sides are in
current-HEAD coordinates, so line drift needs no correction and no per-commit range table needs
maintaining. Do not substitute a per-commit walk: a single diff against a single fixed baseline
cannot go stale, and one rebuilt each round can.

**Chain depth** attributes an induced finding to the fix that caused it:

```bash
git blame -L "<line>,<line>" --porcelain -- "<path>" | head -1   # -> the sha that wrote it
```

If that sha is **not** one of this run's fix commits, the finding is `depth = 0`. Otherwise it is
the `depth` of the ledger entry that sha fixed, **plus 1**. Blame under-counts when one fix
rewrote a line an earlier fix had already rewritten; that failure mode yields a depth that is
too low, which under-triggers Rule 2 and never falsely reverts work.
````

- [ ] **Step 4: Insert the same subsection into the notion-dev copy**

In `plugins/notion-dev/skills/review-and-merge/SKILL.md`, insert the **identical block from Step 3** immediately after line 118 (`round-capped loop, and the round cap is the backstop.`) and before line 120 (`For **each unresolved** thread …`), with one change: the skill reference reads `notion-dev:local-code-review`, not `quick-dev:local-code-review`.

- [ ] **Step 5: Re-sync the mirror**

```bash
cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/
./scripts/verify-mirror.sh
```

Expected: exit 0.

- [ ] **Step 6: Run the harness to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`, exit 0 — the 12 new checks now `PASS` alongside every pre-existing one.

- [ ] **Step 7: Commit**

```bash
git add plugins/quick-dev/skills/review-and-merge/SKILL.md \
        plugins/notion-dev/skills/review-and-merge/SKILL.md \
        .claude/skills/review-and-merge/SKILL.md \
        scripts/verify-convergence.sh
git commit -m "feat(review-and-merge): findings ledger and induced-finding detection

Adds the Convergence controls subsection: a per-run findings ledger,
mechanical severity normalization to blocking/non-blocking, an
induced-finding test against a baseline pinned at the first review's
commit_id, and git-blame chain depth. No rule consumes these yet.

Claude-Session: https://claude.ai/code/session_0165fEU2CPd9nwq2NsSGTTQN"
```

---

### Task 2: Rule 1 — the severity ratchet

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md` (rewrite lines 101–103; append Rule 1 to the Convergence controls subsection)
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md` (same, at lines 116–118)
- Modify: `.claude/skills/review-and-merge/SKILL.md` (via mirror sync)
- Test: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: `blocking` / `non-blocking` severity from Task 1.
- Produces: the phrase `From round 3 onward` and the requirement that the run record *the round the ratchet first changed an outcome* — Task 6's `RATCHET-ENGAGED-AT-ROUND` key reads exactly that value.

- [ ] **Step 1: Write the failing assertions**

In `scripts/verify-convergence.sh`, inside the `for P in "$ND" "$QD"` loop of the `== review-loop convergence ==` section added in Task 1, append after the `git blame -L` line:

```bash
  assert_has   "$n r&m has the severity ratchet"     "$S" 'From round 3 onward, only a `blocking` finding may be triaged'
  assert_has   "$n r&m keeps the decline path"       "$S" 'a decline is not a `drop`'
  assert_lacks "$n r&m drops the stale runaway claim" "$S" 'That is why this cannot run away'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: 6 new `FAIL` lines (3 per plugin); exit non-zero.

- [ ] **Step 3: Replace the stale paragraph in both copies**

The current claim is refuted by the measurement — the loop ran ten and eleven rounds. In **both** `plugins/quick-dev/skills/review-and-merge/SKILL.md` (lines 101–103) and `plugins/notion-dev/skills/review-and-merge/SKILL.md` (lines 116–118), replace:

```markdown
Absorbing does not skip review: the absorbed change is pushed like any other fix and the next
round reviews it. That is why this cannot run away — absorbed work re-enters the existing
round-capped loop, and the round cap is the backstop.
```

with:

```markdown
Absorbing does not skip review: the absorbed change is pushed like any other fix and the next
round reviews it. That re-entry is also what makes absorption expensive — the absorbed change is
new unreviewed surface, and it draws findings of its own. **The round cap alone does not keep
this bounded**; measurement showed the loop running ten and eleven rounds against it. The
**Convergence controls** below are what bound it, and the round cap goes back to being the
runaway backstop it is documented as.
```

- [ ] **Step 4: Append Rule 1 to the Convergence controls subsection in both copies**

Add at the end of the `### Convergence controls` subsection — after the chain-depth paragraph, in both files, identically:

```markdown
**Rule 1 — the severity ratchet. From round 3 onward, only a `blocking` finding may be triaged
`absorb`.**

An agreed **non-blocking** finding arriving at round 3 or later becomes `file` — citing a
blast-radius criterion, as every `file` item must — or `drop`, with its rationale. Rounds 1 and
2 are unchanged: absorb-by-default at any severity. **Record the round at which the ratchet
first changed an outcome**; the final report names it.

The ratchet governs only *where agreed work goes*. It does **not** touch the agree / partially
agree / disagree axis: a finding that is simply wrong is still **declined** with a technical
reason, and a decline is not a `drop`.

Measured cost of this rule across five pull requests: exactly one genuine latent `blocking`
finding would have become a `FILED` item instead of an in-PR fix — tracked, cited, and
reviewable as its own change, not lost. Rounds 3 and later otherwise contributed 34
`non-blocking` findings and 11 self-inflicted `blocking` ones.
```

- [ ] **Step 5: Re-sync the mirror**

```bash
cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/
./scripts/verify-mirror.sh
```

Expected: exit 0.

- [ ] **Step 6: Run the harness to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`, exit 0.

- [ ] **Step 7: Commit**

```bash
git add plugins/quick-dev/skills/review-and-merge/SKILL.md \
        plugins/notion-dev/skills/review-and-merge/SKILL.md \
        .claude/skills/review-and-merge/SKILL.md \
        scripts/verify-convergence.sh
git commit -m "feat(review-and-merge): severity ratchet from round 3

From round 3 onward only blocking findings may be absorbed; agreed
non-blocking findings are filed or dropped with rationale. Also
retires the 'this cannot run away' claim, which the measurement of
ten- and eleven-round loops refutes.

Claude-Session: https://claude.ai/code/session_0165fEU2CPd9nwq2NsSGTTQN"
```

---

### Task 3: Rule 2 — the induced cap

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md` (append to Convergence controls, after Rule 1)
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md` (same)
- Modify: `.claude/skills/review-and-merge/SKILL.md` (via mirror sync)
- Test: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: `depth` and the `blocking` / `non-blocking` axis from Task 1; the decline-path carve-out from Task 2.
- Produces: the notion of a **cut chain**, which Task 6's `INDUCED-CHAINS-CUT` key counts — one per chain this rule stopped, whichever branch it took.

- [ ] **Step 1: Write the failing assertions**

In `scripts/verify-convergence.sh`, inside the same `for P in "$ND" "$QD"` loop, append after the Rule 1 assertions:

```bash
  assert_has "$n r&m has the induced cap"        "$S" 'A finding at `depth ≥ 2` is never absorbed'
  assert_has "$n r&m reverts non-blocking roots" "$S" 'revert the chain'
  assert_has "$n r&m keeps blocking-root fixes"  "$S" 'keep the fixes'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: 6 new `FAIL` lines; exit non-zero.

- [ ] **Step 3: Append Rule 2 to both copies**

Add at the end of the `### Convergence controls` subsection, after Rule 1, in both files, identically:

```markdown
**Rule 2 — the induced cap. A finding at `depth ≥ 2` is never absorbed.**

A `depth = 1` finding — the first defect found in a fix — is triaged normally, subject to Rule
1. The loop gets exactly **one** repair attempt per chain. `depth ≥ 2` means the repair itself
drew a finding, and that is where the chain is cut. Which branch applies is decided by the
severity of the chain's **root** — the `depth = 0` entry it descends from, not the finding in
hand:

- **Root was `non-blocking`** → **revert the chain's fixes** (`git revert` those fix commits, or
  restore the pre-fix text), then re-triage the **root** finding to `file` or `drop` with the
  chain recorded as its rationale. A cosmetic finding that has now cost three patches was not
  worth the first one.
- **Root was `blocking`** → **keep the fixes**; the underlying defect was real and reverting
  would reintroduce it. `file` the depth-2 finding, citing blast-radius criterion 3.

Either branch **cuts one chain** — count it for the report. As with Rule 1, the decline path is
untouched: a depth-2 finding that is wrong is **declined**, not filed.

This rule, not Rule 1, is what handles self-inflicted **`blocking`** findings — the ratchet
would still absorb those, and 11 of the 12 late high-severity findings in the measurement were
exactly this. The two rules are complementary: Rule 1 removes the non-blocking tail, Rule 2
removes the self-inflicted chain at any severity.
```

- [ ] **Step 4: Re-sync the mirror**

```bash
cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/
./scripts/verify-mirror.sh
```

Expected: exit 0.

- [ ] **Step 5: Run the harness to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`, exit 0.

- [ ] **Step 6: Commit**

```bash
git add plugins/quick-dev/skills/review-and-merge/SKILL.md \
        plugins/notion-dev/skills/review-and-merge/SKILL.md \
        .claude/skills/review-and-merge/SKILL.md \
        scripts/verify-convergence.sh
git commit -m "feat(review-and-merge): cut induced fix chains at depth 2

A finding whose location was written by a fix for a finding that was
itself induced is never absorbed. Non-blocking roots get their chain
reverted and the root re-triaged; blocking roots keep their fixes and
file the depth-2 finding.

Claude-Session: https://claude.ai/code/session_0165fEU2CPd9nwq2NsSGTTQN"
```

---

### Task 4: Rule 3 — the minimal patch

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md` (append to Convergence controls, after Rule 2)
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md` (same)
- Modify: `.claude/skills/review-and-merge/SKILL.md` (via mirror sync)
- Test: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: the existing blast-radius criteria 1 and 2 from the triage block directly above.
- Produces: no new named value. Its effect reaches the report only through the existing `FILED` list.

- [ ] **Step 1: Write the failing assertions**

In `scripts/verify-convergence.sh`, inside the same loop, append after the Rule 2 assertions:

```bash
  assert_has "$n r&m has the minimal-patch rule" "$S" 'smallest edit that resolves that finding'
  assert_has "$n r&m bounds the fix by file"     "$S" 'touches no file the finding did not name'
  assert_has "$n r&m names the paired-edit case" "$S" 'stated repository invariant'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: 6 new `FAIL` lines; exit non-zero.

- [ ] **Step 3: Append Rule 3 to both copies**

Add at the end of the `### Convergence controls` subsection, after Rule 2, in both files, identically:

```markdown
**Rule 3 — the minimal patch. A fix must be the smallest edit that resolves that finding.**

Two tests, both checkable against the diff the fix produces:

1. It **touches no file the finding did not name**. The one exception is a **stated repository
   invariant** requiring a paired edit — a mirrored or duplicated copy that must move together —
   and that invariant must be *named* in the reply, never assumed.
2. It **adds no rule, gate, config key, section, or public interface** the finding did not ask
   for.

A fix that fails either test is **not applied**. Re-triage the finding to `file` under
blast-radius criterion 1 (it reaches code this PR was not already changing) or 2 (it needs a new
public interface, dependency, config key, or data migration), and say so in the reply.

This is the one rule that lowers the *rate* at which fixes create findings rather than bounding
the consequences afterwards. The measured rate was **0.62 new findings per applied fix**; a fix
that ranges beyond its finding is how that number gets paid.
```

- [ ] **Step 4: Re-sync the mirror**

```bash
cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/
./scripts/verify-mirror.sh
```

Expected: exit 0.

- [ ] **Step 5: Run the harness to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`, exit 0.

- [ ] **Step 6: Commit**

```bash
git add plugins/quick-dev/skills/review-and-merge/SKILL.md \
        plugins/notion-dev/skills/review-and-merge/SKILL.md \
        .claude/skills/review-and-merge/SKILL.md \
        scripts/verify-convergence.sh
git commit -m "feat(review-and-merge): minimal-patch rule for review fixes

A fix may not touch a file the finding did not name, nor add a rule,
gate, key, section, or interface it did not ask for; one that would is
re-triaged to file. Attacks the 0.62 findings-per-fix induction rate at
source.

Claude-Session: https://claude.ai/code/session_0165fEU2CPd9nwq2NsSGTTQN"
```

---

### Task 5: Rule 4 — verify before push

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md` — append Rule 4 to Convergence controls; rewrite the push instruction at line 117; rewrite `## 4` response-handling item 4 at line 342; correct the stale `VERIFY_OUTPUT` claim at line 398
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md` — append Rule 4 to Convergence controls only
- Modify: `.claude/skills/review-and-merge/SKILL.md` (via mirror sync)
- Test: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: nothing from Tasks 1–4.
- Produces: `VERIFY_OUTPUT` written at every reviewer-loop push site in quick-dev, which the Completeness gate already reads.

**This task is deliberately asymmetric.** `notion-dev` **already** verifies before every push — at its `## 2` push (line 132), at `## 4` item 4 (line 358), and in the local loop (line 397) — driven by the `verify.steps` config key. `quick-dev` verifies **only** in the local loop (line 381), and its own line 398 states the gap outright: *"the reviewer loop never runs tests at all."* So notion-dev gains the rule's statement; quick-dev gains the statement **and** the two missing sites.

- [ ] **Step 1: Write the failing assertions**

Two edits to `scripts/verify-convergence.sh`. First, the shared assertion — **inside** the loop, appended after the Rule 3 assertions:

```bash
  assert_has "$n r&m has verify-before-push" "$S" 'Rule 4 — verify before push'
```

Second, the two quick-dev-only assertions — **after** the loop's `done`, so they run once rather than per plugin:

```bash
assert_has   "quick-dev r&m verifies at the step-2 push" \
  "$QD/skills/review-and-merge/SKILL.md" "run Rule 4's verification first"
assert_lacks "quick-dev r&m drops the stale never-runs-tests claim" \
  "$QD/skills/review-and-merge/SKILL.md" 'the reviewer loop never runs tests at all'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: 4 new `FAIL` lines (2 shared + 2 quick-dev-only); exit non-zero.

- [ ] **Step 3: Append Rule 4 to the quick-dev copy**

Add at the end of the `### Convergence controls` subsection, after Rule 3:

```markdown
**Rule 4 — verify before push. Never push a review fix that has not passed the project's
verification.**

Discover the project's test/build command — the same discovery the Completeness gate performs —
and run it before **every** push of review fixes, at `## 2` and in both loops. Retain the output
as `VERIFY_OUTPUT`, overwriting any earlier value. If it fails, correct or revert the fix
**before** pushing.

A broken fix that gets pushed costs a full round-trip — 3–20 minutes with copilot — to learn
something a local run answers in seconds, and it comes back as a *new finding*, which is then
induced surface for Rule 2 to deal with. When the repo has no test or build command to discover,
say so in the final report and leave `VERIFY_OUTPUT` empty.
```

- [ ] **Step 4: Append Rule 4 to the notion-dev copy**

Add at the same position in `plugins/notion-dev/skills/review-and-merge/SKILL.md`, with the mechanism wording this plugin already uses:

```markdown
**Rule 4 — verify before push. Never push a review fix that has not passed the project's
verification.**

Step 2, `## 4` item 4, and the local review loop's step 4 already do this via the config
`verify.steps` key, retaining the output as `VERIFY_OUTPUT`. The rule restates it here as a
**convergence control**, not only as a Completeness-gate input: a broken fix that gets pushed
costs a full round-trip — 3–20 minutes with copilot — to learn something a local run answers in
seconds, and it comes back as a *new finding*, which is then induced surface for Rule 2 to deal
with. When the repo configures no `verify.steps`, say so in the final report and leave
`VERIFY_OUTPUT` empty.
```

- [ ] **Step 5: Add the two missing quick-dev push sites**

In `plugins/quick-dev/skills/review-and-merge/SKILL.md` line 117–118, replace:

```markdown
Never respond twice to the same comment — track handled comment IDs. If code changed, commit and push:
`git add -A && git commit -m "review: address PR feedback" && git push`
```

with:

```markdown
Never respond twice to the same comment — track handled comment IDs. If code changed, **run Rule 4's verification first and retain its output as `VERIFY_OUTPUT`**, then commit and push:
`git add -A && git commit -m "review: address PR feedback" && git push`
```

And at line 342, replace:

```markdown
4. Commit and push applied changes.
```

with:

```markdown
4. **Run Rule 4's verification and retain its output as `VERIFY_OUTPUT`**, then commit and push applied changes. A fix that fails verification is corrected or reverted here, never pushed for the next round to find.
```

- [ ] **Step 6: Correct the now-false claim at quick-dev line 398**

In the `### The completeness verifier` subsection, replace:

```markdown
**`VERIFY_OUTPUT` is the project's test/build output the loop retained** — the local review loop's step 4 is the one site in this skill that re-runs tests, and it writes `VERIFY_OUTPUT`, overwriting the previous value, so it always holds the most recent verification of the current HEAD. **It is unset far more often than not**: the reviewer loop never runs tests at all, and the local loop runs them only when it applied fixes.
```

with:

```markdown
**`VERIFY_OUTPUT` is the project's test/build output the loop retained** — step 2, the reviewer loop's item 4, and the local review loop's step 4 each write it under Rule 4, overwriting the previous value, so it always holds the most recent verification of the current HEAD. **It can still legitimately be unset**: every one of those sites runs verification only when code changed, so a run whose rounds changed nothing never sets it.
```

- [ ] **Step 7: Re-sync the mirror**

```bash
cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/
./scripts/verify-mirror.sh
```

Expected: exit 0.

- [ ] **Step 8: Run the harness to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`, exit 0.

- [ ] **Step 9: Commit**

```bash
git add plugins/quick-dev/skills/review-and-merge/SKILL.md \
        plugins/notion-dev/skills/review-and-merge/SKILL.md \
        .claude/skills/review-and-merge/SKILL.md \
        scripts/verify-convergence.sh
git commit -m "feat(review-and-merge): verify before every push of review fixes

quick-dev's reviewer loop never ran tests, so a broken fix cost a full
review round-trip to discover and arrived back as induced surface. Adds
verification at its step-2 and round push sites, states the rule in both
plugins, and corrects the VERIFY_OUTPUT gap the completeness verifier
documented.

Claude-Session: https://claude.ai/code/session_0165fEU2CPd9nwq2NsSGTTQN"
```

---

### Task 6: The CONVERGENCE report block

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md` (insert in `## 5. Merge`, after the `DROPPED` list paragraph ending `only \`FILED\` can generate new tickets.`)
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md` (same position)
- Modify: `.claude/skills/review-and-merge/SKILL.md` (via mirror sync)
- Test: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: every ledger field from Task 1; `RATCHET-ENGAGED-AT-ROUND` from Task 2's recorded round; `INDUCED-CHAINS-CUT` from Task 3's cut count.
- Produces: the `CONVERGENCE` block. Callers may read it the way they already read `COMPLETENESS-REPORT`; no caller change is in scope for this plan.

- [ ] **Step 1: Write the failing assertions**

In `scripts/verify-convergence.sh`, **inside** the `for P in "$ND" "$QD"` loop, append after the Rule 4 assertion:

```bash
  assert_has "$n r&m emits a CONVERGENCE block"      "$S" 'CONVERGENCE:'
  assert_has "$n r&m emits APPLY-RATE"               "$S" 'APPLY-RATE:'
  assert_has "$n r&m emits INDUCED"                  "$S" 'INDUCED:'
  assert_has "$n r&m emits INDUCED-CHAINS-CUT"       "$S" 'INDUCED-CHAINS-CUT:'
  assert_has "$n r&m emits RATCHET-ENGAGED-AT-ROUND" "$S" 'RATCHET-ENGAGED-AT-ROUND:'
  assert_has "$n r&m forbids an absent key"          "$S" 'never absence'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: 12 new `FAIL` lines; exit non-zero.

- [ ] **Step 3: Insert the block into both copies**

In **both** files, immediately after the paragraph `Callers depend on this split: the whole point is that only \`FILED\` can generate new tickets.` and before the `COMPLETENESS-REPORT` paragraph, insert identically:

````markdown
The report also carries a **`CONVERGENCE`** block, computed from the findings ledger:

```
CONVERGENCE:
ROUNDS: <n>
FINDINGS-TOTAL: <n>
APPLIED: <n>  DECLINED: <n>  FILED: <n>  DROPPED: <n>
APPLY-RATE: <pct>
INDUCED: <n> (<pct> of findings after round 1)
INDUCED-CHAINS-CUT: <n>
RATCHET-ENGAGED-AT-ROUND: <n | never>
```

Every key appears on every run. A key with nothing to report takes `0` or `never`, **never absence** —
an absent key is indistinguishable from a run that did not measure. This block
exists because the failure it guards against was invisible until someone correlated the GitHub
API against `git`: an 84% apply rate and a 68% induced rate appeared nowhere in any run's own
output. Read it as a calibration signal — an `APPLY-RATE` near 84% means the judgment bar is not
firing, or that Copilot findings are being over-rated as `blocking`; a `FILED` count that dwarfs
`APPLIED` is the opposite mis-calibration, with Rule 3 filing work that should have been fixed.
````

- [ ] **Step 4: Re-sync the mirror**

```bash
cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/
./scripts/verify-mirror.sh
```

Expected: exit 0.

- [ ] **Step 5: Run the harness to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`, exit 0.

- [ ] **Step 6: Commit**

```bash
git add plugins/quick-dev/skills/review-and-merge/SKILL.md \
        plugins/notion-dev/skills/review-and-merge/SKILL.md \
        .claude/skills/review-and-merge/SKILL.md \
        scripts/verify-convergence.sh
git commit -m "feat(review-and-merge): CONVERGENCE report block

Reports rounds, triage counts, apply rate, induced share, chains cut,
and the round the ratchet engaged. The 84% apply rate and 68% induced
rate that motivated this work appeared in no run's own output.

Claude-Session: https://claude.ai/code/session_0165fEU2CPd9nwq2NsSGTTQN"
```

---

### Task 7: Version bumps, spec correction, and the full sweep

**Files:**
- Modify: `plugins/quick-dev/.claude-plugin/plugin.json` (`0.9.0` → `0.10.0`)
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json` (`0.14.0` → `0.15.0`)
- Modify: `docs/superpowers/specs/2026-08-28-convergence-design.md` (lines 44 and 46)
- Test: `scripts/verify-convergence.sh`, `scripts/verify-mirror.sh`, `scripts/verify-completeness.sh`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: nothing later tasks read; this is the closing task.

- [ ] **Step 1: Write the failing assertions**

In `scripts/verify-convergence.sh`, after the closing `done` of the `== review-loop convergence ==` loop:

```bash
assert_identical "r&m mirror matches the quick-dev copy" \
  "$QD/skills/review-and-merge/SKILL.md" .claude/skills/review-and-merge/SKILL.md
assert_version_above "notion-dev bumped for review-loop convergence" "$ND/.claude-plugin/plugin.json" 0.14.0
assert_version_above "quick-dev bumped for review-loop convergence"  "$QD/.claude-plugin/plugin.json" 0.9.0
assert_lacks "2026-08-28 spec no longer claims within-ticket loops converge" \
  docs/superpowers/specs/2026-08-28-convergence-design.md 'The *within-ticket* loops converge.'
assert_lacks "2026-08-28 spec no longer claims the failure is entirely across-ticket" \
  docs/superpowers/specs/2026-08-28-convergence-design.md 'The failure is entirely in *across-ticket filing*.'
assert_has "review-loop spec carries the measurement" \
  docs/superpowers/specs/2026-08-29-review-loop-convergence-design.md '68%'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: 4 `FAIL` lines — the two version checks and the two `assert_lacks` spec checks. The mirror assertion already passes from Task 6's sync, and the `68%` check passes because the spec was committed before this plan began. Exit non-zero.

- [ ] **Step 3: Bump both plugin versions**

In `plugins/quick-dev/.claude-plugin/plugin.json`, change `"version": "0.9.0"` to `"version": "0.10.0"`.
In `plugins/notion-dev/.claude-plugin/plugin.json`, change `"version": "0.14.0"` to `"version": "0.15.0"`.

- [ ] **Step 4: Correct the 2026-08-28 spec**

In `docs/superpowers/specs/2026-08-28-convergence-design.md`, replace line 44's sentence:

```markdown
  cap. The *within-ticket* loops converge.
```

with:

```markdown
  cap. Those stopping rules were **not** sufficient in practice: measurement of 37 reviewer
  rounds found the within-ticket review loop running ten and eleven rounds, 68% of its findings
  self-inflicted. See `2026-08-29-review-loop-convergence-design.md`, which supersedes this
  paragraph. The across-ticket analysis below is unaffected.
```

And replace line 46:

```markdown
The failure is entirely in *across-ticket filing*.
```

with:

```markdown
The failure *this* design addresses is in *across-ticket filing*; the within-ticket review loop
has a separate convergence failure, addressed by `2026-08-29-review-loop-convergence-design.md`.
```

- [ ] **Step 5: Run every harness**

```bash
for s in scripts/verify-*.sh; do echo "--- $s"; "$s" || echo "FAILED: $s"; done
```

Expected: every script exits 0; `verify-convergence.sh` prints `ALL CHECKS PASSED`.

- [ ] **Step 6: Confirm the mirror is clean and nothing else drifted**

```bash
git status --porcelain
diff -r plugins/quick-dev/skills/review-and-merge .claude/skills/review-and-merge --exclude=README.md
```

Expected: `git status` lists only the intended files; `diff -r` prints nothing.

- [ ] **Step 7: Commit**

```bash
git add plugins/quick-dev/.claude-plugin/plugin.json \
        plugins/notion-dev/.claude-plugin/plugin.json \
        docs/superpowers/specs/2026-08-28-convergence-design.md \
        scripts/verify-convergence.sh
git commit -m "chore: bump plugin versions and correct the 2026-08-28 convergence claim

That spec asserted the within-ticket loops converge and the failure was
entirely across-ticket filing. Measurement refutes the first half; the
paragraph now points at the review-loop spec.

Claude-Session: https://claude.ai/code/session_0165fEU2CPd9nwq2NsSGTTQN"
```
