---
name: epic-doc
description: Use when a ticket that belongs to an epic starts (read the epic's markdown brief from origin/<base> as context) and when a ticket resolves (rewrite that brief and commit it to the base branch), and when /notion-dev:next-task needs the epic's recommended next ticket. The single owner of `<epicDocs.dir>/<KEY>-<n>-<slug>.md`.
---

# epic-doc

One concise markdown brief per epic, in the repo, answering four questions: why the epic exists, where it stands, what is open, and what is next. Read by `/notion-dev:ticket` Phase 1.1 and `/notion-dev:next-task`; written by `/notion-dev:ticket` Phase 10 and `/notion-dev:finalize` Phase 5 — and by `/notion-dev:next-task`'s bootstrap. **Nothing else writes it, and no reader ever fetches the Notion epic page for context** — Notion stays the ledger (`epic-update` keeps writing it); this file holds what the ledger cannot say.

Both operations are **best-effort in the `epic-update` sense**: a failure never fails the caller's run, is always stated in the caller's final report, and — for `record` — is recorded as `partial:epic-doc` per `notion-dev:issue-log`.

## The file

**Path:** `<epicDocs.dir>/<KEY>-<n>-<slug>.md`. `epicDocs.dir` comes from `.claude/notion-dev.config.json` (default `docs/epics`). `<KEY>-<n>` is the epic's ticket key; `<slug>` is the epic title kebab-cased exactly as `/notion-dev:ticket` Phase 2.1 slugs a branch (lowercase, non-alphanumerics → `-`, collapse repeats, trim, 40 characters). The H1 carries the exact epic title. **Lookup is always `<KEY>-<n>-*.md`, never by slug**, so a title change in Notion cannot orphan the file.

**Branch.** The brief lives on the branch pull requests merge into — `git.prTargetBranch`, falling back to `git.baseBranch` — called `<epicBranch>` below. `read` and `record` use that one branch for every read and every commit; a brief read from one branch and written to another is stale on the next run, and `/notion-dev:next-task` would bootstrap a second, divergent copy.

**Template.** Six sections, all mandatory, always in this order:

```
# [STO-60] Wallet Indexing
Epic: <notion url> · Status: open | closed · Updated: 2026-09-13 after [STO-67]
Seeded from docs/STO-67-release-plan.md (last at a1b2c3d) · 2026-09-13

## Why
<2-4 sentences: the motivation — from the Notion Overview or the seed>

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

The `Seeded from` line exists only on a brief distilled from a pre-existing hand-written plan (see "Bootstrap" below).

**Rules of content.**

- **Every `## Open threads` bullet names what it blocks or which ticket it informs**, and — for a wait on someone else — what would clear it (`Unblocked by:`). A bullet that names neither is not a thread and is not written.
- **No ticket history, no status table.** Notion is the ledger. The brief holds only what Notion cannot say: why, where we stand, what is waiting on whom, and what is next.
- **`## Next` is an ordered recommendation, not a task list.** Item 1 is the single most recommended **unblocked** ticket with the reason it is first. Further items say what they wait for. The trailing `Blocked:` line names every unresolved child held by an open thread. When the epic is closed, the section reads `epic complete`.
- **Soft budget: 120 lines.** Over it, `record` prunes before it adds. It never prunes a thread that still names an unresolved ticket.
- **Human edits are first-class.** A person may edit the file (for example, "logs arrived — STO-22 unblocked") and commit it. `record` applies a diff evidenced by its inputs and preserves every line it has no evidence to change.

## `read(<epic-id>, <current-ticket-id>?)` → `EPIC_CONTEXT` or `null`

Read-only. Runs before any worktree exists, so it **writes nothing** — not the brief, not a bootstrap, nothing in the primary checkout.

1. `fetchTicket(<epic-id>)` via `notion-dev:ticket-system` and apply the epic predicate: `metadata.parentTaskProperty` empty **and** `metadata.epicMarkerProperty` true — the same predicate `findEpics()`, `getEpicContext` step 2, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply. Not an epic → return `null`. Record the epic's `key`, `title`, `url`, and derive `<KEY>-<n>`.
2. `git fetch origin`, then locate the brief on the remote base: `git ls-tree -r --name-only origin/<epicBranch> -- <epicDocs.dir>/` filtered to `<KEY>-<n>-*.md`, and read it with `git show origin/<epicBranch>:<that path>`. **Always the remote base**, never the primary checkout or a worktree: a stale local branch would hand a run last week's picture. More than one match → take the first in sort order and warn; a second brief for one epic is a defect to name in the report, not to merge silently.
3. **Found** → return the file verbatim as `EPIC_CONTEXT`, plus:
   - `NEXT`: the ordered list parsed from `## Next` — each item's `<KEY>-<n>` and its reason text — and the `Blocked:` line's keys as `BLOCKED`;
   - `STATUS`: `open` or `closed` from the header line;
   - `CHILDREN`: one `listEpicChildren(<epic-id>)` call, `[{ id, key, title, status, url }]`, for the caller's validation. The brief itself carries no statuses, so live ones must travel beside it. When `<current-ticket-id>` is given, mark that entry `(this ticket)` as `getEpicContext` does.
   - `BOOTSTRAP: false`.
4. **Missing** → bootstrap **in memory** per "Bootstrap" below and return the same shape with `BOOTSTRAP: true` and `SEED: <path>` or `SEED: notion`. The file is created later by the first `record` — a resolution's, or `/notion-dev:next-task`'s `record --bootstrap`.

Callers treat `EPIC_CONTEXT` as **background, not requirements** — the ticket body remains the single source of truth for what to build, exactly as it was when this context came from Notion.

## Bootstrap

Runs inside `read` (in memory) and inside `record --bootstrap` (to disk). Produces a complete brief from one of two sources:

1. **Seed search.** On `origin/<epicBranch>`, `git ls-tree -r --name-only origin/<epicBranch> -- docs/` filtered case-insensitively to names containing `<KEY>-<n>` followed by a non-digit or the end of the stem — `STO-6` must match `STO-6-plan.md` and `sto-6.md` but never `STO-60-release-plan.md` — excluding `<epicDocs.dir>/`. This matches a hand-written plan such as `docs/STO-67-release-plan.md` or `docs/sto-306-completion-plan.md`. Exactly one hit → the seed. Several → the most recently committed (`git log -1 --format=%ct origin/<epicBranch> -- <path>`), and every candidate is named in the output block. None → the Notion source below.
2. **Distill a seed** into the template. **Every actionable item carries over**: every wait on someone else with its cause and what clears it, every blocked item, every decision and constraint, every recommended order and the reason for it. What is compressed is reasoning and narrative. `## Why` and `## Goal` come from the seed's opening. Items the seed marks done, struck through, or superseded are dropped — they are history, and Notion holds it.
3. **Notion source** (no seed): identity and `## Overview` via `getEpicContext(<epic-id>, <current-ticket-id>)` — this is now that operation's only job — plus `listEpicChildren(<epic-id>)`, and for order the children's `## Blocked by` sections and their Phase/Step values — `metadata.phaseProperty` and `metadata.stepProperty` from `fetchTicket`, ordered by phase then step, ties by numeric id (fetch each unresolved child once; resolved children need no fetch). `## Why` is the Overview; `## Goal` is what closing every child would achieve, stated in one sentence; `## Open threads` is empty; `## Next` is the unresolved children in dependency order, item 1 being the first with no unresolved `## Blocked by`.

## `record(<id>)` — the single writer

**Args:** `<id>` — the just-resolved ticket's numeric id; or `--bootstrap <epic-id>` (see below).

**Caller-supplied context:** `REPO_ROOT`; `<baseRefName>` and `<merge-commit>` (the branch the PR merged into and the SHA `review-and-merge` returned — `<baseRefName>` must equal `<epicBranch>`; when it does not, the PR merged somewhere the brief does not live: write nothing and return `EPIC-DOC: failed` with `CAUSE: base branch <baseRefName> is not the epic branch <epicBranch>`); `EPIC_REPORT` (the `EPIC-UPDATE:` block — epic identity, `FILED` with the ticket IDs `epic-update` assigned, whether the epic closed); `REVIEW_REPORT` (`BLOCKED` items with external cause and unblocker; `DROPPED` items with rationale); `COMPLETENESS_REPORT` (`not-met` and `unverified` criteria, `TRIAGE` `file` / `drop` entries); `COMPLETION_CLOSEOUT` (the `CLOSEOUT:` block and its `blocked:` / `tracked:` lines from the **completion pass** that ran before the merge); `DECISIONS` (the run's non-interactive decisions); and `DRAFT_REPORT` (the caller's fully composed final report, before its closeout workspace pass). **Any input may be absent; absence is not evidence** — an absent `REVIEW_REPORT` does not mean nothing was blocked.

**Preconditions.** Called from `$REPO_ROOT`, after cleanup, with the primary on the base branch. Before writing anything, assert exactly what the post-merge-hook step asserts:

```bash
git -C $REPO_ROOT rev-parse --abbrev-ref HEAD                    # must equal <baseRefName>
git -C $REPO_ROOT merge-base --is-ancestor <merge-commit> HEAD   # must exit 0
test "$(git -C $REPO_ROOT rev-parse HEAD)" = \
     "$(git -C $REPO_ROOT rev-parse origin/<baseRefName>)"       # must be equal
```

Any failure → write nothing, return `EPIC-DOC: failed` with `CAUSE: <the assertion that failed>`. **A fourth check guards the brief itself:** `git -C $REPO_ROOT status --porcelain -- <brief path>` must be empty. The three assertions above inspect refs and ancestry only, so a human who edited the brief in the primary checkout during a long run — an edit the cleanup pull leaves in place whenever the merged PR did not touch the file — would have it silently overwritten when this step reloads the brief from `origin` and writes over the working tree. Human edits are first-class (see "The file"), so on any uncommitted change to the brief: write nothing, return `EPIC-DOC: failed` with `CAUSE: brief has uncommitted local edits at <brief path> — commit or stash them, then re-run /notion-dev:finalize <pr>`. Refusing is the safe move; merging or committing someone's half-finished edit is not. The three lines are the same three for the same reason: a commit made on a stale or diverged primary would publish the wrong thing to base. On `--bootstrap` there is no merge commit, so the second line is omitted and, in its place, `git -C $REPO_ROOT diff --quiet && git -C $REPO_ROOT diff --cached --quiet` must both succeed **after excluding the two exempt paths `/notion-dev:ticket`'s precondition names** (`-- . ':!.claude/notion-dev.config.json' ':!.mcp.json' ':!.claude/settings.local.json'`) — no other tracked modification. Those files may be tracked and modified in a supported setup, and rejecting them here would abort every first-use bootstrap on such a client. Untracked dirt is fine too: the bootstrap commit stages only the brief and the seed (`git add <brief>`, `git rm <seed>`, never `-a`), so it cannot sweep anything else in.

**Steps.**

1. **Resolve the epic.** From `EPIC_REPORT`: `EPIC-UPDATE: none` → return `EPIC-DOC: none` and stop (the ticket has no epic). Otherwise take the epic key and url from its `EPIC:` line, `git fetch origin`, and load the current brief from `origin/<baseRefName>` as `read` step 2 does. Missing → bootstrap per above; this invocation will create the file.
2. **Apply a diff, not a rewrite.** Touch only lines this run has evidence for:
   - `## Where we stand` — restate in the light of this resolution: what landed (`DRAFT_REPORT`'s PR and ticket lines), what changed the picture.
   - `## Open threads` — **add** one bullet per `REVIEW_REPORT` `BLOCKED` item (cause, what unblocks, which tickets it holds), per `COMPLETION_CLOSEOUT` `blocked:` line, per `not-met` or `unverified` criterion (naming the ticket it belongs to), and per caveat sentence in `DRAFT_REPORT` — the sentences shaped like "worth your attention", "waiting on you", "caveat before you queue it", "note for the next ticket", each rewritten to name what it blocks or informs. **Remove** every bullet this resolution resolved: its `Unblocked by:` happened, or every ticket it named is now resolved. A `tracked:` line and a `FILED` follow-up are tickets, not threads — they appear in `## Next`, never here.
   - `## Decisions & constraints` — add decisions this run made that later tickets must respect: an approach chosen, a version deployed, a `DROPPED` finding whose rationale constrains later work, a `DECISIONS` entry that changed scope.
   - `## Next` — recompute: `listEpicChildren(<epic-id>)` for live statuses; for each unresolved child its `## Blocked by` section and its `metadata.phaseProperty` / `metadata.stepProperty` from `fetchTicket` — order by phase, then step, ties by numeric id (fetch unresolved children only); the open threads decide `Blocked:`. Item 1 is unblocked by construction and carries a one-line reason. Nothing under `Blocked:` appears in the numbered list.
   - Header — `Updated: <YYYY-MM-DD> after [<KEY>-<id>]`. Set `Status: closed` and make `## Next` read `epic complete` when the epic is closed — decided by the epic's **live** status (`fetchTicket(<epic-id>).status` in the resolved set), never only by `EPIC_REPORT` reading `EPIC-UPDATE: closed`: a recovery invocation receives `already-recorded` for a close the original run already performed, and the brief must still catch up. The idempotency signal is the brief's **git history on the epic branch**, not its current header: `git log origin/<epicBranch> --format=%s -- <brief path>` already listing `docs(epic): <KEY>-<n> after <ticket key>` for this ticket means this resolution was recorded by an earlier invocation — even if later children have since moved the header past it — so re-apply nothing from this ticket's reports: recompute `## Next` from live children only, add no thread twice, and never move `Updated:` backwards.
3. **Budget.** Over 120 lines, prune before adding: compress `## Where we stand` first, then `## Decisions & constraints` entries no unresolved ticket depends on. Never prune a thread that names an unresolved ticket.
4. **Write and commit.** When this invocation created the brief from a seed, first cite `git rev-parse --short HEAD` — by precondition this equals `origin/<baseRefName>` and is already pushed, so it is the last base commit that still holds `<seed path>` (`git show <sha>:<seed path>` recovers it) — and put `Seeded from <seed path> (last at <sha>) · <date>` on the header. Then write the file (creating `<epicDocs.dir>/` if absent), `git add` it, and `git rm` the seed in the same commit. **Commit by pathspec, never the whole index:** `git commit --only -m "docs(epic): <KEY>-<n> after <ticket key>" -- <brief path> [<seed path>]` (`git commit -h`: `--only` — commit only specified files). A caller's precondition permits an exempt setup file (`.claude/notion-dev.config.json`, `.mcp.json`, `.claude/settings.local.json`) to be already **staged**; a bare `git commit` would carry it onto the epic branch, and the precondition's exclusion only stops the run from refusing — it unstages nothing. Push: `git push origin <baseRefName>`. After staging, if `git diff --cached --quiet -- <brief path>` succeeds — the brief is byte-identical to the one on `origin/<baseRefName>`, meaning this resolution was already recorded — commit nothing, skip the push, and return `EPIC-DOC: updated` with `THREADS: +0 -0`.
5. **Push rejected** (branch protection, a base that moved) → leave the local commit in place, **do not force**, and return `EPIC-DOC: failed` with `CAUSE: push rejected — <git's message>`. The caller's closeout workspace pass sees the unpushed commit and forces it into a `blocked:` line with that cause.

**`record --bootstrap <epic-id>`** — invoked by `/notion-dev:next-task` when `read` returned `BOOTSTRAP: true`. Preconditions as above minus the ancestor line, with the porcelain check narrowed to tracked modifications outside the caller's exempt paths, as above — the init-generated files and `.claude/settings.local.json` are exempt whether tracked or not, because this step never runs `git add -a`. Resolve the epic via `fetchTicket(<epic-id>)` exactly as `read` step 1 does (there is no `EPIC_REPORT` on this path). Runs the bootstrap to disk: write the distilled brief, `git rm` the seed when there was one, commit `docs(epic): bootstrap <KEY>-<n>`, push. Same rejected-push handling. Returns `EPIC-DOC: created`.

**What `record` must never do:** invent a thread not evidenced by an input; restate ticket history Notion already holds; reword an existing line without evidence from this run; delete a human-written line it has no evidence against; write from anywhere but `$REPO_ROOT` on `<baseRefName>`.

## Output block

Return exactly one block for the caller's report:

```
EPIC-DOC: created | updated | closed | none | failed
PATH: docs/epics/STO-60-wallet-indexing.md                 (omit on none)
SEED: docs/STO-67-release-plan.md · last at a1b2c3d         (only when created from a seed)
THREADS: +2 -1                                              (bullets added / removed this run)
NEXT: [STO-70] Backfill historic wallets — <reason>         (or `epic complete`, or `blocked: <thread>`)
CAUSE: <failed assertion, or push rejection>                (only on failed)
```

`closed` means this run set `Status: closed`. `failed` is the only value that carries `CAUSE`, and it is the only value on which the caller records `partial:epic-doc`. A local commit left behind by a rejected push is named in `CAUSE` so the caller's closeout can find it.
