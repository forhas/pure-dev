# Convergence: Absorb-by-Default Triage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Invert the plugin's default from "defer deferrable work into new tickets" to "absorb it into the current ticket and gate the merge on it," so epics converge.

**Architecture:** A single triage vocabulary (`absorb` / `file` / `drop`) and a mechanical blast-radius test are introduced in the shared plan-review rubric, then threaded through both plugins' plan-review skills, review-and-merge skills, and — in `notion-dev` only — through `REVIEW_REPORT` into `epic-update`, which now consumes `file` items exclusively and no longer lets a declined follow-up block epic closure forever.

**Tech Stack:** Markdown instruction files (Claude Code plugin skills and commands). Bash for the verification harness. No application code, no package manager, no runtime.

**Spec:** `docs/superpowers/specs/2026-08-28-convergence-design.md` — read it before Task 1; every task below argues from it.

## Global Constraints

- **This repo ships prompts, not code.** There is no test framework, no `package.json`, no build. The "tests" in this plan are structural assertions (`grep`, `diff`, key counts) collected in `scripts/verify-convergence.sh`, built up one task at a time. The red/green cycle is real: add the assertion, watch it fail, make the edit, watch it pass.
- **`reviewer-rubric.md` must stay byte-identical** between `plugins/quick-dev/skills/plan-review/references/` and `plugins/notion-dev/skills/plan-review/references/`. It is identical today. Every task that touches it edits one copy and `cp`s to the other.
- **The other four shared skills have already diverged** (`plan-review/SKILL.md`, `review-and-merge/SKILL.md`, `local-code-review/SKILL.md`, `flow-triage/SKILL.md`). Never `cp` these — edit each copy separately, preserving its local wording. Unifying them is explicitly out of scope.
- **Vocabulary is fixed and literal:** `absorb`, `file`, `drop`. Lowercase in prose and in rubric output. Uppercase only as `REVIEW_REPORT` list names: `ABSORBED`, `FILED`, `DROPPED`. No synonyms — not "inline", not "fold in", not "skip".
- **The three blast-radius criteria are numbered 1, 2, 3** and every `file` decision must cite its number. The numbering is part of the contract.
- **The plan-review output block stays at exactly nine keys.** `TRIAGE:` takes the slot `NOT-IN-SCOPE:` occupied. The doc's own sentence "every one of the nine keys must be present" must remain true and remain in the file.
- **`epic-update`'s legacy log line `**Follow-ups skipped**` must still parse.** Clients have live Notion epics containing it. Dropping this compatibility strands exactly the epics this change exists to unstick.
- Commit after every task. Conventional-commit prefixes, matching repo history (`fix(notion-dev):`, `feat(quick-dev):`, `docs(specs):`, `chore:`).

---

### Task 1: Verification harness + rubric triage section

The rubric is the source of the whole change: it is the one file both plugins share byte-for-byte, and it is what tells the reviewer agent to triage instead of merely list.

**Files:**
- Create: `scripts/verify-convergence.sh`
- Modify: `plugins/notion-dev/skills/plan-review/references/reviewer-rubric.md:115-125` (the `## Deferred work` section) and `:141` region (output contract item 4)
- Mirror: `plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md` (via `cp`)

**Interfaces:**
- Consumes: nothing.
- Produces: the `absorb` / `file` / `drop` vocabulary; the three numbered blast-radius criteria; the reviewer-agent output line `TRIAGE-COMPLETE: <yes | no>`. Tasks 2-7 all reference these exact strings.

- [ ] **Step 1: Write the failing test**

Create `scripts/verify-convergence.sh`:

```bash
#!/usr/bin/env bash
# Structural verification for the absorb-by-default triage change.
# This repo ships markdown instruction files, not code — these greps and
# diffs are the test suite. Run from anywhere: ./scripts/verify-convergence.sh
set -uo pipefail
cd "$(dirname "$0")/.."

ND=plugins/notion-dev
QD=plugins/quick-dev
fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# assert_has <label> <file> <literal string>
assert_has() {
  if grep -qF -- "$3" "$2"; then ok "$1"; else bad "$1"; fi
}

# assert_lacks <label> <file> <literal string>
assert_lacks() {
  if grep -qF -- "$3" "$2"; then bad "$1"; else ok "$1"; fi
}

# assert_identical <label> <fileA> <fileB>
assert_identical() {
  if diff -q "$2" "$3" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi
}

echo "== Task 1: rubric =="
RUBRIC=$ND/skills/plan-review/references/reviewer-rubric.md
assert_has    "rubric declares 'absorb'"            "$RUBRIC" '`absorb`'
assert_has    "rubric declares 'file'"              "$RUBRIC" '`file`'
assert_has    "rubric declares 'drop'"              "$RUBRIC" '`drop`'
assert_has    "rubric has blast-radius criterion 1" "$RUBRIC" 'reaches code the ticket was not already changing'
assert_has    "rubric has blast-radius criterion 2" "$RUBRIC" 'new public interface, dependency, config key, or data migration'
assert_has    "rubric has blast-radius criterion 3" "$RUBRIC" 'acceptance criteria do not already settle'
assert_has    "rubric emits TRIAGE-COMPLETE"        "$RUBRIC" 'TRIAGE-COMPLETE:'
assert_lacks  "rubric drops NOT-IN-SCOPE-PRESENT"   "$RUBRIC" 'NOT-IN-SCOPE-PRESENT'
assert_identical "rubric copies are byte-identical" \
  "$QD/skills/plan-review/references/reviewer-rubric.md" "$RUBRIC"

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
```

Then: `chmod +x scripts/verify-convergence.sh`

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: FAIL — 8 failures (every rubric assertion except `rubric copies are byte-identical`, which passes because neither copy has been touched yet).

- [ ] **Step 3: Replace the rubric's `## Deferred work` section**

In `plugins/notion-dev/skills/plan-review/references/reviewer-rubric.md`, replace the entire `## Deferred work` section (from the `## Deferred work` heading through the line `The line reports whether the deferred-work requirement is *satisfied*, not merely whether the heading exists.`) with:

```markdown
## Deferred work

If your review identifies work the plan could reasonably defer, **triage it — do not merely
list it.** Assign every such item exactly one label:

- **`absorb`** — do it in this ticket. **This is the default.**
- **`file`** — genuinely separate work; it becomes its own ticket.
- **`drop`** — theoretical or insignificant; recorded with a rationale, never built.

Evaluate `drop` first, under the judgment bar you already apply to every finding: an item
that is speculative, cosmetic-only, or unverifiable is a `drop`. Do not manufacture work.

Everything surviving `drop` is **`absorb`** unless **any** of these is true, in which case
it is `file`:

1. It **reaches code the ticket was not already changing** — files outside the plan's
   declared file set. New files the plan itself creates count as *inside*.
2. It requires a **new public interface, dependency, config key, or data migration**.
3. It needs a design decision the plan's **acceptance criteria do not already settle**.

None true → `absorb`. Every `file` item **must cite the criterion number** that made it one.
A `file` item with no criterion number is not triaged.

Then emit the `TRIAGE-COMPLETE:` line per these three cases:

- **An `absorb` item is not present in the plan's task list, *or* a `file` item lacks its
  criterion number** — raise one Required finding naming those specific items. For an
  `absorb` item the fix is always *"add this task to the plan"* — never *"add it to Not in
  scope."* Emit `TRIAGE-COMPLETE: no`.
- **Every `absorb` item is already a plan task and every `file` item cites its criterion** —
  no finding; emit `TRIAGE-COMPLETE: yes`. `file` items belong in the plan's `## Not in
  scope` section with a one-line rationale and their criterion number.
- **Nothing to triage** — no finding; emit `TRIAGE-COMPLETE: yes`, regardless of whether a
  `## Not in scope` heading exists. Requiring the heading for its own sake is exactly the
  cosmetic finding this rubric forbids.

The line reports whether the triage requirement is *satisfied*, not merely whether a heading
exists. Pushing work out of the plan is the exception you must justify, not the default.
```

- [ ] **Step 4: Update the rubric's output contract**

In the same file, in `## Output contract (MUST follow exactly)`, replace item 4:

```markdown
4. `NOT-IN-SCOPE-PRESENT: <yes | no>`
```

with:

```markdown
4. `TRIAGE-COMPLETE: <yes | no>`, followed by one line per triaged item on the form
   `<absorb | file | drop>: <item> — <rationale>`, with ` (criterion <n>)` appended on every
   `file` line. Write `TRIAGE-COMPLETE: yes` alone when there was nothing to triage.
```

- [ ] **Step 5: Mirror to quick-dev**

```bash
cp plugins/notion-dev/skills/plan-review/references/reviewer-rubric.md \
   plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md
```

- [ ] **Step 6: Run it to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`

- [ ] **Step 7: Commit**

```bash
git add scripts/verify-convergence.sh plugins/*/skills/plan-review/references/reviewer-rubric.md
git commit -m "feat(plan-review): triage deferrable work as absorb/file/drop instead of listing it

The rubric graded reviewers on producing a deferral list, which made every
plan manufacture follow-up work. Replace it with a blast-radius test whose
default is absorb, and require a criterion number on anything pushed out.

Adds scripts/verify-convergence.sh as the structural test harness for this
change — this repo ships prompts, so greps and diffs are the test suite."
```

---

### Task 2: plan-review skill — contract check, plan edits, output block

The rubric now emits `TRIAGE-COMPLETE`; the skill that parses it, acts on it, and re-emits it to callers must follow. Both plugins, edited separately — these copies have diverged.

**Files:**
- Modify: `plugins/notion-dev/skills/plan-review/SKILL.md:62` (parse), `:70` (contract check clause), `:76` (degradation), `:94` (step 4 plan edit), `:120-131` (output block)
- Modify: `plugins/quick-dev/skills/plan-review/SKILL.md` — same five sites, at `:57`, `:65`, `:71`, `:89`, `:115-126` (verify by anchor text, not by line number)
- Modify: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: `TRIAGE-COMPLETE:` and the per-item triage lines from Task 1's rubric.
- Produces: the nine-key output block with `TRIAGE:` in place of `NOT-IN-SCOPE:`, carrying lines of the form `<absorb|file|drop>: <item> — <rationale>` (plus ` (criterion <n>)` on `file` lines), or `NONE`. Task 5 reads this block as `PLAN_REVIEW_REPORT`.

- [ ] **Step 1: Add the failing assertions**

In `scripts/verify-convergence.sh`, insert before the final `echo`:

```bash
echo "== Task 2: plan-review skill =="
for P in "$ND" "$QD"; do
  S=$P/skills/plan-review/SKILL.md
  n=$(basename "$P")
  assert_has   "$n plan-review parses TRIAGE-COMPLETE" "$S" 'TRIAGE-COMPLETE'
  assert_has   "$n plan-review block has TRIAGE key"   "$S" 'TRIAGE:'
  assert_has   "$n plan-review keeps nine-key rule"    "$S" 'nine keys'
  assert_lacks "$n plan-review drops NOT-IN-SCOPE"     "$S" 'NOT-IN-SCOPE'
  assert_has   "$n plan-review absorb→plan tasks"      "$S" 'absorb'
done
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: FAIL — Task 1 checks pass; 8 of the 10 new checks fail (`nine keys` already passes in both).

- [ ] **Step 3: Update the parse line (both plugins)**

Find the sentence beginning `Parse from its output:` and replace `NOT-IN-SCOPE-PRESENT` with `TRIAGE-COMPLETE` and its per-item triage lines. The notion-dev line becomes:

```markdown
Parse from its output: the findings list with severities, `TRIAGE-COMPLETE` together with the per-item triage lines beneath it, and the `VERDICT` line.
```

- [ ] **Step 4: Update the contract check (both plugins)**

In the `**Contract check.**` paragraph, replace the mandatory-element phrase `a `NOT-IN-SCOPE-PRESENT` line` with:

```markdown
a `TRIAGE-COMPLETE` line
```

Then replace the third bullet of the "every field that asserts a defect must be matched by its own blocking finding" list:

```markdown
  - `NOT-IN-SCOPE-PRESENT: no` with no blocking finding naming the missing deferred work — the rubric emits `no` only when concrete deferrable work is missing from the plan, and requires a Required finding naming those items.
```

with:

```markdown
  - `TRIAGE-COMPLETE: no` with no blocking finding naming the un-triaged items — the rubric emits `no` only when an `absorb` item is missing from the plan's task list or a `file` item lacks its criterion number, and requires a Required finding naming those items.
```

- [ ] **Step 5: Update the degradation path (both plugins)**

In the `**Degradation.**` paragraph, replace `NONE` on both `NOT-IN-SCOPE:` and `DECLINED-WITH-REASONING:` with:

```markdown
`NONE` on both `TRIAGE:` and `DECLINED-WITH-REASONING:`
```

- [ ] **Step 6: Update step 4's plan edit (both plugins)**

Replace this line:

```markdown
If accepted findings identified deferrable work and the plan has no `## Not in scope` section, add one with those items and a one-line rationale each.
```

with:

```markdown
Apply the triage. Every `absorb` item becomes a **task in the plan**, appended to the task list with an unchecked `- [ ]` checkbox so the resume detection callers rely on sees it. Only `file` items go to `## Not in scope` — add the section if it is missing, giving each item a one-line rationale and its blast-radius criterion number. `drop` items are recorded in the output block and are not written into the plan at all.

Never resolve an `absorb` item by moving it to `## Not in scope`. If an item's blast radius was misjudged, re-triage it to `file` **and cite the criterion that turned out true** — that reclassification is a decision on the record, not a way of shelving the work.
```

- [ ] **Step 7: Update the output block (both plugins)**

In the fenced output block, replace:

```
NOT-IN-SCOPE:
<deferred items, one per line with a one-line rationale, or NONE>
```

with:

```
TRIAGE:
<one line per item as `<absorb | file | drop>: <item> — <rationale>`, with ` (criterion <n>)` on every file line, or NONE>
```

Leave the other eight keys and their order untouched — the block must remain nine keys, and the sentence asserting that stays as written.

- [ ] **Step 8: Run it to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`

- [ ] **Step 9: Commit**

```bash
git add scripts/verify-convergence.sh plugins/*/skills/plan-review/SKILL.md
git commit -m "feat(plan-review): act on the triage — absorb items become plan tasks

Parses TRIAGE-COMPLETE, blocks on un-triaged items, and appends absorb
items to the plan's task list so subagent-driven-development builds them.
Only file items reach '## Not in scope'. Output block keeps its nine keys;
NOT-IN-SCOPE: becomes TRIAGE:."
```

---

### Task 3: review-and-merge — triage axis and the absorb merge gate

Plan-time absorption needs no gate because absorbed items are just plan tasks. Review-time absorption does: the PR already exists, so something must insist the work lands before merge.

**Files:**
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md` — `## 2. Process existing review comments` (`:87-110`), `### Local review loop` step 4 (`:374`), `## 5. Merge` hard gates (`:385-395`)
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md` — same three sites at `:72`, `:358`, `:369` (locate by heading text)
- Modify: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: the vocabulary and three criteria from Task 1.
- Produces: the merge-gate rule string `No absorb item may be outstanding at merge`, and the `ABSORBED` / `FILED` / `DROPPED` lists in the skill's final report. Task 5 reads that report as `REVIEW_REPORT`.

- [ ] **Step 1: Add the failing assertions**

In `scripts/verify-convergence.sh`, insert before the final `echo`:

```bash
echo "== Task 3: review-and-merge =="
for P in "$ND" "$QD"; do
  S=$P/skills/review-and-merge/SKILL.md
  n=$(basename "$P")
  assert_has "$n r&m has the absorb merge gate"  "$S" 'No `absorb` item may be outstanding at merge'
  assert_has "$n r&m has the reclassify escape"  "$S" 'reclassification, not a bypass'
  assert_has "$n r&m reports ABSORBED"           "$S" 'ABSORBED'
  assert_has "$n r&m reports FILED"              "$S" 'FILED'
  assert_has "$n r&m reports DROPPED"            "$S" 'DROPPED'
done
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: FAIL — 10 new failures.

- [ ] **Step 3: Add the triage axis to step 2 (both plugins)**

In `## 2. Process existing review comments`, immediately after the paragraph beginning `This judgment bar governs **every** piece of review feedback in this flow`, insert:

```markdown
**Triage is two-axis.** The agree / partially agree / disagree axis decides whether a finding
is *right*. A second axis decides *where the work goes*, and applies to every finding you
agreed with (fully or partly) that is not already fixed in this round:

- **`drop`** — theoretical or insignificant under the judgment bar above. Record the
  rationale; build nothing. A **disagreed** finding is already resolved and is not triaged —
  it is a decline, not a `drop`.
- **`absorb`** — do it in this PR, before merge. **This is the default.**
- **`file`** — becomes its own ticket, and only when **any** of these is true:
  1. It **reaches code this PR was not already changing** — files outside
     `git diff --name-only origin/<PR_BASE>...HEAD`. New files this PR creates count as
     *inside*.
  2. It requires a **new public interface, dependency, config key, or data migration**.
  3. It needs a design decision the ticket's **acceptance criteria do not already settle**.

  Every `file` item must cite the criterion number that made it one.

Absorbing does not skip review: the absorbed change is pushed like any other fix and the next
round reviews it. That is why this cannot run away — absorbed work re-enters the existing
round-capped loop, and the round cap is the backstop.
```

- [ ] **Step 4: Extend the local review loop's triage (both plugins)**

In `### Local review loop (reviewer unavailable)`, append to item 4 (the `**Triage**` item), after `record each decline's rationale in a follow-up PR comment (or the round comment itself)`:

```markdown
Local findings are triaged on the same two axes as step 2 — every agreed-but-unfixed finding gets `absorb`, `file`, or `drop`, and `file` items cite their criterion number.
```

- [ ] **Step 5: Add the merge gate (both plugins)**

In `## 5. Merge`, in the numbered list of hard gates, insert a new gate after the `**All threads resolved**` gate and renumber the gates that follow it:

```markdown
3. **Absorb gate**: **No `absorb` item may be outstanding at merge.** Every finding triaged
   `absorb` in step 2 or the local loop must be applied, pushed, and reviewed.

   The only way past this gate is a **reclassification, not a bypass**: re-triage the item to
   `file` and record which blast-radius criterion turned out true. A misjudged item can always
   get out; it can never get out silently. Because the escape always exists, this gate cannot
   deadlock a non-interactive run.

   This gate composes with the loop terminators rather than replacing them — the round cap,
   the oscillation guard, and the judgment-based stop all still end the loop. The gate only
   asserts that when the loop *does* end, nothing labeled `absorb` was left behind.
```

Renumber the subsequent gates (`Config pre-merge checks` and anything after it) accordingly, and update any cross-reference in the file that names a gate by number.

- [ ] **Step 6: Add the three lists to the final report (both plugins)**

The final report has **no heading of its own** — it is the closing paragraph of `## 5. Merge`, beginning `Confirm `gh pr view <pr> --json state` reports `MERGED`` (notion-dev `:407`; locate the same paragraph in quick-dev by that opening text). Append to that paragraph — do **not** create a new `## 6.` section:

```markdown
The report's triage outcome is **three named lists**, never one undifferentiated set:

- `ABSORBED` — items done in this PR, each with what was changed.
- `FILED` — items that must become their own ticket, each with its criterion number and
  rationale. Reclassified items appear here, marked as reclassified from `absorb`.
- `DROPPED` — items decided against, each with its rationale.

Callers depend on this split: the whole point is that only `FILED` can generate new tickets.
```

- [ ] **Step 7: Run it to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`

- [ ] **Step 8: Commit**

```bash
git add scripts/verify-convergence.sh plugins/*/skills/review-and-merge/SKILL.md
git commit -m "feat(review-and-merge): absorb by default, gate the merge on it

Adds the second triage axis (absorb/file/drop) to review feedback and a
merge gate that no absorb item may be outstanding. The escape is an
explicit reclassification to file citing a blast-radius criterion, so a
misjudged item can get out but never silently.

Splits the report's deferred items into ABSORBED / FILED / DROPPED so only
FILED can generate tickets downstream."
```

---

### Task 4: quick-dev develop — widen the merge gate, surface `FILED`

`quick-dev` has no ticket backend, so its `file` items have nowhere to go and currently die with `PLAN.md`. This is the graveyard half of the same defect.

**Files:**
- Modify: `plugins/quick-dev/skills/develop/SKILL.md:121` (local-mode merge gate) and the final-report section
- Modify: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: `ABSORBED` / `FILED` / `DROPPED` from Task 3's review-and-merge report; `TRIAGE:` from Task 2's plan-review block.
- Produces: nothing downstream — `quick-dev` terminates at the merge.

- [ ] **Step 1: Add the failing assertions**

In `scripts/verify-convergence.sh`, insert before the final `echo`:

```bash
echo "== Task 4: quick-dev develop =="
D=$QD/skills/develop/SKILL.md
assert_has "develop merge gate covers absorb" "$D" 'outstanding `absorb`'
assert_has "develop reports FILED items"      "$D" 'FILED'
assert_lacks "develop drops stale NOT-IN-SCOPE key" "$D" 'NOT-IN-SCOPE'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: FAIL — 2 new failures.

- [ ] **Step 3: Widen the local-mode merge gate**

In `**Local mode**` item 4 (`**Merge gate**`), replace:

```markdown
4. **Merge gate**: findings the flow declined with reasoning (step 2) are resolved and do not block; if any *accepted-but-unfixed* Critical/Required finding remains, do not proceed to the merge silently
```

with:

```markdown
4. **Merge gate**: findings the flow declined with reasoning (step 2) are resolved and do not block; if any *accepted-but-unfixed* Critical/Required finding remains, **or any outstanding `absorb` item remains** (any severity — an `absorb` item is gated by where its work belongs, not by how bad it is; the two conditions are complementary, not overlapping), do not proceed to the merge silently
```

- [ ] **Step 4: Surface `file` items in the final report**

In the final-report section of `develop/SKILL.md`, add:

```markdown
- **Triage outcome** — the `ABSORBED` / `FILED` / `DROPPED` lists from `review-and-merge`, merged with the `file` items from the plan review's `TRIAGE:` block. `quick-dev` has no ticket backend, so **`FILED` items are reported to the user here or they are lost** — this is their only durable destination. Report each with its blast-radius criterion number so the user can judge whether it deserves its own run of `/quick-dev:develop`.
```

- [ ] **Step 4b: Fix the stale `NOT-IN-SCOPE` key references (ruling PF-4)**

`develop/SKILL.md:69` still consumes the plan-review block key that Task 2 renamed. Two edits in that one paragraph:

- In the enumeration of the nine keys (`PLAN-REVIEW`, `FINDINGS`, … `NOT-IN-SCOPE`, `DECLINED-WITH-REASONING`, `UNRESOLVED`), replace `NOT-IN-SCOPE` with `TRIAGE`. The list must still name exactly nine keys.
- Replace the trailing clause `carry `NOT-IN-SCOPE` into the PR body in Phase 3` with:

```markdown
carry the `TRIAGE:` block's `file` items — with their criterion numbers — into the PR body in Phase 3, so a reviewer can see what was deliberately left out and why. `absorb` items are not carried: they are plan tasks and will be in the diff.
```

- [ ] **Step 5: Run it to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`

- [ ] **Step 6: Commit**

```bash
git add scripts/verify-convergence.sh plugins/quick-dev/skills/develop/SKILL.md
git commit -m "fix(quick-dev): gate merge on absorb items and stop losing filed work

The develop flow had no handling of deferred items at all — they died with
PLAN.md. Widen the local merge gate to cover outstanding absorb items, and
report FILED items in the final summary, which is their only destination in
a plugin with no ticket backend."
```

---

### Task 5: `REVIEW_REPORT` three lists through `ticket` and `finalize`

This is where the branching factor actually drops: `epic-update` stops seeing anything but `FILED`.

**Files:**
- Modify: `plugins/notion-dev/commands/ticket.md:286` (Notes), `:313` (record `REVIEW_REPORT`), `:348-349` (Merged fields), `:391` (final report)
- Modify: `plugins/notion-dev/commands/finalize.md:108-109` (Merged fields), `:150` (final report)
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md:221-226` (Merged section rendering example)
- Modify: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: `ABSORBED` / `FILED` / `DROPPED` (Task 3), `TRIAGE:` (Task 2).
- Produces: `REVIEW_REPORT` carrying the three lists. Task 6's `epic-update` reads **only** `FILED` from it.

- [ ] **Step 1: Add the failing assertions**

In `scripts/verify-convergence.sh`, insert before the final `echo`:

```bash
echo "== Task 5: REVIEW_REPORT three lists =="
for F in $ND/commands/ticket.md $ND/commands/finalize.md; do
  n=$(basename "$F")
  assert_has "$n records ABSORBED" "$F" 'ABSORBED'
  assert_has "$n records DROPPED"  "$F" 'DROPPED'
  assert_has "$n passes only FILED to epic-update" "$F" 'the `FILED` list'
done
assert_has "ticket-system renders Absorbed" "$ND/skills/ticket-system/SKILL.md" 'Absorbed'
assert_has "ticket-system renders Dropped"  "$ND/skills/ticket-system/SKILL.md" 'Dropped'
assert_lacks "ticket.md drops stale NOT-IN-SCOPE key" "$ND/commands/ticket.md" 'NOT-IN-SCOPE'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: FAIL — 8 new failures.

- [ ] **Step 3: Update `ticket.md` Phase 6.5 Notes**

Replace the `**Notes**` bullet:

```markdown
  - **Notes** — optional. Any caveats for the reviewer or follow-up items discovered but out of scope — including the plan review's `NOT-IN-SCOPE` deferred items, which otherwise die with `PLAN.md` in 6.6.
```

with:

```markdown
  - **Notes** — optional. Any caveats for the reviewer, plus the plan review's `TRIAGE:` **`file`** items with their criterion numbers, which otherwise die with `PLAN.md` in 6.6. The plan review's `absorb` items are **not** listed here: they were appended to `PLAN.md` as tasks and are already built, so they belong in the **Implementation** bullet above like any other completed work. Its `drop` items are listed with their rationale, so a reader can see what was considered and decided against.
```

- [ ] **Step 3b: Fix the stale `NOT-IN-SCOPE` key reference at `ticket.md:169` (ruling PF-4)**

Phase 4's `PLAN_REVIEW_REPORT` capture enumerates the plan-review block's nine keys and still names the one Task 2 renamed. In that enumeration (`PLAN-REVIEW`, `FINDINGS`, … `NOT-IN-SCOPE`, `DECLINED-WITH-REASONING`, `UNRESOLVED`), replace `NOT-IN-SCOPE` with `TRIAGE`. The list must still name exactly nine keys. Change nothing else in that paragraph.

- [ ] **Step 4: Update `ticket.md` Phase 7's `REVIEW_REPORT` capture**

After the sentence `Record its final report (which loop ran, rounds, applied vs. declined) as `REVIEW_REPORT`.`, insert:

```markdown
`REVIEW_REPORT` carries the skill's three triage lists verbatim — `ABSORBED`, `FILED`, `DROPPED` — and they must survive the persist below intact. **Only the `FILED` list is passed to `notion-dev:epic-update` in 8.2.** `ABSORBED` items are already merged and `DROPPED` items are already decided; filing either would recreate the non-convergence this split exists to stop.
```

- [ ] **Step 5: Update `ticket.md` Phase 8.3 Merged fields**

Replace the `**Review resolution**` and `**Deferred follow-ups**` bullets with:

```markdown
- **Review resolution** — 1-3 bullets summarizing how review feedback was handled, distilled from `REVIEW_REPORT` (e.g. "applied 4 comments, absorbed 2 findings, filed 1 follow-up, disagreed on 1").
- **Absorbed** — items from `REVIEW_REPORT`'s `ABSORBED` list, each with what was changed. Omit the field when the list is empty. These needed no ticket because the work is in this PR.
- **Deferred follow-ups** — items from `REVIEW_REPORT`'s `FILED` list, each with its blast-radius criterion number and its actual follow-up ticket ID/URL from `EPIC_REPORT`'s `FILED` ∪ `ALREADY_FILED` (both now known, since 8.2 already ran). `epic-update` remains best-effort: when `EPIC_REPORT` is `EPIC-UPDATE: none`, or a given item isn't in either list (e.g. `epic-update` failed partway, or the item is in `DROPPED` or `FAILED-TO-FILE`), list that item with no ID rather than inventing one — this section is still written with whatever is known, never blocked on 8.2's outcome.
- **Dropped** — items from `REVIEW_REPORT`'s `DROPPED` list, each with its rationale. Omit the field when the list is empty. A recorded drop is a decision, not an omission.
```

- [ ] **Step 6: Apply the equivalent changes to `finalize.md`**

`finalize.md` Phase 3.3 carries near-identical bullets, but they reference **3.2** where `ticket.md` references 8.2 — do not paste Step 5's text unchanged. Replace its `**Review resolution**` and `**Deferred follow-ups**` bullets with:

```markdown
- **Review resolution** — 1-3 bullets summarizing how review feedback was handled, distilled from `REVIEW_REPORT` (e.g. "applied 4 comments, absorbed 2 findings, filed 1 follow-up, disagreed on 1").
- **Absorbed** — items from `REVIEW_REPORT`'s `ABSORBED` list, each with what was changed. Omit the field when the list is empty. These needed no ticket because the work is in this PR.
- **Deferred follow-ups** — items from `REVIEW_REPORT`'s `FILED` list, each with its blast-radius criterion number and its actual follow-up ticket ID/URL from `EPIC_REPORT`'s `FILED` ∪ `ALREADY_FILED` (both now known, since 3.2 already ran). `epic-update` remains best-effort: when `EPIC_REPORT` is `EPIC-UPDATE: none`, or a given item isn't in either list (e.g. `epic-update` failed partway, or the item is in `DROPPED` or `FAILED-TO-FILE`), list that item with no ID rather than inventing one — this section is still written with whatever is known, never blocked on 3.2's outcome.
- **Dropped** — items from `REVIEW_REPORT`'s `DROPPED` list, each with its rationale. Omit the field when the list is empty. A recorded drop is a decision, not an omission.
```

Then add to `finalize.md` Phase 3.2, after the `notion-dev:epic-update` invocation is described:

```markdown
**Only the `FILED` list** from `REVIEW_REPORT` is passed to `epic-update`. `ABSORBED` items are already merged and `DROPPED` items are already decided; filing either would recreate the non-convergence this split exists to stop.
```

Note that `finalize.md`'s recovery path (Phase 1 step 2) reads a persisted `REVIEW_REPORT` written by an earlier `/notion-dev:ticket` run. A report persisted before this change has no `ABSORBED`/`FILED`/`DROPPED` split — treat its single deferred list as `FILED`, which reproduces the old behavior exactly for in-flight work rather than silently dropping it.

- [ ] **Step 7: Update both final-report lines**

In `ticket.md` and `finalize.md`, the epic-outcome line currently reads `follow-ups filed (with their IDs) versus deferred`. Replace that phrase in both with:

```markdown
follow-ups absorbed, filed (with their IDs), and dropped
```

- [ ] **Step 8: Update the `ticket-system` Merged rendering example**

In the `## Merged` rendered example, after the `**Review resolution**` bullets, replace the `**Deferred follow-ups**` block with:

```markdown
  **Absorbed**
  • Tightened the token TTL check the reviewer flagged (same file as the fix).

  **Deferred follow-ups**
  • STO-42 — refactor session token storage (criterion 1: touches storage layer)

  **Dropped**
  • Rename `sess` to `session` throughout — cosmetic churn, declined under the judgment bar.
```

and update the `**Review resolution**` example bullet `• Deferred 1 as follow-up (see STO-42).` to `• Absorbed 1 finding; deferred 1 as follow-up (see STO-42).`

- [ ] **Step 8b: Update the Merged render contract (ruling PF-5)**

`ticket-system/SKILL.md:204` states the `Merged` section's render contract, and its parenthetical enumerates the **list** fields: `(Review resolution as bullets, Deferred follow-ups as a bulleted list with linked ticket IDs where present)`. Step 8 adds two more list fields, so that enumeration is now incomplete. Replace the parenthetical with:

```markdown
(`Review resolution` as bullets, `Absorbed` as a bulleted list, `Deferred follow-ups` as a bulleted list with linked ticket IDs where present, `Dropped` as a bulleted list with each item's rationale)
```

The per-field scalar/list split rule below it already routes these correctly — this edit keeps the enumeration truthful, it does not change adapter behavior.

- [ ] **Step 9: Run it to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`

- [ ] **Step 10: Commit**

```bash
git add scripts/verify-convergence.sh plugins/notion-dev/commands/ticket.md \
        plugins/notion-dev/commands/finalize.md \
        plugins/notion-dev/skills/ticket-system/SKILL.md
git commit -m "feat(notion-dev): split REVIEW_REPORT into ABSORBED/FILED/DROPPED

Only FILED reaches epic-update, which is where the epic's branching factor
actually drops. ABSORBED items are already merged and DROPPED items are
already decided; both are still recorded on the ticket so nothing becomes
invisible."
```

---

### Task 6: `epic-update` — `FILED`-only input, Drop replaces Skip, closure unblocked

The most intricately-reasoned file in the repo. Its steps 1a, 2, 4, and 5 must change **together** — a partial edit here produces epics that cannot close *and* cannot recover.

**Files:**
- Modify: `plugins/notion-dev/skills/epic-update/SKILL.md` — `:38` (step 1a repopulation), `:48-50` (step 2 source), `:60` (the interactive gate), `:78` (outcome recording), `:84-99` (step 4 closure conditions), `:106-110` (step 5 log lines), `:115` (`UNKNOWN` sentinel parse), `:137-139` (output block)
- Modify: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: `REVIEW_REPORT`'s `FILED` list only (Task 5).
- Produces: `EPIC_REPORT` with `FILED`, `ALREADY_FILED`, `DROPPED`, `FAILED-TO-FILE`. `ticket.md` 8.3 and `finalize.md` 3.3 read `FILED` ∪ `ALREADY_FILED` from it.

- [ ] **Step 1: Add the failing assertions**

In `scripts/verify-convergence.sh`, insert before the final `echo`:

```bash
echo "== Task 6: epic-update =="
E=$ND/skills/epic-update/SKILL.md
assert_has   "epic-update sources FILED only"        "$E" 'only the `FILED` list'
assert_has   "epic-update gate offers Drop"          "$E" 'Drop (with rationale)'
assert_has   "epic-update records DROPPED"           "$E" 'DROPPED'
assert_has   "epic-update writes new log line"       "$E" '**Follow-ups dropped**'
assert_has   "epic-update parses legacy log line"    "$E" '**Follow-ups skipped**'
assert_lacks "epic-update: SKIPPED no longer blocks" "$E" '`SKIPPED` is empty'
assert_lacks "epic-update: SKIPPED key removed"      "$E" 'SKIPPED:'
```

Note the deliberate asymmetry in the last four: the **log line** `**Follow-ups skipped**` must survive (legacy epics contain it); the **blocking condition** and the **output-block key** must not.

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: FAIL — 6 new failures. Only `epic-update parses legacy log line` passes, because `**Follow-ups skipped**` already appears in the file today (4 occurrences). Verified preconditions: `DROPPED` 0 occurrences, `` `SKIPPED` is empty `` 1, `SKIPPED:` 2.

- [ ] **Step 3: Restrict step 2's source to `FILED`**

Replace step 2's opening:

```markdown
**2. File deferred follow-ups.** Source: `REVIEW_REPORT`'s deferred follow-ups — the same list written to the ticket's `## Merged` section.
```

with:

```markdown
**2. File deferred follow-ups.** Source: **only the `FILED` list** from `REVIEW_REPORT` — the same list written to the ticket's `## Merged` **Deferred follow-ups** field. `ABSORBED` items are already merged and `DROPPED` items are already decided; neither is ever filed. Reading any list but `FILED` here reinstates the unbounded ticket growth this split exists to stop.
```

- [ ] **Step 4: Replace the Skip gate with a Drop gate**

Replace the interactive-gate bullet:

```markdown
  - **Interactive**: `AskUserQuestion` — **File as ticket** / **Skip**. Default File. Skip → the item goes to `SKIPPED`, a user decision — permanent, and never retried by a later invocation.
```

with:

```markdown
  - **Interactive**: `AskUserQuestion` — **File as ticket** / **Drop (with rationale)**. Default File. The item arriving here has already been triaged `file` upstream, so choosing Drop is not "leave it undone" — it is *"I disagree with that triage; this is a `drop`."* That is a **decision**, and a decision closes work rather than blocking it. The rationale is required and is written into step 5's log entry. Drop → the item goes to `DROPPED`; it is never retried, and it never blocks closure.
```

- [ ] **Step 5: Rename the outcome variable in steps 1a, 2, and the output block**

Rename `SKIPPED` → `DROPPED` at every site where it names *this run's outcome variable*:
- step 1a's repopulation bullet and its "user decision" explanation,
- step 2's outcome recording (`Record `FILED` = …`),
- step 4's conditions (Step 6 below),
- step 5's log line (Step 7 below),
- the output block's `SKIPPED:` key → `DROPPED:`, and `SKIPPED: unknown` → `DROPPED: unknown`.

Update step 1a's explanation of what the variable means:

```markdown
- `DROPPED` is a **user decision**: the original run's interactive gate offered File/Drop and the user chose Drop, with a rationale. That decision is permanent and is never retried here. It does **not** block epic closure — a recorded drop is finished work, not outstanding work. Parse it off the matched entry's `**Follow-ups dropped**` line, **or its legacy spelling `**Follow-ups skipped**`** — epics written before this change carry the old wording and must still parse. Treat both spellings identically.
```

- [ ] **Step 6: Delete closure condition 3 and collapse condition 5**

In step 4's `Close only when **all** of:` list:

- **Delete** condition 3 (`` `SKIPPED` is empty — a known, user-declined follow-up… ``) in full.
- **Renumber** old condition 4 → **3** and old condition 5 → **4**. The list now has four conditions.
- In new condition 3 (`FAILED` is empty), delete the clause `unlike `SKIPPED` it is expected to resolve itself` — there is no longer a `SKIPPED` to contrast with. It becomes: `a follow-up whose filing failed is not yet finished, and it is expected to resolve itself: step 1a retries every `FAILED` item on each recovery invocation…`
- **Replace** new condition 4 (old 5) with the collapsed single-sentinel form:

```markdown
4. The deferred-item triage is not the **unknown** sentinel (step 2, when `REVIEW_REPORT` arrived absent). This is a distinct failure mode from condition 3, not a rephrasing of it: that fails when there is a *known* outstanding item; this fails when there is *no way to know* whether one exists. An absent `REVIEW_REPORT` must never read as "nothing was filed or failed" — that reading is exactly the bug this condition exists to close off, since it would let a merged-then-interrupted recovery run close an epic over real outstanding work purely because the evidence never reached this invocation.

   **This condition guards one unknown, where a previous revision guarded two.** It formerly checked `SKIPPED` and `FAILED` independently. Now that a drop is a decision rather than an outstanding item, the only thing an absent `REVIEW_REPORT` hides is whether unfiled `file` items exist — a single unknown. The reduction is deliberate, not a simplification of the kind this file elsewhere warns against: it follows from `DROPPED` leaving the blocking set, and it must be reverted if `DROPPED` ever becomes blocking again.

   Record which condition (if any) failed — step 5 states it plainly in that entry's `Next` line. On the already-recorded path (step 1a matched), this condition still applies whenever the matched entry's sentinel could not be resolved this invocation either. It does **not** apply when step 1a's `FAILED` came from a concrete historical list, or from a sentinel this invocation resolved against a current `REVIEW_REPORT`. The sentinel must never be treated as permanently cleared because a prior invocation once restored it: each invocation re-evaluates it independently in step 1a.
```

- Update the closing sentence `When all five hold` → `When all four hold`, and `refusing to close under condition 4 or 5` → `refusing to close under condition 3 or 4`.

- [ ] **Step 7: Update step 5's log lines and the `UNKNOWN` parse rule**

Replace the `**Follow-ups skipped**` template line with:

```markdown
**Follow-ups dropped** — <item> — <rationale>, …                   (omit the line when DROPPED is empty. When DROPPED is the **unknown** sentinel, write the line as the literal `UNKNOWN — review report unavailable`.)
```

In the `Next` line's options, replace the `condition 4` / `condition 5` references with `condition 3` / `condition 4` to match Step 6's renumbering.

In the `UNKNOWN` token paragraph, replace `on either follow-up line` with:

```markdown
on either follow-up line — `**Follow-ups dropped**` or its legacy spelling `**Follow-ups skipped**`, and `**Follow-ups failed to file**`
```

- [ ] **Step 8: Verify the renumbering by hand**

Run: `grep -n 'condition' plugins/notion-dev/skills/epic-update/SKILL.md`
Read every hit. Confirm no reference to "condition 5" survives, that every numeric reference points at the intended condition after renumbering, and that no sentence still contrasts a condition with `SKIPPED`.

- [ ] **Step 9: Run it to verify it passes**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED`

- [ ] **Step 10: Commit**

```bash
git add scripts/verify-convergence.sh plugins/notion-dev/skills/epic-update/SKILL.md
git commit -m "fix(epic-update): a declined follow-up no longer blocks epic closure forever

epic-update now consumes only REVIEW_REPORT's FILED list. Since arriving
items are already triaged 'file', the interactive gate's Skip becomes Drop
— a recorded decision, not outstanding work — so closure condition 3 is
deleted and conditions renumber to four.

Condition 5's two-sentinel structure collapses to one: with DROPPED
non-blocking, an absent REVIEW_REPORT hides a single unknown. The step-1a
parser still recognizes the legacy '**Follow-ups skipped**' log line, so
epics written before this change keep recovering."
```

---

### Task 7: non-interactive contract, docs, worked trace, version bumps

`--non-interactive` is the mode clients spend most of their time in and the largest behavioral change for them, so it gets stated explicitly rather than left to inference.

**Files:**
- Modify: `plugins/notion-dev/commands/create-task.md:102` (non-interactive one-item mode)
- Modify: `plugins/notion-dev/README.md:191`, `:201`, `:203`
- Modify: `docs/superpowers/specs/2026-08-28-convergence-design.md` (append the worked trace its Verification section requires)
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json` (`0.12.2` → `0.13.0`), `plugins/quick-dev/.claude-plugin/plugin.json` (`0.7.2` → `0.8.0`)
- Modify: `scripts/verify-convergence.sh`

**Interfaces:**
- Consumes: everything from Tasks 1-6.
- Produces: nothing — this is the closing task.

- [ ] **Step 1: Add the failing assertions**

In `scripts/verify-convergence.sh`, insert before the final `echo`:

```bash
echo "== Task 7: docs and versions =="
assert_has   "README describes absorb-first"   "$ND/README.md" 'absorb'
assert_lacks "README drops old epic claim"     "$ND/README.md" 'no follow-ups are outstanding'
assert_has   "create-task notes file-only"     "$ND/commands/create-task.md" 'already triaged `file`'
assert_has   "notion-dev version bumped"       "$ND/.claude-plugin/plugin.json" '"version": "0.13.0"'
assert_has   "quick-dev version bumped"        "$QD/.claude-plugin/plugin.json" '"version": "0.8.0"'
assert_has   "spec carries a worked trace"     docs/superpowers/specs/2026-08-28-convergence-design.md 'Appendix: worked trace'

# The spec requires that no plugin invent a synonym for the vocabulary.
for S in $ND/skills/plan-review/SKILL.md $QD/skills/plan-review/SKILL.md \
         $ND/skills/plan-review/references/reviewer-rubric.md \
         $QD/skills/plan-review/references/reviewer-rubric.md \
         $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md \
         $ND/skills/epic-update/SKILL.md; do
  n=${S#plugins/}
  assert_lacks "$n avoids synonym 'fold in'"   "$S" 'fold in'
  assert_lacks "$n avoids synonym 'inline it'" "$S" 'inline it'
done
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-convergence.sh`
Expected: FAIL — 6 new failures. The 14 synonym assertions pass already (no copy uses those phrases today); they are regression guards for the edits in Tasks 1, 2, 3, and 6, not red/green steps.

- [ ] **Step 3: State the non-interactive contract in `create-task.md`**

Append to the non-interactive-mode paragraph:

```markdown
Under absorb-by-default triage, this mode no longer receives every deferred item — an item reaching here has already been triaged `file` upstream, with a blast-radius criterion recorded. Non-interactive runs absorb by default exactly as interactive ones do; what `--non-interactive` removes is the *confirmation prompt* on a `file` item, never the triage itself.
```

- [ ] **Step 4: Update the `notion-dev` README**

Replace the `**Follow-ups land in the same Epic.**` bullet with:

```markdown
- **Most review findings never become tickets.** When a review turns up work the ticket did not plan for, the flow triages it: `absorb` (do it now, in this PR — the default), `file` (its own ticket, only when it reaches code outside the PR, needs a new interface/dependency/config/migration, or needs a decision the acceptance criteria do not settle), or `drop` (recorded with a rationale, never built). Absorbed work is gated: `/notion-dev:ticket` will not merge while an `absorb` item is outstanding. Only `file` items become real tickets, and they land under the same Epic.
```

Replace the closure sentence:

```markdown
When the last unresolved child resolves and no follow-ups are outstanding, the Epic's own status moves to `Implemented`.
```

with:

```markdown
When the last unresolved child resolves and no filing has failed, the Epic's own status moves to `Implemented`. A follow-up you decline at the filing prompt is recorded as a **drop** — a decision, which closes work rather than blocking the Epic indefinitely.
```

Update the `## Resolution Log` row's description from `follow-ups filed, how many tasks remain` to `follow-ups filed and dropped, how many tasks remain`.

- [ ] **Step 5: Append the worked trace to the spec**

Append to `docs/superpowers/specs/2026-08-28-convergence-design.md`:

```markdown
## Appendix: worked trace

Ticket `STO-41` ("Add token refresh to the session handler"), superpowers flow, epic
"Session Hardening". Its PR touches `src/session/handler.ts` and `src/session/token.ts`.

**Plan review** turns up three items:

| Item | Label | Why |
|---|---|---|
| "Cover the refresh path in the existing session test" | `absorb` | No criterion true — the test file is in the plan's declared set |
| "Rate-limit the refresh endpoint" | `file` (criterion 2) | Needs a new config key |
| "Rename `sess` to `session` throughout" | `drop` | Cosmetic churn under the judgment bar |

Emitted as `TRIAGE-COMPLETE: yes` plus three triage lines. The `absorb` item is appended to
`PLAN.md` as a task and built by `subagent-driven-development` — no gate needed.
`## Not in scope` gets the rate-limit item with "criterion 2". `PLAN.md` is deleted at 6.6;
the `file` and `drop` items survive in the ticket's `## Implementation` **Notes** (6.5).

**Code review** turns up two more:

| Item | Label | Why |
|---|---|---|
| "The TTL comparison is off by one" | `absorb` | Same file as the fix |
| "Session storage should move to Redis" | `file` (criterion 1) | Reaches the storage layer, outside the diff |

The absorb gate at merge step 5 holds until the TTL fix is pushed and reviewed; the round cap
bounds that. `REVIEW_REPORT` records `ABSORBED` = [TTL fix], `FILED` = [Redis, rate-limit],
`DROPPED` = [rename].

**Phase 8.** `epic-update` receives **only** `FILED` — two items, not five. Both file. The
user drops the rate-limit one at the prompt with "already tracked in infra backlog"; it lands
in `DROPPED` and does **not** block closure. The Redis ticket is created, so closure
condition 1 fails and the epic stays open — correctly, because real work is outstanding.

The ticket's `## Merged` section shows **Absorbed** (2), **Deferred follow-ups** (1, with its
ID), and **Dropped** (2, with rationales). Five findings; **one new ticket**. Under the old
design, all five would have been filed.
```

- [ ] **Step 6: Bump both plugin versions**

Both changes are behavioral and backward-compatible in configuration, so both are minor bumps:

```bash
sed -i 's/"version": "0.12.2"/"version": "0.13.0"/' plugins/notion-dev/.claude-plugin/plugin.json
sed -i 's/"version": "0.7.2"/"version": "0.8.0"/'   plugins/quick-dev/.claude-plugin/plugin.json
```

- [ ] **Step 7: Run the full harness**

Run: `./scripts/verify-convergence.sh`
Expected: `ALL CHECKS PASSED` — every assertion from Tasks 1-7.

- [ ] **Step 8: Commit**

```bash
git add scripts/verify-convergence.sh plugins/notion-dev/README.md \
        plugins/notion-dev/commands/create-task.md \
        plugins/*/.claude-plugin/plugin.json \
        docs/superpowers/specs/2026-08-28-convergence-design.md
git commit -m "docs(notion-dev): document absorb-first triage; bump plugin versions

States the non-interactive contract explicitly — absorb-by-default applies
there too; --non-interactive removes the confirmation prompt on a file
item, not the triage. Updates the README's epic-closure claim, which no
longer holds now that a drop is a decision. Adds the worked end-to-end
trace the spec's Verification section requires.

notion-dev 0.12.2 → 0.13.0, quick-dev 0.7.2 → 0.8.0."
```

---

## Not in scope

- Epic-scope admission testing for follow-ups (ruled out during design).
- Unifying the four diverged shared skills — a refactor riding a behavioral fix.
- Any change to `task-breakdown`, whose anti-split discipline is already correct.
- Any change to the review loops' round cap, oscillation guard, or judgment bar.
- Migrating existing Notion epics. The step-1a dual-spelling parser makes them recover
  correctly; nothing rewrites their history.
