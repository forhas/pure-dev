# Completeness gate: close a ticket against what it said it would do

**Date:** 2026-08-28
**Status:** Implemented. Plan: `../plans/2026-08-28-completeness.md`; both were executed on the `completeness` branch and ship in the same pull request as this document.
**Scope:** `plugins/notion-dev`, `plugins/quick-dev`
**Problem statement:** `2026-08-28-completeness-problem-statement.md`
**Related:** `2026-08-28-convergence-design.md` — the same leak, a different exit. This design reuses its triage vocabulary, its gate position, and its escape semantics.

## The problem, in one paragraph

A ticket states its own definition of done as `## Acceptance Criteria`, in explicitly checkable form, rendered into Notion as real to-do blocks. Nothing ever reads it back. `updateStatus(id, "implemented")` fires on a merged pull request, not on met criteria, so the boxes stay unticked forever and "most of what the ticket asked for" closes as "the ticket." Separately, a limitation the *author* writes into a spec, plan, or PR body is never labeled at all: the `absorb` / `file` / `drop` triage governs review findings, and a self-declared caveat is not a review finding. Both are incompleteness that no gate holds. The problem statement documents both with file:line evidence and three worked instances from the session that produced the convergence change.

## What this design asserts

**At merge time, nothing incomplete may be unlabeled.**

That is one sentence and one gate. Every unmet acceptance criterion, every unsupported completeness claim, and every stated caveat becomes an item in the vocabulary already shipping — `absorb` (do it now), `file` (its own ticket, citing a blast-radius criterion), `drop` (recorded with a rationale, never built). The existing Absorb gate then holds them. No new enforcement machinery is introduced; the merge block is the one that already exists.

### Design principles

1. **The gate checks artifacts; the agent only judges what needs judgment.** Wherever a verdict can be settled by running a command or matching text, the gate settles it. An agent's assertion is the fallback, not the mechanism.
2. **Not-checked is never rendered as nothing-found.** A third state, `unverified`, is distinct from both `met` and `not-met` — the same distinction `epic-update`'s `unknown` sentinel and the ledger's null-not-zero rule already draw.
3. **An escape always exists.** The convergence gate was built so a non-interactive run cannot deadlock. This one keeps that property: anything the gate holds can be reclassified, at the cost of a recorded rationale.
4. **A true statement produces no finding.** Charges that flag honest prose impose a tax on every run and get worked around. Every charge here fires only on a demonstrated absence.

---

## 1. Architecture

### 1.1 Gate position

A **Completeness gate** joins the hard gates in `review-and-merge` `## 5. Merge` (`notion-dev/skills/review-and-merge/SKILL.md:406`; the `quick-dev` copy at `:390`), in both plugins. It sits after the Absorb gate and before the config pre-merge checks.

The numbered list renumbers, as any numbered list does when an item is inserted into it — `notion-dev`'s config pre-merge checks moves from 4 to 5 and the caller's check from 5 to 6. **No cross-reference breaks, because none uses ordinals.** The caller's pre-merge check already says to re-satisfy "every gate above," written ordinal-free precisely so a later insertion would not go stale — that phrasing was adopted in the convergence change after an enumeration silently omitted the Absorb gate.

### 1.2 A new argument

`review-and-merge` currently receives only a PR number plus optional `--non-interactive` and `--pre-merge-check` (`notion-dev/skills/review-and-merge/SKILL.md:13`). It has no knowledge that a ticket exists. It gains:

```
--criteria-file <path>
```

The file holds the run's acceptance criteria, one per line, verbatim, in their authoritative wording.

**Why a first-class argument rather than reusing `--pre-merge-check`.** That argument is prose evaluated to a pass/fail. The completeness gate must return *structured per-criterion verdicts* to the caller, because the caller writes them back to Notion. A prose channel cannot carry that.

**When the argument is absent** — a manually opened PR, invoked directly rather than through a ticket or feature flow, in either plugin; for `notion-dev`, a ticket with no `## Acceptance Criteria` section, or `finalize` reached with no recoverable ticket body; for `quick-dev`, a `develop` run whose criteria file was removed by hand between phases (it is gitignored and editable; a *resumed* run is not among these — the flow has no automatic resume) — the gate runs charges 2 and 3 (claims and caveats) and reports `CRITERIA-TOTAL: 0`. It degrades; it never becomes a hard failure, and it never silently reports "all criteria met." (`quick-dev` local mode is not among these cases: it never invokes `review-and-merge` at all — see §2.2 and §6.2.)

### 1.3 Data flow

```
criteria source ──► criteria file ──► review-and-merge --criteria-file
                                            │
                                            ├─► verifier agent (charges 1-3)
                                            │        │
                                            │        ▼
                                            │   keyed output block
                                            ▼        │
                                    citation resolution (gate-side, mechanical)
                                            │
                                            ▼
                                    met / not-met / unverified  +  claims  +  caveats
                                            │
                                            ▼
                              triage → absorb | file | drop → Absorb gate
                                            │
                                            ▼
                        durable artifacts (Notion boxes + Implementation, or PR comment + trailers)
```

---

## 2. Where the criteria come from

The two plugins differ here, for a reason that is worth stating rather than smoothing over.

### 2.1 `notion-dev` — Notion is authoritative

The criteria already exist and are not authored by the run. `ticket-interviewer` writes `## Acceptance Criteria` (`SKILL.md:129`), `ticket-system` renders it as to-do blocks (`SKILL.md:201` — "always a **to-do list** (`- [ ]` → Notion to-do blocks). Never plain bullets; the checkability is the point"), and `task-breakdown` carves it per task on a mission split (`SKILL.md:96`).

Both callers already fetch the ticket body:

- `/notion-dev:ticket` Phase 1.1 fetches it and passes it to planning at `:156`.
- `/notion-dev:finalize` Phase 1 step 5 calls `fetchTicket(id)` before Phase 2 invokes `review-and-merge`.

Each writes the `## Acceptance Criteria` list verbatim to `$REPO_ROOT/.claude/notion-dev/criteria-<KEY>-<id>.md` — the same self-ignored directory the ledger, the rescued `PLAN.md`, and the persisted review report already live in — and passes that path as `--criteria-file`.

**Nothing is authored by the run, so nothing can be weakened by it.** This is the strong case, and it is strong precisely because the source is external.

A ticket whose body has no `## Acceptance Criteria` section, or an empty one, writes no file and passes no argument. That is a real state — `create-task` guards against it (`create-task.md:69`) but `finalize` can be handed any PR. It degrades per §1.2.

### 2.2 `quick-dev` — derived, frozen before the build

`quick-dev`'s input is a free-form feature description (`develop/SKILL.md:18`). There is no authoritative source, so the run must produce one — which introduces the risk that it produces criteria it knows it will meet.

The defence is **when**, not **what**.

`quick-dev:flow-triage` gains two blocks in its Step 7 output (`flow-triage/SKILL.md:57`), which already carries `MICRO-PLAN:` and `SCOUT-FINDINGS:`:

```
CRITERIA:
- <observable criterion, 3-6 of them>
COVERAGE-MAP:
- "<clause quoted from the feature description>" -> criterion <n>
- "<clause quoted from the feature description>" -> not covered — <why>
```

Three properties follow from this placement:

1. **It happens before `2b — Build`.** Nothing has been written, so nothing can be reverse-engineered from what was written.
2. **A human sees it in interactive mode.** Step 7's confirmation prompt already exists and already presents the full output block; the criteria ride along at the cost of a few lines. The user is the authority on what they asked for, and this is the only point in the flow where they can say so before code exists.
3. **The coverage map is what catches weak criteria.** Weakness never appears as a bad-looking criterion — it appears as a clause of the request that no criterion mentions. Directional coverage makes that visible. `plan-review`'s rubric already mandates a `COVERAGE-MAP:` block, so this is an existing convention rather than a new one.

**The count is capped at 3-6.** A rambling feature description must not inflate into a dozen criteria; the coverage map explains any clause deliberately left uncovered rather than manufacturing a criterion for it. An uncovered clause with a stated reason is a design decision. An uncovered clause with no entry at all is a defect.

**The freeze.** `develop` Phase 2a writes the criteria to `$REPO_ROOT/.claude/quick-dev/criteria-<SLUG>.md`. Phase 3 (Ship) copies them verbatim into the PR body, alongside the plan review's `file` items it already places there. The PR body is the real freeze: written before review, timestamped, and unaffected by any later edit to the working file.

**Local mode has no PR, so its freeze is only the file, and the file is editable.** This is a genuine weakness, stated rather than papered over, and it is **unmitigated** — matching §10's "Genuinely residual" row rather than claiming a defence. The squash commit's `Unmet:` trailers (§6.2) do not bound it: a weakened criterion is one the gate then settles as `met`, met criteria get no trailer, so the commit is byte-identical to a genuinely complete run. The trailers record what was *not* met and cannot detect a criterion that was quietly made easier. Nothing in local mode can. The PR-body freeze is the only real defence this design has, and local mode does not have one.

---

## 3. The verifier

### 3.1 The seat

A fresh `general-purpose` agent, dispatched synchronously — the gate needs the verdict before it can decide. This mirrors the local review loop's existing reviewer (`notion-dev/skills/review-and-merge/SKILL.md:390`; `quick-dev` at `:374`), which is spawned the same way for the same reason.

It receives, as file paths rather than inline text: the criteria file, the diff (`origin/<base>...HEAD`), the PR body, and the output of the project's verification (`notion-dev`: the config `verify.steps` run the loop already performs at `notion-dev/skills/review-and-merge/SKILL.md:356`; `quick-dev`: the test/build command Phase 2c ran).

It never receives the implementer's reasoning, the plan, or the run's own narrative. Independence from the party that believes the work is done is the property this seat exists to provide.

**`quick-dev` local mode dispatches this same seat itself.** It never invokes `review-and-merge` (§1.2, §2.2, §6.2), so it has its own gate: `develop/SKILL.md` Phase 4 **step 4** — a local-mode Completeness gate, not a duplicate verifier. It spawns the same fresh `general-purpose` agent against the branch diff and instructs it to apply `review-and-merge`'s "The completeness verifier" subsection exactly as written — same three charges, same anti-circularity rule, same output block — then performs the gate-side citation resolution (§4), the triage and re-verify cap (§5), and the degradation handling (§7) itself, folding the items into `develop`'s own merge gate (step 5). One seat, one contract; two dispatchers.

**The verification output the gate resolves test citations against must be *retained* by whatever ran it.** In `review-and-merge` the loop retains its `verify.steps` / test output as `VERIFY_OUTPUT`, and the gate runs verification once itself when the loop never did — a clean run changes no code and so runs no verification, and a gate holding no output would demote every test citation to `unverified` and block a clean run. In local mode, `develop` Phase 2c retains its run as `VERIFY_OUTPUT` and step 4 falls back to it when neither review round re-ran tests.

### 3.2 Charge 1 — per-criterion verdict

For each criterion: `met` or `not-met`, with a **citation**. A `met` verdict without a citation is malformed output, not a passing criterion.

Acceptable citations, in the order the gate prefers them:

| Kind | Form | How the gate checks it (§4) |
|---|---|---|
| Command | the command, and its output | the gate runs it |
| Test | a test name, and its result | the name must appear, passing, in verification output the gate holds |
| Code | a quoted span with `file:line` | the quoted text must appear in that file in the diff |

Not acceptable: restating the criterion, "the implementation handles this", or citing a plan that said it would.

**The anti-circularity rule.** The verifier may never cite the deliverable's own claims as evidence. The PR body, the spec, and the changed docs are *under audit* by charge 2; admitting them as proof under charge 1 would let a false claim validate itself. This single rule is what keeps charges 1 and 2 from becoming mutually confirming, and it is the rule that makes the design work at all.

### 3.3 Charge 2 — unsupported completeness claims

Scoped to text **this pull request changed**. Auditing the whole repository every run would re-litigate everything and is not the goal.

The finding is **the missing referent, not the claim**. The verifier reports only:

> This text says X exists, is handled, is mitigated, or is durable. I looked for X, and it is absent or materially different.

A true claim produces no finding. The noise floor is zero, not "one `drop` per confident sentence." This framing is not a weakened audit — it is what actually caught the two instances the problem statement records:

- the convergence risk table stated the ledger "can count reclassifications per run"; **the counter did not exist**;
- `quick-dev/skills/develop/SKILL.md` called an ephemeral chat report `FILED` items' "only durable destination"; **a chat report is not a destination**.

Neither was flagged for its wording. Both were flagged because the named thing was not there.

### 3.4 Charge 3 — untriaged caveats

A limitation may exist. A limitation may not exist **unlabeled**.

The verifier reports any stated gap, caveat, or known limitation — in the PR body or in docs this PR changed — that carries no triage label. A caveat already labeled `absorb` / `file` / `drop` is fine and produces no finding.

A legitimate limitation is not blocked; it takes `drop` with its rationale, at a cost of one line. What is blocked is a limitation being *merely stated*, which is the behaviour that made the convergence PR's `## Known gaps` section survive to merge review with nothing requiring it to be empty.

**This charge has a specific existing target.** `ticket.md:286` defines the `Notes` field of the ticket's `## Implementation` section as "optional. Any caveats for the reviewer, plus the plan review's `TRIAGE:` **`file`** items with their criterion numbers." The `file` items carry criterion numbers; the caveats carry nothing. That is a designated caveat slot with no gate on it, in the shipped product, today.

### 3.5 Output contract

Following the convention `plan-review` established (`SKILL.md:124`): an uppercase keyed block, a caller-side contract check, retry once, and every key present even on the degraded path.

```
COMPLETENESS: <clean | blocked | degraded>
CRITERIA-TOTAL: <n>
CRITERIA-MET: <n>
CRITERIA-NOT-MET: <n>
CRITERIA-UNVERIFIED: <n>
VERDICTS:
- [<met|not-met|unverified>] <criterion verbatim> — <citation kind>: <citation>
CLAIMS:
- <file:line> — claims <X>; <X> is absent or differs because <…>
CAVEATS:
- <where found> — <the caveat verbatim>
TRIAGE:
- [<absorb|file|drop>] <item> — <rationale; `file` cites its blast-radius criterion number>
```

`NONE` is the literal value for an empty `VERDICTS` / `CLAIMS` / `CAVEATS` / `TRIAGE` block, so an absent block is distinguishable from a block that found nothing.

**`COMPLETENESS` is decided by the gate, never by the verifier** — the same reason the gate owns the counts (§4): the verifier cannot know which of its own citations resolved. `clean` means citation resolution left every criterion `met` and charges 2 and 3 found nothing, so the gate holds no item. `blocked` means the check ran and produced at least one item — any `not-met` or `unverified` criterion, any unsupported claim, any untriaged caveat — and the merge waits until each is absorbed or reclassified. `degraded` is §7's total-failure path. A block re-emitted after resolution reads `clean` when nothing is left; one that still reads `blocked` at merge means every remaining item was reclassified to `file` or `drop` with its rationale in `TRIAGE`, which is a labeled incompleteness — what this design produces, not what it prevents.

**Contract check.** The gate treats the output as usable only if every key is present, `CRITERIA-TOTAL` equals the criteria file's line count, `VERDICTS` carries exactly `CRITERIA-TOTAL` lines — one per criterion, in criteria-file order — and `MET + NOT-MET + UNVERIFIED == TOTAL`. A verdict count short of `CRITERIA-TOTAL` is not a criterion silently `met`; it is a mismatch, and a mismatch is a degradation, not a silent truncation.

---

## 4. Gate-side citation resolution

This is the section that separates this design from an agent promising it checked.

**Every citation is resolved by the gate, not by the verifier.** The verifier's `met` verdict is a claim; the gate's resolution is what makes it a fact.

1. **Command citations — the gate runs the command.** No agent judgment is involved. The criterion is decided by the exit status and output.
2. **Test citations — the gate greps the verification output it already holds.** The named test must appear, and must have passed.
3. **Code citations — the gate matches the quoted text against the file in the diff.** **By content, never by line number.** A correct verdict whose line drifted by two must not be punished; matching the quoted span is both stricter about substance and looser about position.

A citation that does not resolve demotes its criterion to **`unverified`**, a third state that is not `met` and not `not-met`. The verifier may have been right and merely sloppy in citing; the honest statement is that the gate could not confirm it. `unverified` has defined, safe handling both as an ordinary gate item (§5.1) and, when the verifier itself fails outright, on the degraded path (§7).

**The gate re-emits the block; it does not forward the verifier's copy.** The verifier's raw output is a claim, not the record. After resolution the gate produces the block that travels onward — to the report, and to §6's durable artifacts — with the verdict token corrected for any criterion it demoted (`met` → `unverified`), the four `CRITERIA-*` counts restated to match those corrected verdicts, and each surviving `met` verdict's citation replaced by the gate's own resolution of it. A caller consumes the gate's counts, never the verifier's: the verifier cannot know which of its own citations resolved, so its raw counts are provisional in exactly the cases that matter.

Two consequences worth naming:

- **The agent's surface shrinks.** Criteria with mechanical citations are settled by the gate. The verifier's judgment is load-bearing only where judgment is genuinely required.
- **Risk 1 changes character.** It stops being "will the agent be honest" and becomes "can a citation resolve against the wrong thing", which is a much narrower question.

---

## 5. Gate semantics

### 5.1 What the gate holds

Every `not-met` criterion, every `unverified` criterion, every unsupported claim, and every untriaged caveat becomes an item, triaged on the same two axes as any review finding. `unverified` is not a special case reserved for total verifier failure (§7) — a single citation that fails to resolve (§4) produces exactly one `unverified` item here, on an otherwise-clean run, and it is held exactly like any other item. An `unverified` criterion that raised no item would let the Absorb gate see nothing to hold and let it merge unlabeled — the precise failure this design exists to close.

**The default for both an unmet and an unverified criterion is `absorb`.** For `not-met`, the ticket said it would do this — doing it now is the expected resolution, not the exceptional one. For `unverified`, the usual remedy is cheaper than redoing the work: producing a citation that actually resolves — re-running the command, quoting the right span — because the underlying work may already be done and merely uncited.

### 5.2 Escapes

An item leaves the gate by reclassification, never by bypass:

- **`file`** — requires a blast-radius criterion number, exactly as the Absorb gate requires. For an acceptance criterion this is a **scope reduction**, and it is recorded on the ticket (§6.1), not only in the PR.
- **`drop`** — requires a rationale. Correct for a criterion that turned out wrong, irrelevant, or superseded, and for a legitimate stated limitation.

### 5.3 The re-verify cap

`absorb` items are fixed and pushed. **The gate stack then re-runs on the new HEAD, unconditionally** — this holds whether or not a caller supplied `--pre-merge-check`; that check's own "re-satisfy every gate above" is one instance of the rule, stated ordinal-free for the reason given in §1.1, not the rule's source.

**The verifier runs at most twice.** Pass 2 is scoped to only the criteria that came back `not-met` or `unverified` from pass 1 — but against **the new commits plus the original diff** for any criterion being re-cited, not the new commits alone. The remedy §5.1 states for `unverified` is a citation that actually resolves, and the work that citation points at is by definition in pass 1's commits; a pass 2 that saw only the new commits would face an empty diff for a pure re-citation, fail to resolve a second time, and systematically convert "we could not confirm it" into a recorded scope reduction for work that was already complete. Restricting *which criteria* pass 2 re-reads is what bounds it; restricting what they may cite would break it. Whichever state an item entered pass 2 in, if it is still `not-met` or `unverified` after pass 2 it must be reclassified to `file` or `drop` with a rationale.

This bounds both cost and wall-clock, and it preserves the property the convergence gate was deliberately built around: because the escape always exists, the gate cannot deadlock a non-interactive run.

**`quick-dev` local mode carries this same paragraph.** `develop` Phase 4 step 4 fixes its `absorb` items, re-runs its own check on the new HEAD against the full branch diff, caps itself at two passes, and reclassifies whatever remains — in non-interactive runs too. Without it `absorb` would be unreachable in local mode (a `not-met` criterion could only become a scope reduction or halt the run), and charge 3 — which fires on any stated caveat in changed docs, near-certain on the `superpowers` path whose specs carry an "Explicitly not claimed" section — would halt every non-interactive local run.

---

## 6. Durable artifacts

A verdict that lives only in a chat report is the graveyard problem this family of changes exists to fix.

### 6.1 `notion-dev`

**Tick the boxes.** A new `ticket-system` operation:

```
refreshAcceptanceCriteria(id, verdicts)
```

It re-renders the `## Acceptance Criteria` section's to-do blocks with each box ticked or unticked per its verdict, via `upsertSection` (`ticket-system/SKILL.md:411`).

**Why a new operation rather than callers calling `upsertSection` directly.** `refreshEpicTasks` exists for exactly this reason and states it outright: it is "**the single owner of that section's format** — callers never render it themselves, so `/notion-dev:create-task` and the epic-update flow cannot drift apart" (`SKILL.md:563`). Two callers write acceptance criteria — `ticket.md` Phase 8 and `finalize.md` Phase 3 — and the same drift is available to them. `refreshEpicTasks` is also the working precedent for ticking to-do boxes from a computed state, so the write path is proven, not hypothesised.

**It re-renders from the criteria file, never from the verifier's summary.** `upsertSection` replaces a section's children wholesale. A paraphrase anywhere on this path would silently rewrite the ticket's own definition of done — the worst available bug in a change about not quietly altering what "done" meant. The criteria file is the verbatim copy fetched from Notion; the verdicts contribute the box state and nothing else.

**Record the evidence.** `appendToSection(id, "Implementation", …)` (`SKILL.md:583`) with a `Completeness` block: each criterion, its verdict, its resolved citation, and for any escaped criterion its label and rationale.

**Append, not upsert.** `ticket.md:6.5` writes `## Implementation` *before* the merge; the completeness record arrives *after*. A replacing write at Phase 8 would clobber the Plan / Implementation / Files Changed / PR / Branch / Plan review / Notes fields written at 6.5. `appendToSection` is the operation built for "history must accumulate rather than be overwritten."

A dedicated `## Completeness` section was considered and rejected: it needs a palette row, an intro-callout decision, and zone-divider rules, to hold content answering the question `## Implementation` already exists to answer.

### 6.2 `quick-dev`

**GitHub mode** — the completeness record is posted as a PR comment, the same audit-trail-on-a-merged-PR pattern the local review loop already uses for its round findings (`quick-dev/skills/review-and-merge/SKILL.md:378`; `notion-dev`'s copy at `:394`). The frozen criteria are already in the PR body from Phase 3.

**Local mode** — one `Unmet:` trailer per not-met criterion on the squash commit, mirroring the `Deferred:` trailers the convergence change introduced. **The producer is local mode's own Completeness gate** (§3.1): `develop` Phase 4 **step 4** dispatches the verifier, resolves its citations, and records the resolved keyed block as `COMPLETENESS_REPORT`; **step 6** reads that block and writes one trailer per criterion the gate did not settle as `met`. Nothing in `review-and-merge` is involved on this path, and no other step writes these trailers.

```
Unmet: <criterion verbatim> (<absorb|file|drop>; criterion <n>: <rationale>)
```

Met criteria get no trailer — the commit is the evidence.

**Why a separate trailer rather than reusing `Deferred:`.** A reduced acceptance criterion means *the stated definition of done shrank*. A deferred review finding means *someone noticed extra work*. Folding them into one trailer erases the distinction, and the first is the more serious signal. `git log --grep '^Unmet:'` answers a different and sharper question than `git log --grep '^Deferred:'`.

---

## 7. Degradation and the `unverified` state

This section is the total-failure path: the verifier itself does not produce a usable result. It is distinct from the ordinary case (§4, §5.1) where the verifier succeeds and a single citation fails to resolve — that criterion is one `unverified` gate item among possibly-`met` others, defaults to `absorb`, and is handled by the normal re-verify cap (§5.3). Here, nothing the verifier returned can be trusted, so every criterion is `unverified` at once.

The verifier fails, its output is unparseable, or it fails the contract check. It is retried once with the same prompt. It fails again.

**Passing the gate here would be a silent bypass** — and a silent bypass of a completeness gate is precisely the failure this design exists to remove. **Blocking here would deadlock merges behind a flaky agent.**

Neither. Every criterion the gate could not settle becomes **`unverified`**, a third state that is not `met` and not `not-met`:

- **Interactive** — stop and ask. The run has genuinely failed to establish whether the work is done, and that is a fact worth a human's attention rather than a default. **Whatever the user decides, every unverified criterion still becomes an item** — `file` by default — carrying the user's own words as its rationale. "Merge anyway" is a rationale, not an exemption: the item is raised and the criterion is labeled either way. The user may reclassify an individual criterion to `drop` or hold it as `absorb`; what is not available is a merge that raises no items. Without this the interactive branch would be the design's last unlabeled-merge path — an unconstrained question, two lines above the paragraph forbidding exactly that.
- **Non-interactive** — each unverified criterion is recorded as a **`file`** item with the reason `unverified — completeness check degraded`. It becomes tracked follow-up work rather than an absence.

Both branches raise items; they differ only in who writes the rationale. This is principle 3 (§Design principles) applied to the degraded path: the escape exists, and it costs a recorded rationale.

`COMPLETENESS: degraded` is emitted with every key present and all counts in `CRITERIA-UNVERIFIED`.

This reuses a distinction the codebase already draws rather than inventing a third convention: `epic-update`'s `unknown` sentinel and the ledger's null-not-zero rule both exist to keep *we did not check* from rendering as *there was nothing to find*.

---

## 8. Metrics

Four fields join the `triage_*` family in both `flow-triage/references/ledger.md` copies, under the same null-not-zero rule:

| Field | Meaning |
|---|---|
| `completeness_criteria` | criteria the gate evaluated |
| `completeness_met` | settled `met` after citation resolution |
| `completeness_unverified` | could not be settled |
| `completeness_items` | items the gate raised across all three charges |

All four are `null` — never `0` — where no completeness check ran (no criteria file and no changed prose, or a run that stopped before the gate). `0` would be indistinguishable from a check that ran and found nothing.

**Kept to four deliberately.** The questions these must answer are "do runs reach the gate with work undone?" and "is the verifier actually running?". Separate claim and caveat counters would not change a decision.

**Surfaced in the run's own report** when `completeness_unverified` or `completeness_criteria - completeness_met` is non-zero, following the rule the reclassification counter established: a ledger nobody opens is not a signal.

---

## 9. Testing

A sibling `scripts/verify-completeness.sh`, reusing the `assert_has` / `assert_lacks` / `assert_identical` helpers from `scripts/verify-convergence.sh`.

**A sibling, not an extension.** `verify-convergence.sh` is scoped to a shipped change and is worth keeping as a stable regression net rather than growing into a general suite where a failure no longer localises. Both scripts must be green.

The assertions are structural — vocabulary present, parity between plugin copies, no stale tokens, every new key documented where callers parse it. As with the convergence harness, this constrains wording and wiring; it does not verify semantics. That limitation is stated here rather than discovered later.

**Rubric parity remains binding.** The two `plan-review/references/reviewer-rubric.md` copies stay byte-identical. The other shared skills have diverged between plugins and must be edited separately — never copied over one another.

---

## 10. Risks

| Risk | Mitigation | Residual |
|---|---|---|
| **A weak citation passes as proof.** The verifier asserts `met` and cites something irrelevant. | The gate resolves every citation itself (§4): it runs command citations, greps test citations against output it holds, and content-matches code citations against the diff. Unresolvable → `unverified`. The verifier's judgment is load-bearing only where no mechanical citation exists. | A code citation can quote a real span that does not actually establish the criterion. Narrower than the original risk, and the met-rate metric is the signal. Not eliminated. |
| **`quick-dev` criteria authored weak enough to pass.** | Criteria are frozen before `2b — Build`, copied verbatim into the PR body at ship, and accompanied by a directional coverage map naming every clause of the request and which criterion covers it. Interactive runs show them in `flow-triage`'s existing confirmation prompt. | Non-interactive runs have no human on the definition of done, and the coverage map is itself agent-produced. Local mode's freeze is a file, not a PR body. Genuinely residual. |
| **Cost — one independent agent seat per run, reading a diff.** | Reduced: pass 2 is scoped to previously-failing criteria against only the new commits; artifacts are passed as file paths, not inline; mechanically-cited criteria never reach the agent. | Not eliminated, and should not be. Every way to remove the seat — self-attestation, folding into the degraded-path local reviewer — removes the independence that caught all three documented instances. Paying for it is the design working. |
| **Charge 2 over-flags honest prose.** | Reframed: the finding is the *missing referent*, not the claim (§3.3). A true claim produces no finding, so the noise floor is zero rather than one `drop` per assertion. | A referent can be present but weaker than claimed, which is a judgment call. Expect some noise in the first runs. |
| **Citation resolution produces false blocks.** *(Introduced by this design.)* | Code citations match by **content, not line number**, so ordinary drift does not demote a correct verdict. An unresolvable citation goes to `unverified`, which is handled, rather than to `not-met`, which would block. | Odd formatting can still demote a correct verdict and add friction. |
| **The coverage map inflates the criteria count.** *(Introduced by this design.)* | The 3-6 cap is binding. The map explains any clause deliberately left uncovered rather than manufacturing a criterion for it. | A verbose feature description still produces more gate surface than a terse one. |

---

## 11. Worked trace: the three documented instances

The problem statement's evidence is three real instances from one session. A design that would not have caught them is not worth building.

**Instance 1 — a mitigation claimed but never built.** The convergence spec's risk table stated "the ledger can count reclassifications per run." No counter existed.

*Caught by charge 2.* The spec file was changed by that PR, so it is in scope. The claim names a specific referent — a per-run reclassification count in the ledger — and the verifier looks for it in `ledger.md`, finds no such field, and reports the missing referent. It becomes an item, defaults to `absorb`, and the Absorb gate holds the merge until the counter exists or the claim is corrected. In the real session this was caught by a whole-branch review reading skeptically, which the problem statement correctly calls luck.

**Instance 2 — a false durability claim.** `quick-dev/skills/develop/SKILL.md` described the run's ephemeral chat report as `FILED` items' "only durable destination."

*Caught by charge 2*, the same way. The named referent is a durable destination; the verifier looks for one and finds a chat report, which is materially different from what the sentence claims. Note that no keyword scan for limitation language would find this sentence — it asserts completeness, and its wording is confident.

**Instance 3 — a `## Known gaps` section nothing required to be empty.** The PR body listed two unresolved gaps and merged.

*Caught by charge 3.* Two stated limitations in the PR body carrying no triage label. Each becomes an item. Both would have defaulted to `absorb` and blocked the merge, or been escaped to `file` with a blast-radius criterion — which is what a human ultimately asked for by hand.

**And the symptom the whole design exists for:** a ticket whose `## Acceptance Criteria` listed four items, three of which the PR delivered. Charge 1 returns `not-met` for the fourth with no citation available, it defaults to `absorb`, and the merge waits. Today that ticket closes with the box unticked and the criterion unmentioned.

---

## 12. Explicitly not claimed

- **That this eliminates gaps.** It makes an unlabeled gap unable to reach a merge. A gap correctly labeled `file` or `drop` still exists — visibly, with a rationale, which is the goal the convergence design set and this one inherits.
- **That charge 2 finds every false claim.** It finds claims whose named referent the verifier looked for and could not find. A claim too vague to name a referent produces no finding, and vagueness is not currently gated.
- **That the harness verifies behaviour.** `verify-completeness.sh` asserts structure — wording, wiring, parity. Nothing in this repository can execute a skill, so semantic correctness rests on review, as it does for every change here.
- **That work absorbed at this gate is code-reviewed.** It is not. Completeness items arise *after* the review loop has ended, and §5.3's re-run re-runs the gate stack, not the loop — so a `not-met` criterion can cause new implementation at merge time whose only checks are CI, the other hard gates, and the verifier's second pass. The Absorb gate's "the absorbed change is pushed like any other fix and the next round reviews it" holds for review findings, which arise inside the loop; it does not hold for these. Re-entering the loop was rejected: each absorbed round can raise new completeness items and re-enter again, defeating the two-pass bound. The mitigation is a triage rule — prefer `file` over `absorb` when the fix is substantial new implementation rather than a citation, a doc correction, or a small completion — and it is a mitigation, not a closure. Both `review-and-merge` copies state this at the gate itself, where a reader of the gate meets it.
- **That `quick-dev` non-interactive runs get the same guarantee as `notion-dev`.** They do not. `notion-dev`'s criteria come from outside the run; `quick-dev`'s are produced by it. The coverage map narrows the gap; it does not close it.

---

## 13. Versions

Minor bumps in both plugins: `notion-dev` 0.13.0 → 0.14.0, `quick-dev` 0.8.0 → 0.9.0.

`--criteria-file` is optional and the gate degrades to charges 2 and 3 without it, so a caller that does not pass it continues to work. No breaking change.
