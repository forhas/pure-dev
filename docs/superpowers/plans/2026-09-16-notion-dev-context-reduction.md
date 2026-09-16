# notion-dev Context Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut ~48.4k tokens of instruction text out of the `/notion-dev:ticket` orchestrator's context by delegating Phases 8–10 to a subagent and splitting two oversized skills behind progressive disclosure.

**Architecture:** Three independent changes to markdown instruction files. Nothing here executes. (1) `/notion-dev:ticket` Phases 8–10 move into `commands/references/record.md` and are run by one dispatched `general-purpose` agent, with inline recovery when the dispatch fails. (2) `skills/ticket-system/SKILL.md` becomes a ~4k dispatcher plus five operation-clustered references, read on demand. (3) `issue-log`'s `signatures.md` is read on first record rather than up front.

**Tech Stack:** Markdown instruction files; `bash` verification harnesses under `scripts/verify-*.sh` using only `scripts/lib/assert.sh`.

**Spec:** `docs/superpowers/specs/2026-09-16-notion-dev-context-reduction-design.md`

## Global Constraints

- **The test suite is `scripts/verify-*.sh`.** Run **all** of them at the end of every task: `for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done`
- **Never hand-roll an assertion.** Every assertion comes from `scripts/lib/assert.sh`. `verify-assertions.sh` fails a harness that sources anything else or defines its own helper.
- **`assert_present` requires its regex to match exactly one line in its region.** A second match means the anchor is not pinning the place its label claims. Where a document cites the same mechanism N times on purpose, use `assert_count … <n>`.
- **The label is a claim the regex must honour.** Whatever the label names — a backticked literal, an ALL-CAPS key, a `--flag`, a `<placeholder>`, a capitalised mechanism name — must appear in the regex whenever the matched line says it too.
- **Two silent traps.** `awk -v` performs escape processing, so a written `\|` reaches the matcher as bare alternation matching every line — the library passes regexes through `ENVIRON` instead. And these files are **hard-wrapped**: a phrase spanning a line break can never match a line-based grep. Match the shortest distinctive fragment on one line.
- **Prove every new assertion can fail.** Break the file it guards, confirm `FAIL`, restore. **Commit before mutation-testing** — a `git checkout -- .` to undo mutations would otherwise revert the work.
- **Prefer standing invariants over version floors.** Floors rot, invariants do not.
- **One pull request.** Bump `plugins/notion-dev/.claude-plugin/plugin.json` `version` exactly once, at the end: **minor** (Task 11), because Task 9 adds a capability. Never merge a plugin PR whose version equals the base's.
- **Mirror is untouched.** `ticket-system`, `issue-log`, `epic-doc`, `epic-update` and `knowledge` are notion-dev-only — no `quick-dev` counterpart, nothing under `.claude/skills/`. If a task finds itself editing `plugins/quick-dev` or `.claude/skills`, it has gone wrong: stop and re-read the spec.
- **Branch:** work continues on `docs/notion-dev-context-reduction`, which already carries the spec (commits `2f8fdc7`, `934217f`, `e43cb2d`).

---

## File Structure

**Created:**
- `plugins/notion-dev/skills/ticket-system/references/config.md` — configuration resolution, property type handling, Notion page heading parsing
- `plugins/notion-dev/skills/ticket-system/references/styling.md` — palette, zone dividers, intro callouts, rich content, heading attribute preservation
- `plugins/notion-dev/skills/ticket-system/references/read-ops.md` — `fetchTicket`, `findEpics`, `getEpicContext`, `listEpicChildren`
- `plugins/notion-dev/skills/ticket-system/references/write-ops.md` — `updateTicket`, `updateStatus`, `setPullRequest`, `postComment`, `upsertSection`, `refreshAcceptanceCriteria`, `appendToSection`
- `plugins/notion-dev/skills/ticket-system/references/create-ops.md` — title prefix, epic containers, `resolveAssignee`, `createTicket`, `setDependencies`, `getSelectOptions`, `addSelectOption`, `createEpic`, `setParent`, `refreshEpicTasks`
- `plugins/notion-dev/commands/references/record.md` — `/notion-dev:ticket` Phases 8, 9 and 10's record step
- `scripts/verify-context-split.sh` — standing invariants for all three changes

**Modified:**
- `plugins/notion-dev/skills/ticket-system/SKILL.md` — reduced to a dispatcher
- `plugins/notion-dev/commands/ticket.md` — Phases 8–10 replaced by a dispatch site
- `plugins/notion-dev/skills/issue-log/SKILL.md` — `signatures.md` read moved to first record
- `plugins/notion-dev/README.md`, `plugins/notion-dev/.claude-plugin/plugin.json`
- `scripts/verify-ticket-system.sh`, `scripts/verify-runtime-feedback.sh`, `scripts/verify-completeness.sh`, `scripts/verify-epic-doc.sh`, `scripts/verify-knowledge.sh`, `scripts/verify-convergence.sh`, `scripts/verify-new-info.sh` — re-anchored

**Re-anchoring load, measured.** ~46 assertions across 7 harnesses currently point at `ticket-system/SKILL.md`: `verify-runtime-feedback.sh` 26, `verify-ticket-system.sh` 10, `verify-completeness.sh` 4, `verify-epic-doc.sh` 2, `verify-convergence.sh` 2, `verify-knowledge.sh` 1, `verify-new-info.sh` 1. Tasks 2–6 each move one reference file's worth and re-anchor only the assertions that moved with it, so the suite is green at the end of every task.

---

## Task 1: `signatures.md` is read on first record

Smallest change, fully independent of the rest. Do it first so the branch has a green baseline.

**Files:**
- Modify: `plugins/notion-dev/skills/issue-log/SKILL.md:20`
- Create: `scripts/verify-context-split.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/verify-context-split.sh` with the header, `ok`/`bad` helpers and the `. ./scripts/lib/assert.sh` source line. Tasks 7 and 10 append their sections to this same file.

- [ ] **Step 1: Read the current pointer**

```bash
sed -n '18,22p' plugins/notion-dev/skills/issue-log/SKILL.md
```

Line 20 currently reads (hard-wrapped — check the actual wrap before editing):

> **Layer 2 — enumerated sites.** The known degradation points carry explicit signature names, listed in `references/signatures.md`. Cite the registered name so common cases group instead of fragmenting into free-form prose.

- [ ] **Step 2: Create the harness with the failing assertion**

```bash
cat > scripts/verify-context-split.sh <<'SH'
#!/usr/bin/env bash
# Context split — progressive disclosure and the delegated record unit.
#
# Spec: docs/superpowers/specs/2026-09-16-notion-dev-context-reduction-design.md
#
# Three changes share this harness: issue-log reads its signature catalogue only
# when it is about to write an entry; ticket-system's operation index resolves to
# the reference file that owns each operation; and /notion-dev:ticket's record
# phase is dispatched with a bounded wait and an inline fallback.
#
# Standing invariants — no baseline, no version floor. Each goes red the moment
# the mechanism it names stops being in the document.
#
# Run from anywhere: ./scripts/verify-context-split.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
IL=$ND/skills/issue-log/SKILL.md
TS=$ND/skills/ticket-system/SKILL.md
TICKET=$ND/commands/ticket.md
RECORD=$ND/commands/references/record.md

# ---------------------------------------------------------------------------
echo "== issue-log: the signature catalogue is read on first record =="

assert_present "issue-log defers reading \`references/signatures.md\` to the first entry of the run" \
  "$IL" 1 60 'Read .references/signatures\.md. before writing the first entry'

exit $(( fails > 0 ))
SH
chmod +x scripts/verify-context-split.sh
```

- [ ] **Step 3: Run it to verify it fails**

Run: `./scripts/verify-context-split.sh`
Expected: `FAIL  issue-log defers reading ...`, exit 1. The imperative does not exist yet.

- [ ] **Step 4: Add the read imperative**

Edit `plugins/notion-dev/skills/issue-log/SKILL.md` line 20, appending to the Layer 2 sentence. Keep the file's existing hard wrap, and keep the whole matched fragment on one line:

```markdown
**Layer 2 — enumerated sites.** The known degradation points carry explicit signature names,
listed in `references/signatures.md`. Cite the registered name so common cases group instead of
fragmenting into free-form prose. **Read `references/signatures.md` before writing the first entry
of this run** — not on invoking this skill. It is a lookup catalogue consulted only when something
is actually being recorded, and a run with no degradations never needs it.
```

- [ ] **Step 5: Run it to verify it passes**

Run: `./scripts/verify-context-split.sh`
Expected: `PASS  issue-log defers reading ...`, exit 0.

- [ ] **Step 6: Run the whole suite**

```bash
for h in scripts/verify-*.sh; do "$h" >/dev/null 2>&1 || echo "FAILED: $h"; done; echo done
```
Expected: no `FAILED:` lines.

- [ ] **Step 7: Commit**

```bash
git add scripts/verify-context-split.sh plugins/notion-dev/skills/issue-log/SKILL.md
git commit -m "perf(notion-dev): read the signature catalogue on first record, not on load"
```

- [ ] **Step 8: Mutation-test the new assertion**

```bash
sed -i 's/Read `references\/signatures.md` before writing the first entry/Consult the catalogue/' \
  plugins/notion-dev/skills/issue-log/SKILL.md
./scripts/verify-context-split.sh; echo "exit=$?"   # expect FAIL, exit=1
git checkout -- plugins/notion-dev/skills/issue-log/SKILL.md
./scripts/verify-context-split.sh; echo "exit=$?"   # expect PASS, exit=0
```

---

## Task 2: extract `references/config.md`

**Files:**
- Create: `plugins/notion-dev/skills/ticket-system/references/config.md`
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md` — remove lines 114–176 and 188–191 (NOT 177–187, `## Project scoping guardrail`, which stays), add the pointer
- Modify: `scripts/verify-runtime-feedback.sh` — re-anchor the assertions that moved

**Interfaces:**
- Consumes: nothing.
- Produces: `references/config.md`, containing `## Configuration`, `## Property type handling` and `## Notion page heading parsing` verbatim. Tasks 3–6 follow this same extraction pattern and rely on the pointer wording established here.

- [ ] **Step 1: Record which assertions currently match inside the region being moved**

```bash
grep -n 'ticket-system' scripts/verify-runtime-feedback.sh | sed -n '1,40p'
awk 'NR>=114 && NR<=191' plugins/notion-dev/skills/ticket-system/SKILL.md | head -5
```

Note every assertion in any harness whose region overlaps `114,191`. Those are the ones this task re-anchors. Assertions whose regions lie outside it must not be touched.

- [ ] **Step 2: Extract the region verbatim**

```bash
cd plugins/notion-dev/skills/ticket-system
mkdir -p references
{
  printf '# ticket-system — configuration\n\n'
  printf 'Read before the first Notion call of any kind. Resolution rules for the configured\n'
  printf 'property names, how each Notion property type is written and read back, and how a\n'
  printf 'Notion page heading is parsed. Referenced from `../SKILL.md`.\n\n'
  sed -n '114,176p' SKILL.md      # Configuration + Property type handling
  sed -n '188,191p' SKILL.md      # Notion page heading parsing
  # 177-187 is `## Project scoping guardrail` -- it STAYS in SKILL.md, do not move it
} > references/config.md
cd -
```

- [ ] **Step 3: Remove the region from SKILL.md and leave the pointer**

Delete lines **188–191 first, then 114–176** (highest range first, so the earlier range stays
valid). Leave 177–187, `## Project scoping guardrail`, exactly where it is. Insert in place of
the 114–176 range:

```markdown
## Configuration, property types, page headings

Resolution of the configured property names, how each Notion property type is written and read
back, and Notion page heading parsing are in **`references/config.md`**. **Read it before the
first Notion call**; the property-type rules there are load-bearing — a value written in the wrong
shape is accepted by the API and read back wrong.
```

- [ ] **Step 4: Run the suite to see exactly what broke**

```bash
for h in scripts/verify-*.sh; do "$h" >/dev/null 2>&1 || echo "FAILED: $h"; done
```
Expected: `FAILED: scripts/verify-runtime-feedback.sh` (and any other harness whose region covered 114–191). This failure is the signal that tells you which assertions moved — do not skip it.

- [ ] **Step 5: Re-anchor each broken assertion to `config.md`**

For each failing assertion, change its file variable and region to the new file. Add near the top of `scripts/verify-runtime-feedback.sh`, beside the existing `TS=` line:

```bash
TSCFG=$ND/skills/ticket-system/references/config.md
```

Then for each moved assertion, replace `"$TS" <start> <end>` with `"$TSCFG" 1 "$(total_lines "$TSCFG")"`, leaving the label and regex unchanged. The label still names the same mechanism, so `assert_covers` still holds.

- [ ] **Step 6: Run the suite to verify green**

```bash
for h in scripts/verify-*.sh; do "$h" >/dev/null 2>&1 || echo "FAILED: $h"; done; echo done
```
Expected: no `FAILED:` lines.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/skills/ticket-system scripts/verify-runtime-feedback.sh
git commit -m "refactor(notion-dev): move ticket-system configuration into references/config.md"
```

- [ ] **Step 8: Mutation-test one re-anchored assertion**

```bash
sed -i '10d' plugins/notion-dev/skills/ticket-system/references/config.md
./scripts/verify-runtime-feedback.sh >/dev/null 2>&1; echo "exit=$?"   # expect non-zero
git checkout -- plugins/notion-dev/skills/ticket-system/references/config.md
./scripts/verify-runtime-feedback.sh >/dev/null 2>&1; echo "exit=$?"   # expect 0
```

---

## Task 3: extract `references/styling.md`

Same shape as Task 2. Region: `## Styling conventions`, lines 192–286 of the **original** `SKILL.md` — recompute the current line numbers with `grep -n '^## ' SKILL.md` after Task 2's deletion shifted them.

**Files:**
- Create: `plugins/notion-dev/skills/ticket-system/references/styling.md`
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md`
- Modify: `scripts/verify-new-info.sh` (the `Notes` row palette assertion), `scripts/verify-convergence.sh` (`Absorbed` / `Dropped` rendering)

**Interfaces:**
- Consumes: the pointer wording from Task 2.
- Produces: `references/styling.md` containing `## Styling conventions` and its `###` subsections (`Palette per section`, `Zone dividers`, `Intro callouts`, `Rich content inside sections`, `Heading attribute preservation`) verbatim.

- [ ] **Step 1: Recompute the region**

```bash
grep -n '^## ' plugins/notion-dev/skills/ticket-system/SKILL.md | grep -A1 'Styling conventions'
```

- [ ] **Step 2: Extract verbatim**

```bash
cd plugins/notion-dev/skills/ticket-system
{
  printf '# ticket-system — styling conventions\n\n'
  printf 'Read before writing page content. The palette, dividers, callouts and rich-content\n'
  printf 'rules every write path renders through. Referenced from `../SKILL.md`.\n\n'
  sed -n '<start>,<end>p' SKILL.md      # numbers from Step 1
} > references/styling.md
cd -
```

- [ ] **Step 3: Replace the region in SKILL.md with the pointer**

```markdown
## Styling conventions

The palette, zone dividers, intro callouts, rich-content rules and heading attribute preservation
are in **`references/styling.md`**. **Read it before any operation that writes page content** —
`createTicket`, `createEpic`, `upsertSection`, `appendToSection`, `refreshEpicTasks`,
`refreshAcceptanceCriteria`. A section written without these conventions renders inconsistently
with every other section of the same ticket.
```

- [ ] **Step 4: Run the suite to see what broke**

```bash
for h in scripts/verify-*.sh; do "$h" >/dev/null 2>&1 || echo "FAILED: $h"; done
```
Expected: `FAILED: scripts/verify-new-info.sh` and `FAILED: scripts/verify-convergence.sh`.

- [ ] **Step 5: Re-anchor**

Add `TSSTY=$ND/skills/ticket-system/references/styling.md` to each broken harness and repoint the moved assertions at `"$TSSTY" 1 "$(total_lines "$TSSTY")"`. Labels and regexes unchanged.

- [ ] **Step 6: Suite green**

```bash
for h in scripts/verify-*.sh; do "$h" >/dev/null 2>&1 || echo "FAILED: $h"; done; echo done
```

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/skills/ticket-system scripts/verify-new-info.sh scripts/verify-convergence.sh
git commit -m "refactor(notion-dev): move ticket-system styling into references/styling.md"
```

- [ ] **Step 8: Mutation-test**

Delete the `Notes` row from `references/styling.md`, confirm `verify-new-info.sh` FAILs, restore, confirm PASS.

---

## Task 4: extract `references/read-ops.md`

**Files:**
- Create: `plugins/notion-dev/skills/ticket-system/references/read-ops.md`
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md`
- Modify: `scripts/verify-runtime-feedback.sh` (`fetchTicket` step-1 assertions, ~L688–700), `scripts/verify-epic-doc.sh` (2 `getEpicContext` assertions), `scripts/verify-knowledge.sh` (1 `getEpicContext` assertion)

**Interfaces:**
- Consumes: the pointer wording from Task 2.
- Produces: `references/read-ops.md` containing `## fetchTicket(id)`, `## findEpics()`, `## getEpicContext(epicId, currentTicketId)` (with its `## Epic context:` and `## Overview` output-shape subsections) and `## listEpicChildren(epicId)` verbatim.

- [ ] **Step 1: Recompute regions**

```bash
grep -n '^## ' plugins/notion-dev/skills/ticket-system/SKILL.md
```

The four operations are non-contiguous in the original — extract each range separately and concatenate in the order above.

- [ ] **Step 2: Extract each operation verbatim, in order**

```bash
cd plugins/notion-dev/skills/ticket-system
{
  printf '# ticket-system — read operations\n\n'
  printf 'Read before the first read. `fetchTicket`, `findEpics`, `getEpicContext`,\n'
  printf '`listEpicChildren`. Referenced from `../SKILL.md`.\n\n'
  sed -n '<fetchTicket-range>p'      SKILL.md
  sed -n '<findEpics-range>p'        SKILL.md
  sed -n '<getEpicContext-range>p'   SKILL.md   # includes the `## Epic context:` / `## Overview` shape blocks
  sed -n '<listEpicChildren-range>p' SKILL.md
} > references/read-ops.md
cd -
```

- [ ] **Step 3: Delete those ranges from SKILL.md, highest line number first**

Deleting low-to-high shifts every later range. Delete in descending order so earlier ranges stay valid.

- [ ] **Step 4: Add the pointer to SKILL.md**

```markdown
## Read operations

`fetchTicket`, `findEpics`, `getEpicContext` and `listEpicChildren` are in
**`references/read-ops.md`**. **Read it before the first read.** `fetchTicket`'s id-resolution
rules there are load-bearing: a structured filter can be silently ignored rather than rejected, so
the resolved page's `idProperty` is verified on every path.
```

- [ ] **Step 5: Run the suite to see what broke**

Expected: `verify-runtime-feedback.sh`, `verify-epic-doc.sh`, `verify-knowledge.sh`.

- [ ] **Step 6: Re-anchor**

Add `TSREAD=$ND/skills/ticket-system/references/read-ops.md` to each and repoint the moved assertions.

- [ ] **Step 7: Suite green, then commit**

```bash
git add plugins/notion-dev/skills/ticket-system scripts/verify-runtime-feedback.sh scripts/verify-epic-doc.sh scripts/verify-knowledge.sh
git commit -m "refactor(notion-dev): move ticket-system read operations into references/read-ops.md"
```

- [ ] **Step 8: Mutation-test**

Remove the "more than one row, or `has_more: true`, is never resolved by taking the first row" sentence from `read-ops.md`, confirm `verify-runtime-feedback.sh` FAILs, restore, confirm PASS.

---

## Task 5: extract `references/write-ops.md`

**Files:**
- Create: `plugins/notion-dev/skills/ticket-system/references/write-ops.md`
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md`
- Modify: `scripts/verify-completeness.sh` (4 `refreshAcceptanceCriteria` assertions), `scripts/verify-runtime-feedback.sh` (the `upsertSection` assertion, ~L717)

**Interfaces:**
- Consumes: the pointer wording from Task 2.
- Produces: `references/write-ops.md` containing `## updateTicket(id, patch)`, `## updateStatus(id, logicalStatus)`, `## setPullRequest(id, url)`, `## postComment(id, text)`, `## upsertSection(id, sectionName, content)`, `## refreshAcceptanceCriteria(id, verdicts)`, `## appendToSection(id, sectionName, content)` verbatim.

- [ ] **Step 1: Recompute regions with `grep -n '^## '`, extract each verbatim, concatenate in the order above**

Header:

```markdown
# ticket-system — write operations

Read before the first write. `updateTicket`, `updateStatus`, `setPullRequest`, `postComment`,
`upsertSection`, `refreshAcceptanceCriteria`, `appendToSection`. Referenced from `../SKILL.md`.
```

- [ ] **Step 2: Delete those ranges from SKILL.md, highest first**

- [ ] **Step 3: Add the pointer**

```markdown
## Write operations

`updateTicket`, `updateStatus`, `setPullRequest`, `postComment`, `upsertSection`,
`refreshAcceptanceCriteria` and `appendToSection` are in **`references/write-ops.md`**. **Read it
before the first write.** The `upsertSection` / `appendToSection` distinction there is
load-bearing: a replacing write where an append was meant clobbers a section another phase wrote.
```

- [ ] **Step 4: Run the suite; expect `verify-completeness.sh` and `verify-runtime-feedback.sh` to fail**

- [ ] **Step 5: Re-anchor with `TSWRITE=$ND/skills/ticket-system/references/write-ops.md`**

- [ ] **Step 6: Suite green, then commit**

```bash
git add plugins/notion-dev/skills/ticket-system scripts/verify-completeness.sh scripts/verify-runtime-feedback.sh
git commit -m "refactor(notion-dev): move ticket-system write operations into references/write-ops.md"
```

- [ ] **Step 7: Mutation-test**

Delete the `refreshAcceptanceCriteria` heading from `write-ops.md`, confirm `verify-completeness.sh` FAILs, restore, confirm PASS.

---

## Task 6: extract `references/create-ops.md`

The largest extraction, and the one `/notion-dev:ticket` never loads.

**Files:**
- Create: `plugins/notion-dev/skills/ticket-system/references/create-ops.md`
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md`
- Modify: `scripts/verify-ticket-system.sh` (the 5 title-prefix escape assertions, L59–67), `scripts/verify-runtime-feedback.sh` (title-prefix escaping L390–408, `refreshEpicTasks` L714–726)

**Interfaces:**
- Consumes: the pointer wording from Task 2.
- Produces: `references/create-ops.md` containing `## Title prefix`, `## resolveAssignee(value)`, `## createTicket(…)`, `## setDependencies(id, references)`, `## getSelectOptions(configKey)`, `## addSelectOption(configKey, optionName)`, `## Epic containers`, `## createEpic(…)`, `## setParent(id, epicId)`, `## refreshEpicTasks(epicId)` verbatim.

- [ ] **Step 1: Recompute regions, extract verbatim, concatenate in the order above**

Header:

```markdown
# ticket-system — creation and epic-container operations

Read before the first create. Title prefixing, `resolveAssignee`, `createTicket`,
`setDependencies`, `getSelectOptions`, `addSelectOption`, epic containers, `createEpic`,
`setParent`, `refreshEpicTasks`. Referenced from `../SKILL.md`.

`/notion-dev:ticket` never reaches this file — it creates no ticket and no epic.
`/notion-dev:create-task` is its principal consumer.
```

- [ ] **Step 2: Delete those ranges from SKILL.md, highest first**

- [ ] **Step 3: Add the pointer**

```markdown
## Creation and epic-container operations

Title prefixing, `resolveAssignee`, `createTicket`, `setDependencies`, `getSelectOptions`,
`addSelectOption`, epic containers, `createEpic`, `setParent` and `refreshEpicTasks` are in
**`references/create-ops.md`**. **Read it before the first create.** The title-prefix escaping
rules there are load-bearing — an unescaped write fails with `No matches found`, and an
unescaped read-back produces a double prefix.
```

- [ ] **Step 4: Run the suite; expect `verify-ticket-system.sh` and `verify-runtime-feedback.sh` to fail**

- [ ] **Step 5: Re-anchor with `TSCREATE=$ND/skills/ticket-system/references/create-ops.md`**

Note `verify-runtime-feedback.sh:402` is an `assert_count … 2` ("canonical rule + the Tasks-update site"). Check whether both matched lines moved into `create-ops.md` together. If one stayed in `SKILL.md`, the count must be split into two `assert_present` calls, one per file — a `2` that now finds `1` is a real failure, not an anchoring detail to paper over.

- [ ] **Step 6: Suite green, then commit**

```bash
git add plugins/notion-dev/skills/ticket-system scripts/verify-ticket-system.sh scripts/verify-runtime-feedback.sh
git commit -m "refactor(notion-dev): move ticket-system creation operations into references/create-ops.md"
```

- [ ] **Step 7: Mutation-test**

Remove the optional-escape detection regex from `create-ops.md`, confirm `verify-ticket-system.sh` FAILs, restore, confirm PASS.

---

## Task 7: the operation index and its standing invariant

What makes the split safe: a table mapping every operation to its file, plus a rule that forbids performing an operation whose file has not been read.

**Files:**
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md`
- Modify: `scripts/verify-context-split.sh`

**Interfaces:**
- Consumes: the five reference files created in Tasks 2–6.
- Produces: the `## Operation index` section; Tasks 10 and 11 assert against it.

- [ ] **Step 1: Add the index to SKILL.md, immediately after `## Logical operations`**

```markdown
## Operation index

Every operation lives in exactly one reference file. **You may not perform an operation whose
reference file you have not read in this run** — the contract is in that file, not here, and
improvising it writes malformed pages that the Notion API accepts without complaint.

| operation | file |
|---|---|
| `fetchTicket` | `references/read-ops.md` |
| `findEpics` | `references/read-ops.md` |
| `getEpicContext` | `references/read-ops.md` |
| `listEpicChildren` | `references/read-ops.md` |
| `updateTicket` | `references/write-ops.md` |
| `updateStatus` | `references/write-ops.md` |
| `setPullRequest` | `references/write-ops.md` |
| `postComment` | `references/write-ops.md` |
| `upsertSection` | `references/write-ops.md` |
| `appendToSection` | `references/write-ops.md` |
| `refreshAcceptanceCriteria` | `references/write-ops.md` |
| `resolveAssignee` | `references/create-ops.md` |
| `createTicket` | `references/create-ops.md` |
| `createEpic` | `references/create-ops.md` |
| `setParent` | `references/create-ops.md` |
| `setDependencies` | `references/create-ops.md` |
| `getSelectOptions` | `references/create-ops.md` |
| `addSelectOption` | `references/create-ops.md` |
| `refreshEpicTasks` | `references/create-ops.md` |

`references/config.md` is read before the first Notion call of any kind; `references/styling.md`
before any operation that writes page content. Neither is keyed to a single operation.
```

- [ ] **Step 2: Add the standing invariant to `scripts/verify-context-split.sh`**

Append before the `exit` line. This is the invariant that cannot rot — it goes red the moment an operation is added, moved or renamed without its index entry:

```bash
# ---------------------------------------------------------------------------
echo "== ticket-system: the operation index resolves =="

assert_present "ticket-system states the read-before-use gate" \
  "$TS" 1 "$(total_lines "$TS")" \
  'may not perform an operation whose reference file you have not read'

# Every indexed operation resolves to a file that exists and carries its own heading,
# and no operation body is left behind in the dispatcher.
idx_fail=0
while IFS='|' read -r _ op file _; do
  op=$(printf '%s' "$op" | tr -d ' `'); file=$(printf '%s' "$file" | tr -d ' `')
  case "$op" in ''|operation|---*) continue ;; esac
  if [ ! -f "$ND/skills/ticket-system/$file" ]; then
    bad "index: $op -> $file (file missing)"; idx_fail=1; continue
  fi
  if ! grep -q "^## $op(" "$ND/skills/ticket-system/$file"; then
    bad "index: $op is not defined in $file"; idx_fail=1; continue
  fi
  if grep -q "^## $op(" "$TS"; then
    bad "index: $op body is still in the dispatcher"; idx_fail=1; continue
  fi
done < <(grep '^| `' "$TS")
[ "$idx_fail" -eq 0 ] && ok "every indexed operation resolves to its reference file, and none is left in the dispatcher"
```

- [ ] **Step 3: Run it to verify it passes**

Run: `./scripts/verify-context-split.sh`
Expected: both assertions PASS.

- [ ] **Step 4: Verify the dispatcher hit its size target**

```bash
echo "dispatcher: $(( $(wc -c < plugins/notion-dev/skills/ticket-system/SKILL.md) / 4 )) tok (target ~4000)"
for f in plugins/notion-dev/skills/ticket-system/references/*.md; do
  echo "  $(basename "$f"): $(( $(wc -c < "$f") / 4 )) tok"
done
```

If the dispatcher is materially over ~5,000 tokens, something that belongs in a reference is still in it — find it before moving on.

- [ ] **Step 5: Suite green, then commit**

```bash
for h in scripts/verify-*.sh; do "$h" >/dev/null 2>&1 || echo "FAILED: $h"; done
git add plugins/notion-dev/skills/ticket-system/SKILL.md scripts/verify-context-split.sh
git commit -m "feat(notion-dev): ticket-system operation index with a read-before-use gate"
```

- [ ] **Step 6: Mutation-test the invariant, both halves**

```bash
# half 1: an index entry pointing at a file that does not define it.
# Use a delimiter that does not occur in a markdown table row -- `|` would end the
# sed expression on the row's own first column separator.
sed -i 's#read-ops.md` |#write-ops.md` |#' \
  plugins/notion-dev/skills/ticket-system/SKILL.md
./scripts/verify-context-split.sh; echo "exit=$?"   # expect FAIL
git checkout -- plugins/notion-dev/skills/ticket-system/SKILL.md

# half 2: an operation body left in the dispatcher
printf '\n## postComment(id, text)\n\nleftover\n' >> plugins/notion-dev/skills/ticket-system/SKILL.md
./scripts/verify-context-split.sh; echo "exit=$?"   # expect FAIL
git checkout -- plugins/notion-dev/skills/ticket-system/SKILL.md
./scripts/verify-context-split.sh; echo "exit=$?"   # expect PASS
```

---

## Task 8: extract Phases 8–10 into `commands/references/record.md`

Pure move, no behaviour change yet. Task 9 adds the dispatch.

**Files:**
- Create: `plugins/notion-dev/commands/references/record.md`
- Modify: `plugins/notion-dev/commands/ticket.md` — Phases 8, 9, and Phase 10's `record` step
- Modify: `scripts/verify-post-merge-ordering.sh`, `scripts/verify-knowledge.sh`, `scripts/verify-epic-doc.sh`, `scripts/verify-primary-lock.sh` (any assertion whose region covers `ticket.md` lines 443–596)

**Interfaces:**
- Consumes: nothing from earlier tasks — independent of the `ticket-system` split.
- Produces: `commands/references/record.md`, whose contents Task 9's dispatch prompt names by path.

- [ ] **Step 1: Find every assertion anchored inside the region**

```bash
grep -n 'TICKET\|ticket\.md' scripts/verify-*.sh | grep -n 'assert_'
grep -n '^## Phase' plugins/notion-dev/commands/ticket.md
```

Record which assertions have regions overlapping Phase 8's start through Phase 10's `record` step. Those move with the content.

- [ ] **Step 2: Extract verbatim**

```bash
cd plugins/notion-dev/commands
mkdir -p references
{
  printf '# /notion-dev:ticket — the record unit (Phases 8-10)\n\n'
  printf 'Read by the agent dispatched from `../ticket.md` Phase 8, or by the orchestrator\n'
  printf 'itself on the inline-recovery path when that dispatch fails.\n\n'
  printf 'The caller has already resolved the interactive filing gate (`FILING_DECISIONS`),\n'
  printf 'taken the primary lock (`LOCK_HELD: true`), and left the worktree (`cd $REPO_ROOT`).\n'
  printf 'Do not take the lock again, do not ask the user anything, and do not release the\n'
  printf 'lock — the caller does that after this unit returns.\n\n'
  sed -n '<phase8-start>,<phase10-record-end>p' ticket.md
} > references/record.md
cd -
```

- [ ] **Step 3: Append the return contract to `record.md`**

```markdown
## Output block

Return exactly this block and nothing else after it:

```
RECORD:
EPIC-REPORT: <the epic-update EPIC-UPDATE: block verbatim, or `none`>
TICKET-RECORD: <ok | partial: <what was not written> | failed: <cause>>
CLEANUP: <ok | partial: <which step> | failed: <cause>>
EPIC-DOC-RECORD: <ok | skipped: <why> | failed: <cause>>
ISSUES: <comma-separated issue-log signatures recorded in this unit, or `none`>
```

Every key appears on every run. A key with nothing to report takes its `ok` or `none` value, never
absence — an omitted key is indistinguishable from a step that never ran.
```

- [ ] **Step 4: Replace the region in `ticket.md` with a placeholder pointing at the file**

Task 9 replaces this placeholder with the dispatch. For now:

```markdown
## Phase 8 — Record

Touch the run marker: `phase` = "Phase 8", `heartbeat` = now.

The record, cleanup and `epic-doc record` steps are in **`references/record.md`**. Resolve the
interactive filing gate first (below), take the primary lock, `cd $REPO_ROOT`, then follow that
file.
```

Keep the interactive filing gate paragraph (8.2's `AskUserQuestion` walk over `REVIEW_REPORT`'s `FILED` list) and the lock-take paragraph **in `ticket.md`** — they do not move. Verify by reading `references/record.md` and confirming neither appears there.

- [ ] **Step 5: Run the suite, re-anchor whatever broke to `references/record.md`**

```bash
for h in scripts/verify-*.sh; do "$h" >/dev/null 2>&1 || echo "FAILED: $h"; done
```

- [ ] **Step 6: Suite green, then commit**

```bash
git add plugins/notion-dev/commands scripts/verify-*.sh
git commit -m "refactor(notion-dev): move ticket Phases 8-10 into commands/references/record.md"
```

- [ ] **Step 7: Mutation-test one re-anchored assertion**

Break a line in `references/record.md` that a re-anchored assertion pins, confirm its harness FAILs, restore, confirm PASS.

---

## Task 9: dispatch the record unit, with a bounded wait and inline recovery

**Files:**
- Modify: `plugins/notion-dev/commands/ticket.md` — Phase 8
- Modify: `plugins/notion-dev/skills/issue-log/references/signatures.md` — register the new signature

**Interfaces:**
- Consumes: `commands/references/record.md` and its `RECORD:` output block from Task 8.
- Produces: `RECORD_REPORT`, read by Phase 10's report. Task 10 asserts the dispatch site's three required elements.

- [ ] **Step 1: Register the failure signature**

Add a row to `plugins/notion-dev/skills/issue-log/references/signatures.md`, matching the existing table's column shape:

```markdown
| `unexpected:record-unit-not-dispatched` | unexpected | `/notion-dev:ticket` | the Phase 8 record unit could not be dispatched, returned zero bytes, or exceeded the ~15-minute bound. The orchestrator ran `commands/references/record.md` inline instead, so the work is done and only the context saving was lost — never a verdict about the record itself | once/run |
```

- [ ] **Step 2: Replace Phase 8's placeholder with the dispatch**

```markdown
## Phase 8 — Record

Touch the run marker: `phase` = "Phase 8", `heartbeat` = now.

**Resolve the interactive filing gate before the lock is taken.** In interactive mode, walk
`REVIEW_REPORT`'s `FILED` list and put each item to the user with `AskUserQuestion` — File as
ticket, or Drop with a rationale — and carry the answers forward as `FILING_DECISIONS`. A person
deciding this can outlast the lock's 60-minute stale threshold, after which another run breaks a
lock this one still believes it holds and both write at once. A non-interactive run files
everything and has nothing to ask.

**Take the primary lock**, exactly as before:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <KEY>-<id> --section record --wait 3600`.
The caller holds it across the dispatch and releases it after Phase 10's `record`; the dispatched
agent is told `LOCK_HELD: true` so it never takes it again.

**Leave the worktree: `cd $REPO_ROOT`.** `references/record.md`'s cleanup removes the worktree, and
the orchestrator is normally sitting inside it.

**Dispatch one `general-purpose` agent, synchronously**, with a self-contained prompt carrying:
the ticket id, PR number and URL, `$REPO_ROOT`, the worktree path, the branch name, `baseRefName`,
`REVIEW_REPORT`, `COMPLETENESS_REPORT`, `COMPLETION_CLOSEOUT`, the `CRITERIA_FILE` path, the run id,
`FILING_DECISIONS`, `LOCK_HELD: true`, `--non-interactive` when this run has it, and the
instruction to read `references/record.md` and follow it exactly. Record its `RECORD:` block as
`RECORD_REPORT`.

**Reaching this step is itself the request for that agent.** A standing rule of the shape *do not
dispatch subagents unless the user asks for one* is already satisfied by the user invoking this
command, and is not grounds to skip the dispatch.

**Bound the wait at ~15 minutes** — the same bound `notion-dev:review-and-merge`'s checks gate,
`notion-dev:plan-review` and `notion-dev:flow-triage` already apply, and for the same reason: a
dispatch that never returns emits nothing, so no check written against a delivered result can ever
fire. The tell is `ListAgents` reporting the same agent as "started <1m ago" on repeated checks.

**On a failed, zero-byte, or timed-out dispatch: do not retry, and do not stop.** Record
`unexpected:record-unit-not-dispatched` per `notion-dev:issue-log`, then **read
`references/record.md` and run it inline yourself**, exactly as `/notion-dev:finalize`'s `MERGED`
post-merge recovery path does. The work is idempotent and the fallback is the path that already
exists; only this run's context saving is forfeited. Say so plainly in Phase 10's report.

This is the reverse of Phase 7's reasoning, deliberately: there a lost dispatch costs the merge and
has no fallback, so the skill is invoked in this context. Here it costs only the saving.
```

- [ ] **Step 3: Update Phase 10 to read `RECORD_REPORT`**

Phase 10's report renders from `RECORD_REPORT`'s keys rather than from values it computed itself. Its closing `notion-dev:session-closeout` pass stays in the orchestrator — already loaded at Phase 7, and it may need to ask the user.

- [ ] **Step 4: Confirm the orchestrator no longer names the moved skills**

```bash
sed -n '/^## Phase 8/,/^## Failure and stop/p' plugins/notion-dev/commands/ticket.md \
  | grep -n 'epic-update\|notion-dev:knowledge\|updateStatus\|appendToSection\|refreshAcceptanceCriteria'
```
Expected: no output. Any hit is content that should have moved to `references/record.md`.

- [ ] **Step 5: Suite green, then commit**

```bash
for h in scripts/verify-*.sh; do "$h" >/dev/null 2>&1 || echo "FAILED: $h"; done
git add plugins/notion-dev/commands/ticket.md plugins/notion-dev/skills/issue-log/references/signatures.md
git commit -m "feat(notion-dev): dispatch the ticket record unit, with inline recovery"
```

---

## Task 10: standing invariants for the delegation

**Files:**
- Modify: `scripts/verify-context-split.sh`

**Interfaces:**
- Consumes: the dispatch site from Task 9 and `references/record.md` from Task 8.
- Produces: the final harness; Task 11 runs it as part of the suite.

- [ ] **Step 1: Append the assertions, before the `exit` line**

```bash
# ---------------------------------------------------------------------------
echo "== ticket: the record unit is dispatched, and recoverable when it is not =="

assert_order "Phase 8 asks, locks, leaves the worktree, then dispatches" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  "filing gate"  'Resolve the interactive filing gate before the lock is taken' \
  "lock take"    'knowledge\.py. lock take .*--section record' \
  "cd REPO_ROOT" 'Leave the worktree: .cd \$REPO_ROOT' \
  "dispatch"     'Dispatch one .general-purpose. agent, synchronously'

assert_present "the dispatch names \`references/record.md\` as the agent's instructions" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  'instruction to read .references/record\.md. and follow it exactly'

assert_present "the wait is bounded at ~15 minutes" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  'Bound the wait at ~15 minutes'

assert_present "a lost dispatch records \`unexpected:record-unit-not-dispatched\` and runs inline" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  'unexpected:record-unit-not-dispatched'

assert_present "the fallback runs \`references/record.md\` inline rather than stopping" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  'read.*references/record\.md. and run it inline yourself'

assert_present "\`references/record.md\` returns a \`RECORD:\` block" \
  "$RECORD" 1 "$(total_lines "$RECORD")" 'RECORD:'

assert_present "\`references/record.md\` is told the lock is already held" \
  "$RECORD" 1 "$(total_lines "$RECORD")" 'LOCK_HELD'

# The saving is the point: the orchestrator's own record phase must not name the
# skills the unit was created to carry. This is what goes red if the delegation
# is quietly unwound by a later edit.
assert_absent "the orchestrator's record phase no longer invokes \`notion-dev:epic-update\`" \
  "$TICKET" "$(find_line "$TICKET" 1 "$(total_lines "$TICKET")" '^## Phase 8')" \
  "$(total_lines "$TICKET")" 'notion-dev:epic-update'
```

- [ ] **Step 2: Run it to verify every assertion passes**

Run: `./scripts/verify-context-split.sh`
Expected: all PASS, exit 0. Any `weak anchor` message means the regex matches more than one line — tighten it rather than switching to `assert_count`, unless the document genuinely says it twice on purpose.

- [ ] **Step 3: Commit**

```bash
git add scripts/verify-context-split.sh
git commit -m "test(notion-dev): standing invariants for the dispatched record unit"
```

- [ ] **Step 4: Mutation-test each new assertion**

```bash
for probe in 'Bound the wait at ~15 minutes' 'unexpected:record-unit-not-dispatched' \
             'and run it inline yourself'; do
  sed -i "s/$probe/REMOVED/" plugins/notion-dev/commands/ticket.md
  ./scripts/verify-context-split.sh >/dev/null 2>&1; echo "$probe -> exit=$? (expect 1)"
  git checkout -- plugins/notion-dev/commands/ticket.md
done
./scripts/verify-context-split.sh >/dev/null 2>&1; echo "restored -> exit=$? (expect 0)"
```

Also break the `assert_order` by moving the dispatch paragraph above the lock-take paragraph, confirm FAIL, restore.

---

## Task 11: version bump, README, and the full proof

**Files:**
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json`
- Modify: `plugins/notion-dev/README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: the mergeable branch.

- [ ] **Step 1: Bump the manifest — minor**

```bash
grep '"version"' plugins/notion-dev/.claude-plugin/plugin.json
git show origin/main:plugins/notion-dev/.claude-plugin/plugin.json | grep '"version"'
```

Current base is `0.27.1`. Set `0.28.0` — Task 9 adds a capability. Confirm strictly greater than base.

- [ ] **Step 2: Update the README**

The skills tree comment for `ticket-system` gains its references; add `commands/references/record.md`. Keep it to the structure block — this change alters no user-facing command surface.

- [ ] **Step 3: Measure the result against the spec's claim**

```bash
echo "=== ticket-flow instruction load ==="
for f in plugins/notion-dev/commands/ticket.md \
         plugins/notion-dev/skills/ticket-system/SKILL.md \
         plugins/notion-dev/skills/ticket-system/references/config.md \
         plugins/notion-dev/skills/ticket-system/references/read-ops.md \
         plugins/notion-dev/skills/ticket-system/references/write-ops.md \
         plugins/notion-dev/skills/ticket-system/references/styling.md \
         plugins/notion-dev/skills/issue-log/SKILL.md; do
  printf '%-64s %6d tok\n' "$f" $(( $(wc -c < "$f") / 4 ))
done
```

The spec claims ~15,800 for the `ticket-system` group (dispatcher + config + read-ops + write-ops + styling). If the actual total is materially higher, say so in the PR body rather than restating the spec's estimate.

- [ ] **Step 4: Run the full suite one final time, showing output**

```bash
for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done
```
Expected: every harness prints only `PASS` lines; no `FAILED:`.

- [ ] **Step 5: Commit and open the pull request**

```bash
git add plugins/notion-dev/.claude-plugin/plugin.json plugins/notion-dev/README.md
git commit -m "chore(notion-dev): 0.28.0 — context split"
git push -u origin docs/notion-dev-context-reduction
```

PR body must state: the measured before/after instruction load; that Change 1 pays 3–6k for its dispatch prompt against ~30k saved; that the client-side `context-mode` and MCP-trimming items (~164k, ~3.4× this PR) are **not** in scope and are the user's to do; and the two rejected options with the measurements that killed them, so a reviewer does not re-raise them.

- [ ] **Step 6: Drive it to merge**

Invoke `notion-dev:review-and-merge` with the PR number and the stale-bump `--pre-merge-check`, per `CLAUDE.md`. Let its final sweep take any small fix rather than filing it.
