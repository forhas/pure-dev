# `/notion-dev:new-info` — route one new fact to every epic brief it affects

**Date:** 2026-09-14 · **Plugin:** `notion-dev` · **Release:** 0.22.0 → 0.23.0 (minor)

## Problem

Since 0.22.0 every epic has one markdown brief (`<epicDocs.dir>/<KEY>-<n>-<slug>.md`, owned by
`notion-dev:epic-doc`) that says why the epic exists, where it stands, what is waiting on whom,
and what is next. Two things write it: a ticket resolution (`record`) and a human. Nothing routes
a fact that arrives *between* resolutions — "the customer deployed v1.4.2 on 2026-09-14",
"Asher approved removing the opening-price guard" — to the several epics it touches. Today a
person opens each brief, has to know which `## Open threads` bullet the fact clears and which
tickets that unblocks, edits by hand, and then tells Notion separately, or does not.

## Goal

One command that takes one fact, reads every brief, decides per epic whether and how the fact
changes it, applies exactly that change with `record`'s diff discipline, commits it to the epic
branch, tells the Notion epic and the tickets it unblocked, and reports what it did and what it
skipped — so a fact learned once lands everywhere it matters, and `/notion-dev:next-task` picks
it up on its next read.

Non-goals: rewriting a ticket's Requirements or Acceptance Criteria from a one-line fact;
inventing a thread the fact does not evidence; changing what `record` or `read` do; a second
config key; running the clients' knowledge-bundle hooks from this command (see decision 7).

## Decisions taken during design

The first six were taken in the previous session and confirmed against the code. Decisions 7
and 8 are where the code disagreed with the plan; each names what the code says and the
resolution.

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Scope | The `--epic` ids given; otherwise every brief under `epicDocs.dir` plus every open epic in Notion with no brief yet | A fact is rarely known to touch only one epic; the whole set is the default. |
| 2 | Relevance | Judged per brief against four tests, and the reason recorded either way | Skipping is a decision, not silence. |
| 3 | Writer | A new `epic-doc` operation `note`, two phases: `propose` (writes nothing) and `apply` (writes, commits, pushes) | The brief keeps one format owner. The gate in decision 4 needs a diff *before* a commit, which `record` never had to offer. |
| 4 | Landing | Direct commit to `<epicBranch>` per epic, behind a per-epic interactive gate (Apply / Skip / Revise); `--non-interactive` applies and logs; `--pr` puts every change on one branch and drives one PR through `notion-dev:review-and-merge` | Same slot and same assertions as `record` and the post-merge hooks. A human sees every diff by default; the PR path is for a protected epic branch. |
| 5 | Notion epic | `appendToSection(EPIC_ID, "Notes", …)` with a dated entry; never rewrite; the Resolution Log stays for resolutions | Append is what the ledger does everywhere else. |
| 6 | Tickets | `postComment` on each ticket a cleared thread unblocks and on each ticket whose Requirements or Acceptance Criteria the fact contradicts; never edit a ticket body | A comment is reversible and visible; a rewritten criterion from a one-line fact is neither. |
| 7 | Knowledge bundles | **Not run from this command.** The previous plan ran `git.postMergeHooks` after the note commits. Both clients' hooks (`knowledge-capture`) are ticket-shaped: step 1 derives a ticket key from the branch, PR title, or merge-commit subject, and the rest reads that PR's diff and review threads. Invoked after a `docs(epic): note …` commit there is no ticket, no PR and no diff to read — the hook either aborts at step 1 or, per the foundry variant's own rule, "captures nothing" | Running a hook whose inputs do not exist is not "updating the bundle", and a new config key was ruled out. The fact reaches the bundle the way everything else does: the next ticket merge's hook, which reads the brief the note just changed. The report says so per epic. |
| 8 | Bootstrap | An open epic with no brief is judged on the **in-memory** brief `read` already builds; only an *affected* one is written to disk (`record --bootstrap`, then `note --apply`) | The previous plan bootstrapped every brief-less epic first. Distilling a 400-line plan for an epic the fact does not touch is work with no reader; an unaffected epic loses nothing by waiting for `/notion-dev:next-task`. |
| 9 | Issue log | One signature, `partial:new-info` | One run, one degraded outcome, regardless of which of its best-effort steps failed. |

## 1. The command

```
/notion-dev:new-info <information> [--epic <id>]… [--non-interactive] [--pr]
```

`plugins/notion-dev/commands/new-info.md`, frontmatter `disable-model-invocation: true` — a
fact is something a person knows; nothing in the plugin has one to route.

**Args.** `--epic <id>` (repeatable, or `--epic=<id>`): restrict scope to these epics; each
accepts every id form `/notion-dev:ticket` accepts. `--non-interactive`: never pause; apply
every `affected` proposal and log each decision for the report. `--pr`: land through one pull
request instead of direct commits (§4). Everything that is not a flag is `<information>`, the
fact, verbatim; empty → fail with usage. A short form for commit subjects and Notion entries,
`<short fact>`, is the fact truncated to 60 characters at a word boundary.

**Standing rule — runtime issues.** As in `next-task.md`: anything unexpected is recorded via
`notion-dev:issue-log` at the moment it happens; a failure to write the log never fails the run.

**Preconditions.** `REPO_ROOT` first (primary checkout from `git worktree list`);
`.claude/notion-dev.config.json` present and read from `$REPO_ROOT`; an `origin` remote;
`gh auth status` and `jq --version` succeed (the `--pr` path and the closeout need them); and
the clean-tree rule of `/notion-dev:ticket`'s precondition block applied verbatim, including its
exactly-two exempt dirt kinds and its `git stash -u` remedy wording. `dependencies.superpowers`
and `dependencies.featureDev` are **not** required — this command builds nothing. Then
`git -C $REPO_ROOT checkout <epicBranch> && git -C $REPO_ROOT pull --ff-only origin <epicBranch>`
(`<epicBranch>` = `git.prTargetBranch`, falling back to `git.baseBranch`, per
`notion-dev:epic-doc`); a `--ff-only` failure stops the run with the same diverged-base report
`/notion-dev:ticket` Phase 9 step 4 gives — never stash or discard.

**Not an epic guard.** Every `--epic` id goes through `fetchTicket` and the epic predicate
(`metadata.parentTaskProperty` empty **and** `metadata.epicMarkerProperty` true). A page that
is not an epic is named and the run stops before touching anything — a mistyped id must not
silently narrow the scope.

## 2. Scope

Without `--epic`:

1. **Briefs on disk.** `git ls-tree -r --name-only origin/<epicBranch> -- <epicDocs.dir>/`
   filtered to `<KEY>-<n>-*.md`; each yields an epic key. This is the authoritative list of
   what enters the scope: a brief whose epic Notion no longer returns (deleted, re-parented)
   is still listed here, then skipped at 3.1 with reason `not an epic`, and the report names
   it so a person can retire or re-parent the file.
2. **Open epics without a brief.** `findEpics()` via `notion-dev:ticket-system`. It returns no
   status, so `fetchTicket` each hit whose key has no brief from step 1 and keep those whose
   status is not in the resolved set. `findEpics` returning `null` (marker or parent slot
   unusable — it records its own signature) means step 2 contributes nothing; say so in the
   report and continue with step 1's list alone.

A closed epic with a brief is judged like any other: its brief reads `Status: closed`, and a
fact that reopens a closed epic is a Notion status change, not this command's call — it is
skipped with reason `epic closed`. A brief whose header says `closed` while the live status is
unresolved is treated as open (the stale-header rule `next-task.md` already applies).

Order: by numeric epic id. Every epic in scope appears in the report exactly once.

## 3. Per epic

### 3.1 Read

`notion-dev:epic-doc` `read(<epic-id>)` → `EPIC_CONTEXT`, `NEXT`, `BLOCKED`, `STATUS`,
`CHILDREN`, `BOOTSTRAP`, `SEED`. `null` (not an epic) → skip with reason. `BOOTSTRAP: true` →
the in-memory brief is judged in 3.2 exactly like a committed one; only an affected epic
reaches disk (3.4).

### 3.2 Propose — `note(<fact>, <epic-id>)`

`epic-doc`'s new operation, phase one. **Writes nothing.** Inputs: the fact, `EPIC_CONTEXT`,
`CHILDREN`, and for each unresolved child its body (`fetchTicket`, once) — needed for
`## Blocked by`, Phase/Step, and the Requirements / Acceptance Criteria comparison below.

**Four relevance tests**, applied in order; the first that fires makes the epic `affected`,
and every test that fires is recorded:

1. **Clears a thread.** An `## Open threads` bullet whose `Unblocked by:` the fact satisfies,
   or whose wait the fact ends. Effect: remove the bullet; every ticket the bullet named as
   blocked is `UNBLOCKED` (unless another thread still names it).
2. **Adds a constraint.** The fact is something a later ticket must respect and the brief
   does not already say it (a version now deployed, an environment that now exists, an approach
   now approved or rejected). Effect: one bullet under `## Decisions & constraints`, dated.
3. **Contradicts a decision.** A `## Decisions & constraints` bullet the fact makes false.
   Effect: the bullet is **replaced**, not appended to — the old text survives only in git —
   and the replacement names the fact that changed it.
4. **Changes what is runnable.** After 1–3, recompute `## Next` exactly as `record` step 2
   does: `CHILDREN` for live statuses, each unresolved child's `## Blocked by` and Phase/Step,
   the remaining threads deciding `Blocked:`. A changed item 1 or a changed `Blocked:` line
   fires this test even when 1–3 did not (a fact that only adds a thread — "the customer asked
   us to hold STO-71 until their audit" — is a thread **added**, the mirror of test 1).

A fact that fires none is `unaffected`, with the one-line reason (`no thread, decision, or
child mentions <the fact's subject>`), and the brief is untouched.

**Requirements and Acceptance Criteria impact.** For each unresolved child, compare the fact
against its `## Requirements` and `## Acceptance Criteria`: a requirement or criterion that
states an assumption the fact contradicts (a version, an environment, a count, an approach) is
listed as `AC-IMPACT: [<KEY>-<n>] <the sentence>`. This is a finding for a person; the command
never edits a ticket body (decision 6).

Then `## Where we stand`: one sentence when the fact changed the picture (a deployment, an
approval, a customer decision), none when it only touched a thread or a constraint. Header:
`Updated: <YYYY-MM-DD> after new-info`; `Status: closed` and `## Next` = `epic complete` only
when the epic's **live** status is in the resolved set, as `record` decides closure. Budget:
`record`'s rule — over 120 lines, prune before adding, never a thread naming an unresolved
ticket.

**Diff discipline is `record`'s, verbatim:** touch only lines the fact evidences; never reword
a line without evidence; never delete a human-written line the fact does not contradict;
never invent a thread. The one thing `note` does that `record` never does is *replace* a
decision bullet (test 3), because a fact that contradicts a decision is exactly the evidence
`record` lacks.

**Output — the proposal block:**

```
NOTE: affected | unaffected
REASON: <one line; the tests that fired, or why none did>
CLEARED: <thread text> → unblocks STO-22, STO-23        (one line per test-1 hit)
ADDED: <decision or thread bullet text>                  (one line per test-2 hit or thread added)
REPLACED: <old bullet> → <new bullet>                    (one line per test-3 hit)
NEXT: [STO-70] <title> — <reason>  |  unchanged
AC-IMPACT: [STO-71] <the requirement or criterion>       (zero or more lines)
DIFF:
<unified diff of the brief, or `none`>
```

### 3.3 Gate

`unaffected` → skip; the report names the epic with `REASON`. No gate.

`affected`, interactive: print the proposal block and `AskUserQuestion` — **Apply** (default),
**Skip**, **Revise** (the user's text is guidance; re-run `note` propose with it and gate
again; at most three revisions, then Apply / Skip only). When `AC-IMPACT` is non-empty, a
second question per listed ticket: **Comment** (default) / **Nothing** — the command never
offers to edit the ticket.

`affected`, non-interactive: Apply, and comment on every `AC-IMPACT` ticket; both logged as
decisions for the report.

### 3.4 Apply — `note --apply <epic-id>`

`epic-doc`'s new operation, phase two, from `$REPO_ROOT`. Input: the accepted proposal (its
diff, `CLEARED`, `NEXT`), `REPO_ROOT`, `<epicBranch>` as `<baseRefName>`, and on the `--pr`
path `--branch <noteBranch>` (§4).

**Preconditions — `record --bootstrap`'s, by reference, not repeated:** the primary is on
`<baseRefName>` (`rev-parse --abbrev-ref HEAD`), HEAD equals `origin/<baseRefName>`, no
tracked modification outside the exempt paths, and the brief's own porcelain is empty. Any
failure → `EPIC-DOC: failed` with `CAUSE:`; nothing written. The `note` section of
`epic-doc/SKILL.md` cites `record`'s precondition block rather than restating its three
commands, so the existing harness anchors on those commands stay unique.

**Bootstrap first when `BOOTSTRAP: true`:** invoke `record --bootstrap <epic-id>` exactly as
`next-task.md` does (it writes the distilled brief, `git rm`s the seed, commits
`docs(epic): bootstrap <KEY>-<n>`, pushes; on the `--pr` path it takes `--branch <noteBranch>`
and commits without pushing), then re-derive the proposal on the bootstrapped brief: on the
direct path re-run `read` and re-propose. Under `--pr`, `read` is **not** the source — it
always resolves the brief on `origin/<epicBranch>`, where the local bootstrap commit is not
yet present — so `EPIC_CONTEXT` comes from `git show HEAD:<brief path>` (the bootstrap's
`PATH:`) with the `CHILDREN` already in hand, and only 3.2 re-runs. Either way the proposal is
re-derived, not re-gated, unless its `DIFF` changed. `failed` there stops this epic with the
bootstrap's `CAUSE:`.

**Then:** write the brief; `git add <brief>`; if `git diff --cached --quiet -- <brief>`
succeeds, the accepted diff is already on `origin/<baseRefName>` — commit nothing, return
`EPIC-DOC: updated` with `THREADS: +0 -0`, and the caller **skips 3.5 and 3.6** for this epic
(a re-run must not append a second Notion note or a second comment). Otherwise
`git commit --only -m "docs(epic): note <KEY>-<n> — <short fact>" -- <brief path>` and
`git push origin <baseRefName>`. Rejected push → local commit left in place, **do not force**,
`EPIC-DOC: failed`, `CAUSE: push rejected — <git's message>` — and because HEAD now differs
from `origin/<baseRefName>`, **every later epic in this run fails the same precondition**:
the command stops the loop, reports the remaining epics as `skipped — earlier push rejected`,
and the closeout's workspace pass forces the unpushed commit into `blocked:`.

**Output:** the `EPIC-DOC:` block `record` returns, same five values, `closed` when this
apply set `Status: closed`, plus `UNBLOCKED: STO-22, STO-23` (the tickets `CLEARED` freed,
empty when none).

### 3.5 Notion epic

`appendToSection(EPIC_ID, "Notes", <entry>)` — a `divider` block, then:

```
### <YYYY-MM-DD HH:MM UTC> — new info
**Fact:** <the fact, verbatim>
**Brief:** <brief path> — <THREADS> · next: <NEXT>
**Cleared:** <thread> (unblocks STO-22, STO-23)      (per CLEARED; omit when none)
**Changed:** <ADDED / REPLACED lines>                (omit when none)
```

Best-effort, like every `epic-update` write: a failed append is a warning, the run continues,
and the epic's report line says `notion: failed`. `Notes` is added to `ticket-system`'s palette
table (`gray`, no callout, epic pages only) so the section the plugin writes is one it styles.

### 3.6 Tickets

For each key in `UNBLOCKED`, `postComment(<id>, …)`:

> New information (<date>): <fact>. The thread "<thread text>" in <brief path> is cleared, so
> this ticket is no longer waiting on it. — /notion-dev:new-info

For each `AC-IMPACT` ticket the gate accepted:

> New information (<date>): <fact>. This may change "<the requirement or criterion>" — please
> re-check it before the ticket starts; the plugin does not edit requirements. — /notion-dev:new-info

Best-effort; a failed comment is named in the report. A ticket that appears in both lists gets
one comment carrying both paragraphs.

## 4. `--pr`

Same scope, proposal and gate; the landing differs:

1. After preconditions, `git -C $REPO_ROOT checkout -b <noteBranch> origin/<epicBranch>`,
   `<noteBranch>` = `notes/new-info-<YYYYMMDD>-<slug>` (`<slug>` from `<short fact>`, kebab-cased
   as `/notion-dev:ticket` Phase 2.1 slugs a branch). No worktree: the primary is clean by
   precondition and returns to `<epicBranch>` in step 5.
2. Every `note --apply` carries `--branch <noteBranch>`. Its preconditions then read: HEAD's
   branch equals `<noteBranch>`; `git merge-base --is-ancestor origin/<epicBranch> HEAD` exits 0
   (the branch was cut from, and still contains, the epic branch). Those two checks replace
   the **first two** inherited lines — the primary-on-`<baseRefName>` check, which HEAD on a
   note branch cannot satisfy, and the HEAD-equals-origin line, which cannot hold from the
   second commit on; both porcelain checks, the brief's included, are unchanged. Commit per epic as in 3.4; **no push per epic**. A `BOOTSTRAP: true` epic is
   bootstrapped on this branch too — `record --bootstrap` given `--branch` commits without
   pushing, under the same three lines.
3. Zero commits after the loop → `git checkout <epicBranch>`, `git branch -D <noteBranch>`,
   report `nothing to land`. Otherwise `git push -u origin <noteBranch>` and open the PR —
   `gh pr create --base <epicBranch> --body-file -` as Phase 5 of `/notion-dev:ticket` spells
   it — with a body listing every epic changed and its `REASON`. A rejected push there leaves
   the branch and its commits local, **never** forces, adds the §5 `blocked:` line naming
   `<noteBranch>` and git's rejection, skips the PR, and goes to the report.
4. `notion-dev:review-and-merge <pr> [--non-interactive] --pre-merge-check "<the completion
   pass requirement /notion-dev:ticket Phase 7 passes, verbatim>"`. A run that stops before the
   merge leaves the branch and PR for inspection and reports both; nothing in 3.5–3.6 runs.
5. Merged → `git checkout <epicBranch> && git pull --ff-only origin <epicBranch>`,
   `git branch -D <noteBranch>`, confirm the remote branch is gone (Phase 9 step 3). Then 3.5
   and 3.6 for every epic whose commit landed.

## 5. Report

Print, in this order:

- The fact, `<short fact>`, and the scope (`N briefs, M open epics without a brief`, or the
  `--epic` list).
- One line per epic in scope: `[<KEY>-<n>] <title> — updated | created+updated | skipped —
  <REASON>` then, indented, `cleared:` / `added:` / `replaced:` / `next:` / `unblocked:` /
  `commented:` / `notion: ok | failed` / `AC-impact:` lines, each only when non-empty. An
  epic that failed carries its `CAUSE:`.
- Per updated epic on a client with `git.postMergeHooks`: `knowledge bundle: not touched —
  <hook names> run at the next ticket merge and read this brief` (decision 7).
- Non-interactive decisions (every auto-Apply, every auto-comment).
- On `--pr`: the PR URL and merge SHA, or where it stopped.
- **Closeout:** compose the draft above, then invoke the **workspace pass** of
  `notion-dev:session-closeout` and end with its `CLOSEOUT:` block verbatim, followed by its
  `tracked:` and `blocked:` lines. The workspace pass does not enumerate unpushed
  work — that is the completion pass's source 2 — so **the command adds that line itself**,
  before invoking the pass: `- blocked: docs(epic): note commit <sha> unpushed on
  <epicBranch> — push rejected: <git's message>; unblocked by pushing once the branch accepts
  it`. There is no completion pass on the direct-commit path (nothing merges);
  on `--pr` the completion pass runs as step 4's pre-merge check.

**`partial:new-info`** — recorded once per run when any `note --apply` returned `failed`, a
bootstrap on this path returned `failed`, a Notion append failed, or a ticket comment failed.
Kind `degraded`, site `new-info.md`. Registered per `signatures.md`'s "Adding a signature";
its subject is not a config property, so the `Context` whitelist needs no entry.

## 6. Verification

`scripts/verify-new-info.sh` — standing invariant, every assertion from `scripts/lib/assert.sh`,
each proven to fail by mutation. Anchors:

| Guard | File | Assertion |
|---|---|---|
| User-only | `new-info.md` | `disable-model-invocation: true` in the frontmatter |
| Flags | `new-info.md` | `--epic`, `--non-interactive`, `--pr` each named once in the args paragraph |
| Reads through the owner | `new-info.md` | one `read(<epic-id>)` invocation; one `note(<fact>, <epic-id>)`; one `note --apply` |
| Scope | `new-info.md` | `findEpics()` named; the `<KEY>-<n>-*.md` filter, both in the scope region |
| Gate | `new-info.md` | `Apply`, `Skip`, `Revise` on one line; the AC-impact question |
| Never edits tickets | `new-info.md` | `never edits a ticket body`; `upsertSection` absent |
| Notion append | `new-info.md` | `appendToSection(EPIC_ID, "Notes"` once; `upsertSection` absent |
| Comments | `new-info.md` | `postComment` in the tickets section |
| Hooks not run | `new-info.md` | `postMergeHooks` exactly once in the report region (`assert_count`) and absent before it (`assert_absent`); `not touched` |
| Stop on rejected push | `new-info.md` | `earlier push rejected` |
| Closeout | `new-info.md` | the workspace-pass invocation line; `CLOSEOUT:` |
| `--pr` mechanics | `new-info.md` | `checkout -b <noteBranch> origin/<epicBranch>`; every apply `carries \`--branch <noteBranch>\``; `merge-base --is-ancestor origin/<epicBranch> HEAD`; `notion-dev:review-and-merge <pr>`; `pull --ff-only origin <epicBranch>` |
| Signature | `new-info.md`, `signatures.md` | `record \`partial:new-info\` per \`notion-dev:issue-log\``; the registry row |
| `note` exists | `epic-doc/SKILL.md` | `## \`note(` heading; the `### Apply — \`note --apply <epic-id>\`` heading; `--branch <noteBranch>`; the `NOTE: affected \| unaffected` block; `REPLACED:`; `AC-IMPACT:`; `UNBLOCKED:`; `docs(epic): note`; `git diff --cached --quiet -- <brief` in the note region; `do not force` in the note region |
| `note` region does not restate record's assertions | `epic-doc/SKILL.md` | `rev-parse --abbrev-ref HEAD` absent from the note region |
| Palette | `ticket-system/SKILL.md` | the `Notes` palette row |
| Surfaces | `README.md` | `/notion-dev:new-info` row; the Epic docs bullet naming it |
| Release | `plugin.json` | `assert_version_above … 0.22.0` |

**`verify-epic-doc.sh` changes, in the same commit as the `note` section:** its `record`
region becomes `find_line '^## \`record\('` … `find_line '^## \`note\('` (today it runs to end
of file, and `note`'s `--branch` assertion would be a second `merge-base --is-ancestor` match),
and the `docs\(epic\):` count declaration moves from 3 to the new count. Every other anchor is
unchanged; all other harnesses must pass unchanged.

## 7. Documentation and release

- **README:** `/notion-dev:new-info` row in the command table; under "Epic docs", a **New
  information** bullet (what it does, the gate, `--non-interactive`, `--pr`, that tickets get
  comments not edits, that bundles update at the next merge).
- **`epic-doc/SKILL.md`:** frontmatter description names the third operation; `## \`note(…)\``
  section after `record`; the "Nothing else writes it" sentence now names `/notion-dev:new-info`.
- **`ticket-system/SKILL.md`:** `Notes` palette row; `appendToSection`'s epic-page note.
- **Issue log:** `partial:new-info` row.
- **Version:** `plugin.json` 0.22.0 → 0.23.0. One PR.

## Files touched

| File | Change |
|---|---|
| `plugins/notion-dev/commands/new-info.md` | new |
| `plugins/notion-dev/skills/epic-doc/SKILL.md` | `note` operation; description |
| `plugins/notion-dev/skills/ticket-system/SKILL.md` | `Notes` palette row |
| `plugins/notion-dev/skills/issue-log/references/signatures.md` | `partial:new-info` row |
| `plugins/notion-dev/README.md` | command row; Epic docs bullet |
| `plugins/notion-dev/.claude-plugin/plugin.json` | 0.23.0 |
| `scripts/verify-new-info.sh` | new |
| `scripts/verify-epic-doc.sh` | record-region bound; `docs(epic):` count |
| `docs/superpowers/specs/2026-09-14-new-info-design.md` | this file |
| `docs/superpowers/plans/2026-09-14-new-info.md` | the plan |
