# Completeness Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a close-time gate that holds a merge when the ticket's own acceptance criteria are unmet, a completeness claim is unsupported, or a stated caveat carries no triage label.

**Architecture:** One new hard gate in both `review-and-merge` copies, fed by a new `--criteria-file` argument. A fresh `general-purpose` verifier returns a keyed block; the *gate*, not the verifier, resolves every citation — running command citations, grepping test citations, content-matching code citations. Unmet items enter the `absorb` / `file` / `drop` triage the Absorb gate already holds. `notion-dev` gets its criteria from Notion; `quick-dev` derives and freezes them at `flow-triage` before the build.

**Tech Stack:** Markdown instruction files (Claude Code plugin skills and commands). No application code, no package manager, no test framework. `scripts/verify-completeness.sh` — `grep -F` and `diff` structural assertions — is the test suite.

**Spec:** `docs/superpowers/specs/2026-08-28-completeness-design.md`

## Global Constraints

- **This repo ships markdown, not code.** There is no build, no `npm test`, no runtime. `./scripts/verify-completeness.sh` and `./scripts/verify-convergence.sh` are the only test commands; both must be green at the end of every task.
- **Vocabulary is fixed and literal.** Triage labels: `absorb` / `file` / `drop`, lowercase and backticked. Report list names: `ABSORBED` / `FILED` / `DROPPED`, uppercase. Verdicts: `met` / `not-met` / `unverified`, lowercase and backticked. Never invent synonyms ("satisfied", "partial", "unchecked").
- **`unverified` is a third state.** It is not `met` and not `not-met`. Never collapse it into either. This mirrors `epic-update`'s `unknown` sentinel and the ledger's null-not-zero rule: *we did not check* must never render as *there was nothing to find*.
- **Never reference a gate by ordinal in prose.** The gate list itself is a numbered markdown list and inserting into it renumbers the items below — that is expected. What must never appear is a *cross-reference* by number ("re-satisfy gates 1-3"): gates are named in prose ("the Absorb gate", "the caller's pre-merge check"). An enumeration goes stale the next time a gate is inserted — this repo already had to fix exactly that defect once.
- **The two plugins' shared skills have DIVERGED.** `review-and-merge/SKILL.md`, `develop`/`ticket.md`, and `flow-triage/references/ledger.md` differ between `plugins/notion-dev` and `plugins/quick-dev`. Edit each copy separately. **Never `cp` one over another.** Line numbers differ too: `## 5. Merge` is `notion-dev:406` and `quick-dev:390`; the local reviewer spawn is `notion-dev:390` and `quick-dev:374`.
- **`plan-review/references/reviewer-rubric.md` must stay byte-identical between plugins.** This plan does not modify it; do not touch it.
- **Ledger fields are `null`, never `0`, when nothing was measured.** `0` is indistinguishable from "ran and found nothing".
- **`NONE` is the literal value for an empty output block**, so an absent block is distinguishable from one that found nothing.
- **Every key of a keyed output block is present even on the degraded path.** Callers parse the whole block.
- **Overlapping files across tasks.** `commands/ticket.md`, `commands/finalize.md`, and `quick-dev/skills/develop/SKILL.md` are each touched by two tasks (5 or 4, then 6). Task 6 only appends ledger fields and a report sentence; it must not restructure what the earlier task wrote.

---

## File structure

**Create:**
- `scripts/verify-completeness.sh` — the harness for this change. A sibling of `verify-convergence.sh`, not an extension of it: that script is a stable regression net for a shipped change and must keep localising its own failures.

**Modify — `plugins/notion-dev`:**
- `skills/ticket-system/SKILL.md` — new `refreshAcceptanceCriteria` operation (the Notion write path)
- `skills/review-and-merge/SKILL.md` — `--criteria-file`, the verifier, citation resolution, the Completeness gate
- `commands/ticket.md` — write the criteria file, pass the argument, consume the report, ledger, final report
- `commands/finalize.md` — the same, at its own phases
- `skills/flow-triage/references/ledger.md` — four new fields
- `README.md`, `.claude-plugin/plugin.json`

**Modify — `plugins/quick-dev`:**
- `skills/flow-triage/SKILL.md` — `CRITERIA:` and `COVERAGE-MAP:` output blocks
- `skills/develop/SKILL.md` — freeze the criteria, pass the argument, `Unmet:` trailers, final report
- `skills/review-and-merge/SKILL.md` — same gate as `notion-dev`'s copy, applied to diverged text
- `skills/flow-triage/references/ledger.md` — four new fields
- `README.md`, `.claude-plugin/plugin.json`

---

### Task 1: `ticket-system` — the acceptance-criteria write path

**Files:**
- Create: `scripts/verify-completeness.sh`
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `refreshAcceptanceCriteria(id, verdicts)` → `void`. `verdicts` is an ordered list matching the criteria file line-for-line, each entry `{ criterion, verdict }` where `verdict` ∈ `met` | `not-met` | `unverified`. Task 5 calls this.

- [ ] **Step 1: Create the harness with its first failing assertions**

Create `scripts/verify-completeness.sh`, `chmod +x` it:

```bash
#!/usr/bin/env bash
# Structural verification for the completeness gate.
# This repo ships markdown instruction files, not code — these greps are the
# test suite. Run from anywhere: ./scripts/verify-completeness.sh
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

echo "== Task 1: ticket-system write path =="
TS=$ND/skills/ticket-system/SKILL.md
assert_has "ticket-system tables refreshAcceptanceCriteria" "$TS" '| `refreshAcceptanceCriteria` |'
assert_has "refreshAcceptanceCriteria has its own section"  "$TS" '## refreshAcceptanceCriteria(id, verdicts)'
assert_has "it renders from the criteria file"              "$TS" 'never from the verifier'
assert_has "it owns the Acceptance Criteria format"         "$TS" 'single owner of the `Acceptance Criteria` section'

if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-completeness.sh`
Expected: `4 CHECK(S) FAILED` — all four strings are absent today.

- [ ] **Step 3: Add the row to the Logical operations table**

In `plugins/notion-dev/skills/ticket-system/SKILL.md`, in the `## Logical operations` table, insert this row immediately **after** the `refreshEpicTasks` row (they are siblings — both re-render a to-do section from computed state):

```
| `refreshAcceptanceCriteria` | `id`, `verdicts` | `void` — re-renders the ticket's `## Acceptance Criteria` to-do blocks with each box ticked or unticked per its verdict. The single owner of the `Acceptance Criteria` section's format after creation, for the same reason `refreshEpicTasks` owns `## Tasks`: two callers write it (`/notion-dev:ticket` Phase 8 and `/notion-dev:finalize` Phase 3) and would otherwise drift apart. Renders criterion text from the caller's criteria file, **never from the verifier's summary**. No-op when the ticket has no `## Acceptance Criteria` section. |
```

- [ ] **Step 4: Add the operation section**

Insert a new `## refreshAcceptanceCriteria(id, verdicts)` section immediately **after** the `## refreshEpicTasks(epicId)` section and before `## appendToSection(id, sectionName, content)`:

```markdown
## refreshAcceptanceCriteria(id, verdicts)

Re-renders the ticket's `## Acceptance Criteria` section as to-do blocks, ticking each box that its verdict marks `met`. **The single owner of the `Acceptance Criteria` section's format** after creation — `/notion-dev:ticket` Phase 8 and `/notion-dev:finalize` Phase 3 both write it, and without one owner they drift apart exactly as `refreshEpicTasks` exists to prevent for `## Tasks`.

`verdicts` is an ordered list matching the caller's criteria file line-for-line: `{ criterion, verdict }` with `verdict` ∈ `met` | `not-met` | `unverified`.

1. `fetchTicket(id)` → `pageId`. If the page has no `## Acceptance Criteria` section, return without writing. A ticket may legitimately have none (`/notion-dev:finalize` accepts any PR), and inventing the section here would fabricate a definition of done.
2. Render one Notion to-do block per entry, in the given order:

```
- [x] Three tests pass under `npm run test:unit`
- [ ] The error message names the offending field
```

   The box is ticked when and only when `verdict` is `met`. Both `not-met` and `unverified` render unticked — they are different states, but neither is met, and the distinction is carried by the `Completeness` record in `## Implementation`, which is where a rationale can actually be read.
3. **Take each criterion's text verbatim from `verdicts[].criterion`, which the caller sourced from the criteria file — never from the verifier's summary or any paraphrase of it.** `upsertSection` replaces a section's children wholesale, so a paraphrase anywhere on this path would silently rewrite the ticket's own definition of done. That is the worst available failure in a change whose entire purpose is to stop "done" being quietly altered.
4. `upsertSection(id, "Acceptance Criteria", <rendered blocks>)`.

Safe to call repeatedly: the rendering is a pure function of `verdicts`, and `upsertSection` replaces only up to the next top-level heading, so `## Implementation` and `## Merged` below are never touched.
```

- [ ] **Step 5: Run it to verify it passes**

Run: `./scripts/verify-completeness.sh`
Expected: `ALL CHECKS PASSED` (4 assertions).

Also run `./scripts/verify-convergence.sh` — expected `ALL CHECKS PASSED`, unchanged.

- [ ] **Step 6: Commit**

```bash
git add scripts/verify-completeness.sh plugins/notion-dev/skills/ticket-system/SKILL.md
git commit -m "feat(ticket-system): add refreshAcceptanceCriteria, the write path for criteria verdicts

Acceptance criteria render into Notion as real to-do blocks and nothing has
ever ticked them. This adds the operation that does, alongside
refreshEpicTasks and for the same ownership reason: two callers write the
section, so one owner keeps them from drifting.

It renders criterion text from the caller's criteria file, never from a
verifier summary — upsertSection replaces a section wholesale, so a
paraphrase on this path would silently rewrite the ticket's own definition
of done."
```

---

### Task 2: `review-and-merge` — the verifier, citation resolution, and the gate

**Files:**
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md`
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md`
- Modify: `scripts/verify-completeness.sh`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: the `--criteria-file <path>` argument, and a `COMPLETENESS-REPORT` section in the skill's final report carrying the keyed block below. Tasks 4, 5, and 6 consume both.

**The two files have diverged.** Apply the same *content* to both, but read each file's surrounding text and match it. Do not diff or copy one onto the other.

- [ ] **Step 1: Add the failing assertions**

In `scripts/verify-completeness.sh`, before the final `if [ "$fails" -eq 0 ]`:

```bash
echo "== Task 2: completeness gate =="
for RM in $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md; do
  n=${RM#plugins/}
  assert_has "$n documents --criteria-file"          "$RM" '--criteria-file'
  assert_has "$n dispatches the verifier"            "$RM" 'completeness verifier'
  assert_has "$n states the anti-circularity rule"   "$RM" 'never cite the deliverable'
  assert_has "$n names the Completeness gate"        "$RM" 'Completeness gate'
  assert_has "$n resolves citations gate-side"       "$RM" 'the gate resolves every citation'
  assert_has "$n matches code citations by content"  "$RM" 'by content, never by line number'
  assert_has "$n defines the unverified state"       "$RM" '`unverified`'
  assert_has "$n files unverified when degraded"     "$RM" 'unverified — completeness check degraded'
  assert_has "$n emits the COMPLETENESS key"         "$RM" 'COMPLETENESS:'
  assert_has "$n uses NONE for empty blocks"         "$RM" 'the literal `NONE`'
done
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-completeness.sh`
Expected: 20 new failures (10 assertions × 2 files), 24 total run.

- [ ] **Step 3: Document the new argument**

In each file's `## Input` section, extend the arguments sentence so it also names `--criteria-file <path>`, then add this paragraph beneath it:

```markdown
`--criteria-file <path>` names a file holding the run's acceptance criteria, one per line, verbatim in their authoritative wording. It feeds the Completeness gate in `## 5. Merge`. **When it is absent** — `quick-dev` local mode, a manually opened PR, a ticket with no `## Acceptance Criteria` section — the gate still runs its claim and caveat charges and reports `CRITERIA-TOTAL: 0`. It degrades; it never becomes a hard failure, and it must never report criteria as met when it had none to check.
```

- [ ] **Step 4: Add the verifier subsection**

Insert a new `### The completeness verifier` subsection at the end of `## 4. Review loop`, immediately before `## 5. Merge`:

````markdown
### The completeness verifier

Dispatched by the Completeness gate below. A fresh `general-purpose` agent, synchronous — the gate needs the verdict before it can decide — spawned the same way the local review loop spawns its reviewer, and for the same reason: independence from the party that believes the work is done.

Pass these as **file paths, not inline text**: the criteria file, the diff (`origin/<baseRefName>...HEAD`), the PR body, and the verification output already produced during the loop. Pass **nothing** from the implementer — not the plan, not the run's narrative, not prior reasoning. That exclusion is the point of the seat.

Its three charges:

1. **Per-criterion verdict.** `met` or `not-met` for each line of the criteria file, each with a **citation**: a command and its output, a named test and its result, or a quoted span with `file:line`. A `met` verdict carrying no citation is malformed output, not a passing criterion. Restating the criterion, "the implementation handles this", and pointing at a plan that said it would are all non-citations.

2. **Unsupported completeness claims**, over text **this pull request changed** — not the whole repository. The finding is the **missing referent, not the claim**: report only "this text says X exists, is handled, is mitigated, or is durable; I looked for X and it is absent or materially different." A true claim produces no finding, so honest prose costs nothing.

3. **Untriaged caveats.** Any stated gap, caveat, or known limitation — in the PR body or in docs this PR changed — carrying no `absorb` / `file` / `drop` label. A labeled caveat is fine and produces no finding. A limitation may exist; it may not exist unlabeled.

**The anti-circularity rule: the verifier may never cite the deliverable's own claims as evidence.** The PR body, the spec, and the changed docs are what charge 2 is auditing. Admitting them as proof under charge 1 would let a false claim validate itself, and charges 1 and 2 would confirm each other instead of checking anything.

Its output block, ending its response:

```
COMPLETENESS: <clean | blocked | degraded>
CRITERIA-TOTAL: <n>
CRITERIA-MET: <n>
CRITERIA-NOT-MET: <n>
CRITERIA-UNVERIFIED: <n>
VERDICTS:
- [<met|not-met>] <criterion verbatim> — <command|test|code>: <citation>
CLAIMS:
- <file:line> — claims <X>; <X> is absent or differs because <…>
CAVEATS:
- <where found> — <the caveat verbatim>
TRIAGE:
- [<absorb|file|drop>] <item> — <rationale; `file` cites its blast-radius criterion number>
```

`VERDICTS` / `CLAIMS` / `CAVEATS` / `TRIAGE` each take the literal `NONE` when empty, so an absent block is distinguishable from one that found nothing. Every key appears even on the degraded path.

**Contract check.** The output is usable only if every key is present, `CRITERIA-TOTAL` equals the criteria file's line count, and `CRITERIA-MET + CRITERIA-NOT-MET + CRITERIA-UNVERIFIED == CRITERIA-TOTAL`. A mismatch is a degradation, never a silent truncation.

**Citation resolution — the gate resolves every citation, not the verifier.** A `met` verdict is a claim until the gate confirms it:

- **Command citation** — the gate runs the command. The criterion is decided by exit status and output; no agent judgment is involved.
- **Test citation** — the named test must appear, passing, in the verification output the gate already holds.
- **Code citation** — the quoted span must appear in that file in the diff. Match **by content, never by line number**: a correct verdict whose line drifted by two must not be punished, and matching the span is stricter about substance while looser about position.

A citation that does not resolve demotes its criterion to `unverified` — **not** to `not-met`. The verifier may have been right and merely sloppy in citing; the honest statement is that the gate could not confirm it.

**Degradation.** If the agent fails, or its output fails the contract check, retry **once** with the same prompt. If it fails again, emit `COMPLETENESS: degraded` with every key present and every criterion counted in `CRITERIA-UNVERIFIED`. Then:

- **Interactive** — stop and ask. The run has genuinely failed to establish whether the work is done, and that deserves a human rather than a default.
- **Non-interactive** — record each unverified criterion as a `file` item with the reason `unverified — completeness check degraded`. It becomes tracked follow-up work rather than an absence.

Passing the gate on degradation would be a silent bypass, and a silent bypass of a completeness gate is the exact failure this gate exists to remove. Blocking on it would deadlock merges behind a flaky agent. `unverified` is neither.
````

- [ ] **Step 5: Add the gate**

In `## 5. Merge`, insert this immediately **after** the Absorb gate and **before** the config pre-merge checks gate. Renumber the two gates that follow it, and change nothing else about them:

```markdown
4. **Completeness gate**: **Nothing incomplete may be unlabeled at merge.**

   Run the completeness verifier (see `## 4. Review loop`), resolve its citations, and
   triage what it returns. Every `not-met` criterion, every unsupported completeness
   claim, and every untriaged caveat becomes an item on the same two axes as any review
   finding: `absorb` — the default, because for an unmet criterion the ticket said it
   would do this — `file` citing a blast-radius criterion number, or `drop` with a
   rationale. `absorb` items are then held by the Absorb gate above; this gate adds no
   second enforcement mechanism.

   For an acceptance criterion, `file` and `drop` are **scope reductions**, not deferrals
   of extra work. The caller records them where the work is tracked, not only in the PR.

   `absorb` items are fixed, pushed, and re-checked. **The verifier runs at most twice.**
   Pass 2 covers only the criteria that came back `not-met` or `unverified`, against only
   the new commits — bounding both cost and wall-clock. Anything still unresolved after
   pass 2 must be reclassified to `file` or `drop` with a rationale. As with the Absorb
   gate, the escape always exists, so this gate cannot deadlock a non-interactive run.
```

- [ ] **Step 6: Carry the block into the final report**

In the closing paragraph of `## 5. Merge`, where the report's three triage lists are specified, add:

```markdown
The report also carries a **`COMPLETENESS-REPORT`** section: the verifier's keyed block verbatim, with each `met` verdict's citation replaced by the gate's resolution of it. Callers depend on this — `/notion-dev:ticket` and `/notion-dev:finalize` tick the ticket's to-do boxes from `VERDICTS`, and every caller writes its counts to the ledger. When no verifier ran, the section is present and reads `COMPLETENESS: degraded` with its reason, never absent.
```

- [ ] **Step 7: Run it to verify it passes**

Run: `./scripts/verify-completeness.sh`
Expected: `ALL CHECKS PASSED`, 24 assertions.

- [ ] **Step 8: Commit**

```bash
git add scripts/verify-completeness.sh plugins/notion-dev/skills/review-and-merge/SKILL.md plugins/quick-dev/skills/review-and-merge/SKILL.md
git commit -m "feat(review-and-merge): add the completeness gate

Nothing incomplete may be unlabeled at merge. Unmet acceptance criteria,
unsupported completeness claims, and untriaged caveats all become items in
the absorb/file/drop vocabulary, and the Absorb gate holds them — no second
enforcement mechanism.

The load-bearing part is that the GATE resolves citations, not the verifier:
it runs command citations, greps test citations against verification output
it already holds, and content-matches code citations against the diff. A met
verdict is a claim until the gate confirms it, and an unresolvable citation
demotes to unverified rather than to not-met.

The verifier may never cite the deliverable's own claims as evidence.
Without that rule the criteria check and the claim audit confirm each other
instead of checking anything.

A degraded verifier yields unverified — not met, not not-met. Passing on
degradation would be the silent bypass this gate exists to remove; blocking
would deadlock merges behind a flaky agent."
```

---

### Task 3: `quick-dev:flow-triage` — derive and freeze the criteria

**Files:**
- Modify: `plugins/quick-dev/skills/flow-triage/SKILL.md`
- Modify: `scripts/verify-completeness.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: two new keys in the Step 7 output block — `CRITERIA:` (3–6 lines) and `COVERAGE-MAP:`. Task 4 parses both.

- [ ] **Step 1: Add the failing assertions**

```bash
echo "== Task 3: quick-dev criteria derivation =="
FT=$QD/skills/flow-triage/SKILL.md
assert_has "flow-triage emits CRITERIA"           "$FT" 'CRITERIA:'
assert_has "flow-triage emits COVERAGE-MAP"       "$FT" 'COVERAGE-MAP:'
assert_has "flow-triage caps the criteria count"  "$FT" '3-6 observable criteria'
assert_has "flow-triage marks uncovered clauses"  "$FT" 'not covered'
assert_has "flow-triage freezes before the build" "$FT" 'before any code exists'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-completeness.sh`
Expected: 5 new failures, 29 total run.

- [ ] **Step 3: Add the derivation step**

Add a new numbered item to `## Step 7 — Confirm, record, output`, **before** the existing `1. **Confirm**` item, and renumber the three that follow:

```markdown
1. **Derive the acceptance criteria.** From the feature description alone — not from the scout findings or the micro-plan, which describe what *we* intend rather than what was *asked for* — state **3-6 observable criteria**: conditions a reader could check against the finished work without trusting the run's own account of it.

   Then build the **coverage map** in the other direction: quote every substantive clause of the feature description and name the criterion covering it. A clause deliberately left uncovered gets an entry saying `not covered` and why.

   The map is what catches weak criteria. Weakness never shows up as a bad-looking criterion — it shows up as part of the request that no criterion mentions, and only directional coverage makes that visible. The 3-6 cap is binding: a rambling description is explained in the map, never inflated into a dozen criteria.

   This runs **before any code exists**, which is what stops the criteria being reverse-engineered from what was built. In interactive mode the user sees them in the confirmation below — they are the authority on what they asked for, and this is the only point in the flow where they can say so before there is code to defend.
```

- [ ] **Step 4: Add the output keys**

In the Step 7 output block, add these two keys immediately after `DRIFT:` and before `SCOUT-FINDINGS:`:

```
CRITERIA:
- <observable criterion>
COVERAGE-MAP:
- "<clause quoted from the feature description>" -> criterion <n>
- "<clause quoted from the feature description>" -> not covered — <why>
```

Then extend the sentence beneath the block that begins "`FLOW:` reflects `flow_chosen`" with:

```markdown
`CRITERIA:` is the run's frozen definition of done — callers write it to a criteria file before the build and never regenerate it afterwards. On `--advise-only` both blocks are still emitted; on a forced flow they are still emitted, since neither depends on the scout.
```

- [ ] **Step 5: Run it to verify it passes**

Run: `./scripts/verify-completeness.sh`
Expected: `ALL CHECKS PASSED`, 29 assertions.

- [ ] **Step 6: Commit**

```bash
git add scripts/verify-completeness.sh plugins/quick-dev/skills/flow-triage/SKILL.md
git commit -m "feat(quick-dev): derive and freeze acceptance criteria at triage

quick-dev has no ticket, so it has no definition of done to check at merge.
Triage now states 3-6 observable criteria from the feature description
before the build starts — the timing is the defence, since criteria authored
after the fact are criteria the run knows it met.

The coverage map runs the other direction, quoting each clause of the request
and naming the criterion covering it. Weakness shows up as an uncovered
clause, never as a bad-looking criterion, so only directional coverage makes
it visible. Interactive runs show both in the confirmation prompt that
already exists, putting the user on the definition of done before there is
code to defend."
```

---

### Task 4: `quick-dev:develop` — freeze, pass, and record

**Files:**
- Modify: `plugins/quick-dev/skills/develop/SKILL.md`
- Modify: `scripts/verify-completeness.sh`

**Interfaces:**
- Consumes: `CRITERIA:` and `COVERAGE-MAP:` from Task 3; `--criteria-file` and `COMPLETENESS-REPORT` from Task 2.
- Produces: `Unmet:` commit trailers, and the Phase 6 report sentence.

- [ ] **Step 1: Add the failing assertions**

```bash
echo "== Task 4: quick-dev develop wiring =="
D=$QD/skills/develop/SKILL.md
assert_has "develop writes a criteria file"        "$D" 'criteria-<SLUG>.md'
assert_has "develop freezes criteria in the PR"    "$D" 'The PR body is the freeze'
assert_has "develop passes --criteria-file"        "$D" '--criteria-file'
assert_has "develop writes Unmet: trailers"        "$D" 'Unmet:'
assert_has "develop reports unmet criteria"        "$D" 'acceptance criteria were not met'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-completeness.sh`
Expected: 5 new failures, 34 total run.

- [ ] **Step 3: Persist the frozen criteria (Phase 2a)**

At the end of `### 2a — Triage (choose the flow)`, after the sentence recording `FLOW`, `MICRO_PLAN`, and `SCOUT_FINDINGS`, add:

```markdown
Also record `CRITERIA` (the `CRITERIA:` block) and `COVERAGE_MAP` (the `COVERAGE-MAP:` block), and write `CRITERIA` — one criterion per line, verbatim, no bullet markers — to `$REPO_ROOT/.claude/quick-dev/criteria-<SLUG>.md` (`mkdir -p` plus the self-ignoring `.gitignore` first, commands in `../flow-triage/references/ledger.md`, so it never appears in `git status`). This happens **before** `2b — Build`: the criteria are the run's definition of done, and a definition of done written after the work is not one.
```

- [ ] **Step 4: Freeze them in the PR body (Phase 3)**

In `## Phase 3 — Ship`, where the PR body is composed, add:

```markdown
Include the frozen acceptance criteria verbatim under an `## Acceptance criteria` heading, alongside the plan review's `file` items already placed here. **The PR body is the freeze** — written before review, timestamped, and unaffected by any later edit to the criteria file.

Local mode has no PR, so its only freeze is the criteria file, which is editable. That is a real weakness of local mode rather than an oversight: it is bounded by the `Unmet:` trailers in step 5, which still record what was not met, so a weakened criterion leaves a visible absence of trailers rather than a silent pass.
```

- [ ] **Step 5: Pass the argument (Phase 4)**

In `## Phase 4 — Review and merge`, where `quick-dev:review-and-merge` is invoked, add `--criteria-file "$REPO_ROOT/.claude/quick-dev/criteria-<SLUG>.md"` to the args, and record its `COMPLETENESS-REPORT` section as `COMPLETENESS_REPORT`. Add:

```markdown
Omit `--criteria-file` when the file is absent (a resumed run that skipped 2a). The gate then runs its claim and caveat charges only — see that skill's `## Input`.
```

- [ ] **Step 6: Write the `Unmet:` trailers (local mode, step 5)**

In `**Local mode**` step 5, immediately after the paragraph introducing the `Deferred:` trailers, add:

```markdown
**A reduced criterion gets its own trailer.** Append one `Unmet:` line for every criterion the completeness gate did not settle as `met`:

    Unmet: <criterion verbatim> (<absorb|file|drop>; criterion <n>: <rationale>)

Met criteria get no trailer — the commit is the evidence. Keep this separate from `Deferred:` deliberately: a reduced acceptance criterion means *the stated definition of done shrank*, while a deferred review finding means *someone noticed extra work*. Folding them into one trailer erases that distinction, and the first is the more serious signal. `git log --grep '^Unmet:'` answers a sharper question than `git log --grep '^Deferred:'`.
```

- [ ] **Step 7: Report it (Phase 6)**

In `## Phase 6 — Verify and report`, add a bullet after `**Triage outcome**`:

```markdown
- **Completeness outcome** — from `COMPLETENESS_REPORT`. When any criterion is not `met`, state it: "<n> of <m> acceptance criteria were not met at the completeness gate", then list each with its verdict, its triage label, and its rationale. State `CRITERIA-UNVERIFIED` separately whenever it is non-zero — `unverified` means the gate could not check, which is not the same as finding the work undone, and collapsing the two is the distinction this gate exists to preserve. Say nothing when every criterion is `met`. In GitHub mode the record itself is the PR comment `review-and-merge` posted; this report is the readable summary of it.
```

- [ ] **Step 8: Run it to verify it passes**

Run: `./scripts/verify-completeness.sh`
Expected: `ALL CHECKS PASSED`, 34 assertions.

- [ ] **Step 9: Commit**

```bash
git add scripts/verify-completeness.sh plugins/quick-dev/skills/develop/SKILL.md
git commit -m "feat(quick-dev): wire the completeness gate through develop

Criteria are written to a file at 2a before the build and copied verbatim
into the PR body at ship, so the PR body is the freeze — unaffected by any
later edit to the file. Local mode has no PR and therefore a weaker freeze;
that is stated rather than papered over.

Every criterion not settled as met becomes an Unmet: trailer on the squash
commit, kept separate from Deferred: on purpose. A reduced acceptance
criterion means the stated definition of done shrank; a deferred finding
means someone noticed extra work. One trailer for both would erase the more
serious of the two signals."
```

---

### Task 5: `notion-dev` callers — criteria in, verdicts back to Notion

**Files:**
- Modify: `plugins/notion-dev/commands/ticket.md`
- Modify: `plugins/notion-dev/commands/finalize.md`
- Modify: `scripts/verify-completeness.sh`

**Interfaces:**
- Consumes: `refreshAcceptanceCriteria(id, verdicts)` from Task 1; `--criteria-file` and `COMPLETENESS-REPORT` from Task 2.
- Produces: nothing later tasks consume beyond the ledger inputs Task 6 reads.

- [ ] **Step 1: Add the failing assertions**

```bash
echo "== Task 5: notion-dev caller wiring =="
for C in $ND/commands/ticket.md $ND/commands/finalize.md; do
  n=${C#plugins/}
  assert_has "$n writes a criteria file"          "$C" 'criteria-<KEY>-<id>.md'
  assert_has "$n passes --criteria-file"          "$C" '--criteria-file'
  assert_has "$n ticks the acceptance criteria"   "$C" 'refreshAcceptanceCriteria'
  assert_has "$n records a Completeness block"    "$C" 'Completeness'
  assert_has "$n reports unmet criteria"          "$C" 'acceptance criteria were not met'
done
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-completeness.sh`
Expected: 10 new failures, 44 total run.

- [ ] **Step 3: Write the criteria file**

In `ticket.md` Phase 1.1 (after the ticket is fetched) and in `finalize.md` Phase 1 step 5 (after `fetchTicket(id)`), add:

```markdown
Write the ticket body's `## Acceptance Criteria` list — one criterion per line, verbatim, with the `- [ ]` markers stripped — to `$REPO_ROOT/.claude/notion-dev/criteria-<KEY>-<id>.md`, in the self-ignored directory the ledger, the rescued `PLAN.md`, and the persisted review report already share (`mkdir -p` plus its `.gitignore`, commands in `skills/flow-triage/references/ledger.md`). Record the path as `CRITERIA_FILE`.

**Nothing is authored here.** The criteria come from Notion, which no part of this run can weaken. That is what makes them worth gating on.

When the body has no `## Acceptance Criteria` section, or it is empty, write no file and leave `CRITERIA_FILE` unset. `/notion-dev:create-task` guards against that state, but this command accepts any ticket and must not invent a definition of done for one that has none.
```

- [ ] **Step 4: Pass the argument**

In `ticket.md` Phase 7 and `finalize.md` Phase 2, where `notion-dev:review-and-merge` is invoked, add `--criteria-file "<CRITERIA_FILE>"` to the args — **only when `CRITERIA_FILE` is set** — and record the skill's `COMPLETENESS-REPORT` section as `COMPLETENESS_REPORT` alongside `REVIEW_REPORT`.

Persist it with `REVIEW_REPORT`: append the `COMPLETENESS-REPORT` block to the same `review-report-<KEY>-<id>.md` file, under a `## Completeness` heading, so `/notion-dev:finalize`'s post-merge recovery path finds it. Best-effort, exactly like the existing write — a failure here never fails the run.

- [ ] **Step 5: Tick the boxes and record the evidence**

In `ticket.md` Phase 8.3 and `finalize.md` Phase 3.3, add:

```markdown
From `COMPLETENESS_REPORT`'s `VERDICTS` block, build `verdicts` — one entry per criteria-file line, in file order, `{ criterion, verdict }` — and call `refreshAcceptanceCriteria(id, verdicts)` via `notion-dev:ticket-system`. Take each `criterion` from `CRITERIA_FILE`, **not** from the verdict line's echo of it: the file is the verbatim copy fetched from Notion, and a paraphrase written back would silently rewrite the ticket's own definition of done. Skip entirely when `CRITERIA_FILE` was unset or the report is absent — an unticked box means "not met", and writing one for a ticket that never had criteria would assert something false.

Then `appendToSection(id, "Implementation", …)` with a **Completeness** block: each criterion, its verdict, the gate's resolved citation, and — for any criterion escaped to `file` or `drop` — its label and rationale. Append rather than upsert: Phase 6.5 wrote `## Implementation` before the merge, and a replacing write here would clobber its Plan / Implementation / Files Changed / PR / Branch / Plan review / Notes fields.

For an acceptance criterion, `file` and `drop` are **scope reductions**, not deferrals of extra work — which is why they land on the ticket rather than only in the PR. Someone tracking this work must be able to see that its stated definition of done shrank.
```

- [ ] **Step 6: Report it**

In `ticket.md` Phase 10 and `finalize.md` Phase 5, add to the final report:

```markdown
- **Completeness** — when any criterion is not `met`: "<n> of <m> acceptance criteria were not met at the completeness gate", then each with its verdict, triage label, and rationale. State `CRITERIA-UNVERIFIED` separately whenever it is non-zero: `unverified` means the gate could not check, which is not the same as finding the work undone. Say nothing when every criterion is `met`.
```

- [ ] **Step 7: Run it to verify it passes**

Run: `./scripts/verify-completeness.sh`
Expected: `ALL CHECKS PASSED`, 44 assertions.

- [ ] **Step 8: Commit**

```bash
git add scripts/verify-completeness.sh plugins/notion-dev/commands/ticket.md plugins/notion-dev/commands/finalize.md
git commit -m "feat(notion-dev): check the acceptance criteria at close and tick them

The ticket has stated its own definition of done as to-do blocks since the
beginning and nothing ever read it back — status flipped on a merged PR, not
on met criteria, and the boxes stayed unticked permanently.

Both callers now write the criteria to a file, pass it to the merge gate, and
write the verdicts back: boxes ticked via refreshAcceptanceCriteria, evidence
and any escape rationale appended to ## Implementation. Criterion text comes
from the file, never from the verifier's echo of it.

For an acceptance criterion, file and drop are scope reductions rather than
deferrals, which is why they land on the ticket instead of only in the PR."
```

---

### Task 6: Ledger fields and the calibration signal

**Files:**
- Modify: `plugins/notion-dev/skills/flow-triage/references/ledger.md`
- Modify: `plugins/quick-dev/skills/flow-triage/references/ledger.md`
- Modify: `plugins/notion-dev/commands/ticket.md` (its `### Ledger outcome` block)
- Modify: `plugins/notion-dev/commands/finalize.md` (its `### Ledger outcome` block)
- Modify: `plugins/quick-dev/skills/develop/SKILL.md` (its `**Ledger outcome**` bullet)
- Modify: `scripts/verify-completeness.sh`

**Interfaces:**
- Consumes: `COMPLETENESS_REPORT` from Tasks 4 and 5.
- Produces: nothing.

**The two `ledger.md` files have diverged. Edit each separately; never `cp`.** This task appends to sections Tasks 4 and 5 already edited — do not restructure their work.

- [ ] **Step 1: Add the failing assertions**

```bash
echo "== Task 6: completeness metrics =="
for L in $ND/skills/flow-triage/references/ledger.md $QD/skills/flow-triage/references/ledger.md; do
  n=${L#plugins/}
  assert_has "$n documents completeness_criteria"   "$L" 'completeness_criteria'
  assert_has "$n documents completeness_unverified" "$L" 'completeness_unverified'
done
assert_has "ticket.md writes completeness counts"   "$ND/commands/ticket.md"      'completeness_criteria'
assert_has "finalize.md writes completeness counts" "$ND/commands/finalize.md"    'completeness_criteria'
assert_has "develop writes completeness counts"     "$QD/skills/develop/SKILL.md" 'completeness_criteria'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-completeness.sh`
Expected: 7 new failures, 51 total run.

- [ ] **Step 3: Extend both ledger schemas**

In EACH `ledger.md`, in the `## Format` section's field notes, add a bullet after the `triage_*` bullet:

```markdown
- `completeness_criteria` / `completeness_met` / `completeness_unverified` / `completeness_items` — the completeness gate's outcome: how many acceptance criteria it evaluated, how many settled as `met` after the gate resolved their citations, how many it could not settle at all, and how many items it raised across its three charges. `completeness_unverified` is the health signal for the check itself — a run that cannot verify its own criteria has not passed them, and a rising rate means the verifier or its citations are failing rather than the work improving. Compare `completeness_met` against `completeness_criteria`, never against the item count. All four are `null` — never `0` — wherever no completeness check ran: a run with no criteria file and no changed prose, or one that stopped before the gate. `0` would be indistinguishable from a check that ran and found everything met, which is the opposite conclusion. Added after the original schema; readers must tolerate their absence in older lines.
```

Also add the four fields to that file's example `outcome` JSON line, immediately after the `triage_*` fields:

```
,"completeness_criteria":4,"completeness_met":4,"completeness_unverified":0,"completeness_items":0
```

- [ ] **Step 4: Write the counts (three sites)**

In `ticket.md`'s `### Ledger outcome`, `finalize.md`'s `### Ledger outcome`, and `develop/SKILL.md`'s `**Ledger outcome**` bullet: append the same four fields to each example JSON line, and extend the "metrics come from" sentence with:

```markdown
The four `completeness_*` counts come from `COMPLETENESS_REPORT`'s `CRITERIA-TOTAL` / `CRITERIA-MET` / `CRITERIA-UNVERIFIED` keys, with `completeness_items` counting its `TRIAGE` entries. Write `null` for all four — never `0` — when no completeness check ran.
```

Adapt only the surrounding wording each file needs; do not restructure those sections or alter what Tasks 4 and 5 wrote.

- [ ] **Step 5: Run it to verify it passes**

Run: `./scripts/verify-completeness.sh`
Expected: `ALL CHECKS PASSED`, 51 assertions.

- [ ] **Step 6: Commit**

```bash
git add scripts/verify-completeness.sh plugins/notion-dev/skills/flow-triage/references/ledger.md plugins/quick-dev/skills/flow-triage/references/ledger.md plugins/notion-dev/commands/ticket.md plugins/notion-dev/commands/finalize.md plugins/quick-dev/skills/develop/SKILL.md
git commit -m "feat: record completeness metrics in both ledgers

Four fields following the triage_* precedent including its null-not-zero
rule: criteria evaluated, criteria met, criteria the gate could not settle,
and items raised.

completeness_unverified is the health signal for the check itself. A run
that cannot verify its own criteria has not passed them, and a rising rate
means the verifier or its citations are failing rather than the work getting
better — a distinction zero-instead-of-null would erase."
```

---

### Task 7: Documentation, versions, and the full harness

**Files:**
- Modify: `plugins/notion-dev/README.md`
- Modify: `plugins/quick-dev/README.md`
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json`
- Modify: `plugins/quick-dev/.claude-plugin/plugin.json`
- Modify: `scripts/verify-completeness.sh`

**Interfaces:**
- Consumes: everything.
- Produces: nothing.

- [ ] **Step 1: Add the failing assertions**

```bash
echo "== Task 7: docs and versions =="
assert_has "notion-dev README covers the gate" "$ND/README.md" 'completeness gate'
assert_has "quick-dev README covers the gate"  "$QD/README.md" 'completeness gate'
assert_has "notion-dev version bumped"         "$ND/.claude-plugin/plugin.json" '"version": "0.14.0"'
assert_has "quick-dev version bumped"          "$QD/.claude-plugin/plugin.json" '"version": "0.9.0"'
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/verify-completeness.sh`
Expected: 4 new failures, 55 total run.

- [ ] **Step 3: Document it in `plugins/notion-dev/README.md`**

Add a bullet beside the existing "Most review findings never become tickets" bullet:

```markdown
- **A ticket closes against what it said it would do.** The `## Acceptance Criteria` you wrote are checked at merge, not assumed: each is `met` with a citation the gate itself resolves — running the command, matching the quoted code against the diff — or it becomes an item in the same `absorb` / `file` / `drop` triage. Met criteria get their Notion to-do boxes ticked; escaped ones stay unticked with the rationale recorded on the ticket, because reducing a ticket's criteria is a scope change and belongs where the work is tracked. The same completeness gate reports any claim in the change that names something absent, and any stated caveat carrying no triage label.
```

- [ ] **Step 4: Document it in `plugins/quick-dev/README.md`**

```markdown
- **The run states its definition of done before it starts.** Triage derives 3-6 observable acceptance criteria from your feature description — with a coverage map naming every clause of the request and which criterion covers it — and freezes them in the PR body before any code exists. At merge, the completeness gate checks each one, and anything not met becomes an `absorb` / `file` / `drop` item rather than a silent omission. Locally, unmet criteria land as `Unmet:` trailers on the squash commit, so `git log --grep '^Unmet:'` shows where a definition of done shrank.
```

- [ ] **Step 5: Bump both versions**

`plugins/notion-dev/.claude-plugin/plugin.json`: `"version": "0.13.0"` → `"version": "0.14.0"`.
`plugins/quick-dev/.claude-plugin/plugin.json`: `"version": "0.8.0"` → `"version": "0.9.0"`.

Minor bumps: `--criteria-file` is optional and the gate degrades without it, so no caller breaks.

- [ ] **Step 6: Run BOTH harnesses**

```bash
./scripts/verify-completeness.sh   # ALL CHECKS PASSED, 55 assertions
./scripts/verify-convergence.sh    # ALL CHECKS PASSED, unchanged
```

Both must be green. If `verify-convergence.sh` regressed, a task edited text the convergence change owns — fix that rather than weakening its assertion.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/README.md plugins/quick-dev/README.md plugins/notion-dev/.claude-plugin/plugin.json plugins/quick-dev/.claude-plugin/plugin.json scripts/verify-completeness.sh
git commit -m "docs: document the completeness gate; bump both plugins

notion-dev 0.13.0 -> 0.14.0, quick-dev 0.8.0 -> 0.9.0. Minor, not major:
--criteria-file is optional and the gate degrades to its claim and caveat
charges without it, so no existing caller breaks."
```

---

## Verification summary

| Task | New assertions | Running total |
|---|---|---|
| 1 — `ticket-system` write path | 4 | 4 |
| 2 — the gate, both copies | 20 | 24 |
| 3 — `quick-dev` criteria derivation | 5 | 29 |
| 4 — `quick-dev:develop` wiring | 5 | 34 |
| 5 — `notion-dev` caller wiring | 10 | 44 |
| 6 — ledger metrics | 7 | 51 |
| 7 — docs and versions | 4 | 55 |

**What this harness does not do.** It constrains vocabulary, wiring, and parity. It cannot verify that the gate behaves correctly, because nothing in this repository can execute a skill. Semantic correctness rests on review — as it does for every change here, and as `scripts/verify-convergence.sh` states about itself.
