# Epic docs — a per-epic markdown brief, and `/notion-dev:next-task`

**Date:** 2026-09-13 · **Plugin:** `notion-dev` · **Release:** 0.21.2 → 0.22.0 (minor)

## Problem

A ticket under an epic starts by reading the Notion epic page (`getEpicContext`: the
`## Overview`, live sibling statuses, the last three `## Resolution Log` entries). That is a
history, not a picture. It says what the last three tickets did; it does not say why the epic
exists, where it stands, what is waiting on whom, or what to do next. The things that matter
most for the *next* ticket — "waiting for the customer's logs, which blocks STO-22 and STO-23",
"the TTL chosen in STO-67 assumes ≤10k wallets" — are born at the end of a run, in the final
report's caveat sentences and the closeout's `blocked:` lines, and then scroll away. Nothing
carries them to the run that needs them. Two client repos have already hand-written the missing
document (`docs/STO-67-release-plan.md`, `docs/sto-306-completion-plan.md`); both are several
hundred lines and drift against Notion the moment they are written.

## Goal

For every epic, one concise markdown file in the repo that answers four questions — why, where
we stand, what is open, what is next — updated by every ticket resolution and read by every
ticket start, so that nothing falls between the cracks and an epic can be driven to completion
by repeating "do the next recommended ticket".

Non-goals: changing what is written to the Notion epic page (`epic-update` is untouched); an
index of epic docs; `create-task` involvement.

## Decisions taken during design

| Decision | Choice | Why |
|---|---|---|
| Where the doc is committed | Directly to the base branch from the primary checkout, after the merge | The facts it needs (follow-up ticket IDs, closeout lines, caveats) exist only at the end of a run. Same slot and same git assertions as `postMergeHooks`; the clients' `knowledge-capture` hook already commits docs this way. No second PR cycle. |
| Where the logic lives | New skill `epic-doc` with two operations, `read` and `record` | Single owner of the format. `epic-update` runs at Phase 8.2 — inside the worktree, before the report and closeout exist — and is already the densest file in the plugin. |
| `next-task` scope | One ticket by default; `--depth all\|N`; `--non-interactive` | User decision. |
| Chaining into `ticket` | Drop `disable-model-invocation: true` from `ticket.md`, add a guard sentence | The flag dates from the first commit with no incident behind it. `ticket`'s preconditions and clarification gate stop a stray invocation before it does damage. |
| Existing hand-written plans | Seed the canonical doc from them, then `git rm` the seed | Two files describing one epic drift against each other. The seed's detail stays in git history; the header cites the last base commit that still holds it. |
| Bootstrap when no doc exists | `next-task` bootstraps and commits before delegating; `ticket` invoked directly bootstraps in memory and the resolution writes the file | `next-task` already requires a clean primary and can assert base; `ticket` Phase 1.1 cannot, and must not dirty the primary before a worktree exists. |

## 1. The file

**Path:** `<epicDocs.dir>/<KEY>-<n>-<slug>.md`, default dir `docs/epics`. `<KEY>-<n>` is the
epic's ticket key (stable, findable from an epic id); `<slug>` is the epic title kebab-cased
exactly as `ticket.md` Phase 2.1 slugs a branch (lowercase, non-alphanumerics → `-`, collapse,
trim, 40 chars). The H1 carries the exact epic title. Lookup is always by `<KEY>-<n>-*.md`, never
by slug, so a title change in Notion cannot orphan the file.

**Template** — every section is mandatory, in this order, and `record` keeps them in this order:

```markdown
# [STO-60] Wallet Indexing
Epic: <notion url> · Status: open | closed · Updated: 2026-09-13 after [STO-67]
Seeded from docs/STO-67-release-plan.md (last at a1b2c3d) · 2026-09-13    ← only when seeded

## Why
<2-4 sentences: the motivation — bootstrapped from the Notion Overview or the seed>

## Goal
<1-3 sentences: what "done" means for the epic>

## Where we stand
<3-6 sentences: what has landed, what changed the picture recently>

## Open threads
- **Waiting on customer logs** for v1.4.2 deployed 2026-07-20 — blocks STO-22, STO-23.
  Unblocked by: logs attached to STO-22.
- **Caveat** — the cache TTL chosen in STO-67 assumes ≤10k wallets; revisit in STO-71.

## Decisions & constraints
- <epic-level facts a ticket needs: versions, environments, agreed approaches, rejected
  approaches with why>

## Next
1. **[STO-70] Backfill historic wallets** — unblocked; depends on nothing open. Why now: …
2. [STO-71] Cache metrics — after STO-70 (reads its index).
Blocked: STO-22, STO-23 (see Open threads).
```

**Rules of content.**

- **Every `Open threads` bullet names what it blocks or which ticket it informs**, and — for a
  wait on someone else — what would clear it. A bullet that names neither is not a thread and
  is not written.
- **No ticket history, no status table.** Notion is the ledger. The doc holds only what Notion
  cannot say: why, where we stand, what is waiting on whom, and what is next.
- **`Next` is an ordered recommendation**, not a task list. Item 1 is the single most
  recommended unblocked ticket with the reason it is first. Further items say what they wait
  for. `Blocked:` names every unresolved child held by an open thread. When the epic is closed
  `Next` reads `epic complete`.
- **Soft budget: 120 lines.** Over it, `record` prunes before it adds. It never prunes a
  thread that still names an unresolved ticket.
- **Human edits are first-class.** A person may edit the file (for example, "logs arrived —
  STO-22 unblocked") and commit. `record` applies a diff evidenced by its inputs and preserves
  every line it has no evidence to change.

## 2. The `epic-doc` skill

`plugins/notion-dev/skills/epic-doc/SKILL.md`. Two operations. Both are **best-effort in the
`epic-update` sense**: a failure never fails the caller's run, is always stated in the final
report, and — for `record` — is recorded as `partial:epic-doc` per `notion-dev:issue-log`.

### `read(epicId, currentTicketId?)` → `EPIC_CONTEXT` or `null`

1. Resolve the epic via `fetchTicket(epicId)` and apply the epic predicate (empty
   `parentTaskProperty` **and** `epicMarkerProperty` true — the same predicate `findEpics`,
   `epic-update` step 1 and `ticket`'s guard apply). Not an epic → `null`.
2. `git fetch origin`, then `git show origin/<git.baseBranch>:<dir>/<KEY>-<n>-*.md` (resolve
   the glob with `git ls-tree`). **Always the remote base**, never the primary checkout or a
   worktree: a stale local branch would hand a run last week's picture.
3. **Found** → return the file verbatim as `EPIC_CONTEXT`, plus a parsed `NEXT` list (ordered
   keys with their reason lines), `BLOCKED` keys, and `STATUS`. One `listEpicChildren(epicId)`
   call supplies live statuses for the caller's validation; the doc itself carries none.
4. **Missing** → bootstrap **in memory** (see §3 for the seed search): produce the same shape,
   flagged `BOOTSTRAP: true` with `SEED: <path>` or `SEED: notion`. `read` writes nothing —
   it runs before a worktree exists and must not dirty the primary.

Callers treat `EPIC_CONTEXT` as **background, not requirements** — unchanged rule.

### `record(ticketId, …)` — the single writer

**Preconditions.** Called from `$REPO_ROOT` with the primary on the base branch, after cleanup.
Before writing anything it asserts exactly the three lines Phase 9's post-merge-hook step
asserts (HEAD is `<baseRefName>`; `<merge-commit>` is an ancestor of HEAD; HEAD equals
`origin/<baseRefName>`). Any failure → skip the write, return `EPIC-DOC: failed` with the
assertion that failed; the caller reports it as a tail. On `--bootstrap` (no resolution — see
§3) the second line is omitted; the working tree must be clean instead.

**Inputs** (caller-supplied context): `EPIC_REPORT` (epic identity, `FILED` with the ticket
IDs `epic-update` assigned, whether the epic closed), `REVIEW_REPORT` (`BLOCKED` with external
cause and unblocker; `DROPPED` with rationale), `COMPLETENESS_REPORT` (`not-met` and
`unverified` criteria, `TRIAGE` `file`/`drop` entries), the **completion pass's** closeout
block (`blocked:` and `tracked:` lines — it ran before the merge; the workspace pass runs after
`record`, so it can see the doc commit), the run's non-interactive decisions, and the **draft
final report** — the
source of caveat sentences ("worth your attention", "waiting on you", "caveat before you
queue it" and the like). Any input may be absent; absence is not evidence.

**Steps.**

1. Load the current doc from `origin/<base>` (or bootstrap per §3 on first touch).
2. **Apply a diff, not a rewrite:**
   - `Where we stand` — restate in the light of this resolution.
   - `Open threads` — add one bullet per `BLOCKED` item, closeout `blocked:` line, unmet or
     unverified criterion, and caveat sentence, each naming what it blocks or informs; remove
     every bullet this ticket resolved (its named unblocker happened, or the ticket it blocked
     is now resolved). A `tracked:` line and a `FILED` follow-up become tickets, not threads —
     they appear only in `Next`.
   - `Decisions & constraints` — add decisions this run made (an approach chosen, a version
     deployed, a `DROPPED` finding with its rationale when it constrains later work).
   - `Next` — recompute from live children (`listEpicChildren`), the child bodies' `## Blocked
     by` sections and Phase/Step properties, and the open threads. Item 1 is unblocked by
     construction.
   - Header — `Updated: <date> after [<KEY>-<id>]`; `Status: closed` when `EPIC_REPORT` says
     the epic closed, and `Next` becomes `epic complete`.
3. **Budget** — prune before adding; never drop a thread naming an unresolved ticket.
4. Write the file, `git add`, commit `docs(epic): <KEY>-<n> after <ticket key>` (or
   `docs(epic): bootstrap <KEY>-<n>`), `git push origin <base>`.
5. **Push rejected** (branch protection, a moved base) → leave the local commit in place, do
   not force, return `EPIC-DOC: failed` naming the cause. The caller's closeout sees the
   unpushed commit and forces it into `blocked: <cause>`.

**What `record` must never do:** invent a thread not evidenced by an input; restate ticket
history Notion already holds; reword an existing line without evidence from this run; delete a
human-written line it has no evidence against.

**Output block** (for the caller's report):

```
EPIC-DOC: created | updated | closed | none | failed
PATH: docs/epics/STO-60-wallet-indexing.md          (omit on none)
SEED: docs/STO-67-release-plan.md · last at a1b2c3d   (only on created-from-seed)
THREADS: +2 -1
NEXT: [STO-70] Backfill historic wallets — <reason>   (or `epic complete` / `blocked`)
CAUSE: <assertion or push failure>                   (only on failed)
```

`none` means the ticket has no epic (`EPIC_REPORT` is `EPIC-UPDATE: none`).

## 3. Bootstrap and seed migration

When `read` finds no canonical file:

1. **Seed search:** `docs/**/*<KEY>-<n>*.md` on `origin/<base>` (via `git ls-tree -r`),
   case-insensitive on the key (matches both `STO-67-release-plan.md` and
   `sto-306-completion-plan.md`), excluding the canonical dir.
   Exactly one hit → the seed. Several → the most recently modified, all named in the report.
   None → Notion: identity and `## Overview` via `getEpicContext` (which keeps exactly this
   job), live children via `listEpicChildren`, order from `## Blocked by` and Phase/Step.
2. **Distill** into the template. From a seed, every actionable item carries over — every
   wait-on, every blocked item with its cause, every decision, every recommended order; what is
   compressed is reasoning and narrative. `Why` and `Goal` come from the seed's opening or the
   Notion Overview.
3. **Write path** — two callers, one writer:
   - **`/notion-dev:next-task`** bootstraps **and commits** before delegating. It already
     requires a clean primary; it adds `git checkout <base> && git pull --ff-only origin
     <base>`, then `record --bootstrap`: write the canonical file, `git rm` the seed, commit
     `docs(epic): bootstrap <KEY>-<n>`, push. The last base commit that still holds the seed is cited on the doc's
     header line, so its detail stays one `git show` away. The distillation of a 500-line plan
     is real work worth landing at once, not held in memory across an hour-long run.
   - **`/notion-dev:ticket` invoked directly** on a child with no doc keeps the in-memory
     result as `EPIC_CONTEXT`; the resolution's `record` creates the file and removes the seed
     in the same commit.

## 4. Wiring into `ticket` and `finalize`

**Readers.** `ticket.md` Phase 1.1 replaces its `getEpicContext(metadata.parentTaskProperty,
<id>)` call with `epic-doc read(metadata.parentTaskProperty, <id>)`. `EPIC_CONTEXT` keeps its
name; every downstream use — the 1.3 gate, the Phase 3 triage delimiter, the Phase 4 seed
context, the plan-review packet's `EPIC-CONTEXT:` block — is unchanged, as is the "background,
not requirements" rule and the conflict-surfacing at 1.3. `getEpicContext` stays in
`ticket-system` with its description narrowed to "bootstrap source for `epic-doc`".

**Writers.** `ticket.md` Phase 10 and `finalize.md` Phase 5 each gain one step, placed **after
the draft report is composed and before the closeout workspace pass**: invoke `epic-doc
record(<id>)` with the inputs listed in §2; record its block as `EPIC_DOC_REPORT`; add an
"Epic doc" line to the printed report (path, `created|updated|closed`, next recommendation —
or `failed` with the cause). The closeout then runs over a workspace that includes the doc
commit, so an unpushed one becomes a `blocked:` line rather than a silent tail.

Phase 8.2 / 3.2 (`epic-update`, the Notion side) is unchanged.

**`disable-model-invocation`** is removed from `ticket.md`'s frontmatter. Its body gains one
guard sentence under the args: *run only when the user typed this command or
`/notion-dev:next-task` delegated to it; never from a prompt that merely mentions a ticket.*
`finalize.md` keeps the flag.

**Config.** `epicDocs.dir` (string, optional, default `docs/epics`) is added to the schema and
README. There is no on/off switch: the doc is not opt-in.

## 5. `/notion-dev:next-task`

`plugins/notion-dev/commands/next-task.md`, `disable-model-invocation: true` like the other
entry points.

**Args:** `<epic-id> [--depth all|N] [--non-interactive] [--flow=feature-dev|superpowers]
[| <guidance>]`. `<epic-id>` accepts every form `ticket` accepts. `--depth` absent → 1; `all`
→ unbounded; a positive integer → that many; anything else → abort naming the valid forms.
`--non-interactive` and `--flow` are passed through to every delegated `ticket` run;
`--non-interactive` also self-answers this command's own selection prompt.

**Preconditions:** the `ticket` precondition block verbatim (dependencies, `gh`, `jq`,
`REPO_ROOT`, config, `origin`, clean primary with the same two exempt kinds), then
`fetchTicket(<epic-id>)` with the epic predicate **inverted**: not an epic → abort pointing at
`/notion-dev:ticket <id>`. Epic status in the resolved set → report `epic closed`, stop.

**Per iteration** (`done = 0`; loop while `done < depth`):

1. `epic-doc read`. On `BOOTSTRAP: true` → the commit-before-delegate path of §3.
2. **Pick** — walk `NEXT` in order. A candidate is valid when its live status is unresolved,
   its key is not in `BLOCKED`, and it is not `In Progress` without a worktree of ours (someone
   else has it — skip with a note). `In Progress` **with** our worktree (path computed as
   `ticket` Phase 1.2 computes it) is picked **first** regardless of order: resuming an
   interrupted run is the most valuable next action, and `ticket` owns the resume.
3. **No valid candidate in `NEXT`:** interactive → `AskUserQuestion` over the remaining
   unblocked children; non-interactive → the first unblocked child in Phase/Step order, logged
   as a decision. None → stop with `epic blocked`, printing `Open threads` verbatim.
4. Announce `Next: [<key>] <title> — <the doc's reason>`, then invoke `/notion-dev:ticket
   <key> [flags] | selected by next-task from <doc path>: <reason>[; <user guidance>]`.
5. **After the run:** `done += 1`. The run's own Phase 10 already ran `record`, so re-read on
   the next iteration. **Stop early** when the run ended in a stop or failure (a worktree left
   for inspection is never built over), when `record` reported `failed`, or when the doc now
   reads `Status: closed`.

**Report:** one line per ticket run (key, outcome, PR URL), the doc's final `Next` block
verbatim, and the closeout block from the last delegated run. When the loop stopped early, the
first line says why.

## 6. Verification

`scripts/verify-epic-doc.sh` — a standing invariant (no baseline, no version floor), every
assertion from `scripts/lib/assert.sh`, each proven to fail by mutation before the PR is
reported done. It asserts mechanism, not wording:

| Guard | File | Assertion |
|---|---|---|
| Reader switched | `ticket.md` | one line invoking `epic-doc` in Phase 1.1; `getEpicContext(` absent |
| Bootstrap source kept | `ticket-system/SKILL.md` | `## getEpicContext(` still present |
| Writer present once, in order | `ticket.md`, `finalize.md` | one `record` invocation; ordered after the draft-composition line and before the closeout workspace-pass line |
| Notion side untouched | `ticket.md`, `finalize.md` | `epic-update` invocation line count unchanged (1 each) |
| Format owner | `epic-doc/SKILL.md` | the six `## ` headings; `origin/<git.baseBranch>` on the read path; the three assertion commands; `docs(epic):`; `git rm`; `EPIC-DOC:` block keys; the `120` budget; `--bootstrap` |
| Read never writes | `epic-doc/SKILL.md` | no `git commit` / `git push` in the `read` region |
| Command contract | `next-task.md` | `--depth`, default `1`, `all`, `disable-model-invocation: true`, `/notion-dev:ticket` invocation, the stop-on-failure rule, the inverted epic guard |
| Flag moved | `ticket.md`, `finalize.md` | `disable-model-invocation` absent from `ticket.md`, present in `finalize.md`; the guard sentence present in `ticket.md` |
| Signature registered | `issue-log/references/signatures.md` | `partial:epic-doc` row |
| Surfaces | `README.md`, schema | `next-task` in the command table; `epicDocs` in the schema |
| Release | `plugin.json` | `assert_version_above` the base |

`verify-post-merge-ordering.sh` and the other existing harnesses must still pass unchanged;
`record`'s placement after cleanup is what keeps them green.

## 7. Documentation and release

- **README:** new "Epic docs" subsection under Epics (path, template, single-writer rule, seed
  migration with `git rm`, human edits welcome, `epicDocs.dir`); `/notion-dev:next-task` row
  in the command table; the "reads its Epic before planning" bullet rewritten to name the
  doc; `epic-doc/` in the tree listing; the flag change on `ticket` noted.
- **Issue log:** `partial:epic-doc` — degraded, recorded by `ticket.md` and `finalize.md`,
  once per run: `record` could not assert, write, commit, or push.
- **Version:** `plugin.json` 0.21.2 → 0.22.0. One PR.

## Files touched

| File | Change |
|---|---|
| `plugins/notion-dev/skills/epic-doc/SKILL.md` | new |
| `plugins/notion-dev/commands/next-task.md` | new |
| `plugins/notion-dev/commands/ticket.md` | Phase 1.1 reader; Phase 10 writer step; frontmatter flag; guard sentence |
| `plugins/notion-dev/commands/finalize.md` | Phase 5 writer step |
| `plugins/notion-dev/skills/ticket-system/SKILL.md` | `getEpicContext` description narrowed |
| `plugins/notion-dev/skills/issue-log/references/signatures.md` | `partial:epic-doc` |
| `plugins/notion-dev/schema/notion-dev.config.schema.json` | `epicDocs.dir` |
| `plugins/notion-dev/README.md` | Epic docs, command table, tree |
| `plugins/notion-dev/.claude-plugin/plugin.json` | 0.22.0 |
| `scripts/verify-epic-doc.sh` | new |
