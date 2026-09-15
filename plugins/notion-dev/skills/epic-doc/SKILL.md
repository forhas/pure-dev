---
name: epic-doc
description: Use when a ticket that belongs to an epic starts (read the epic's markdown brief from origin/<base> as context), when a ticket resolves (rewrite that brief and commit it to the base branch), when /notion-dev:next-task needs the epic's recommended next ticket, and when /notion-dev:new-info routes a fact to the brief (`note`). The single owner of the epic brief — see "The file" below for its path.
---

# epic-doc

One concise markdown brief per epic, in the repo, answering four questions: why the epic exists, where it stands, what is open, and what is next. Read by `/notion-dev:ticket` Phase 1.1 and `/notion-dev:next-task`; written by `/notion-dev:ticket` Phase 10 and `/notion-dev:finalize` Phase 5 — and by `/notion-dev:next-task`'s bootstrap and `/notion-dev:new-info`'s `note` — and by `refresh`, which every start, stop, create and drift repair calls (see below). **Nothing else writes it, and no reader ever fetches the Notion epic page for context** — Notion stays the ledger (`epic-update` keeps writing it); this file holds what the ledger cannot say.

All four operations are **best-effort in the `epic-update` sense**: a failure never fails the caller's run and is always stated in the caller's final report — for `record` it is recorded as `partial:epic-doc`, and for `note` the caller records `partial:new-info`, both per `notion-dev:issue-log`.

## The file

**Path:** `<knowledge.dir>/epic/<KEY>-<n>-<slug>.md`. `knowledge.dir` comes from `.claude/notion-dev.config.json` (default `knowledge`). `<KEY>-<n>` is the epic's ticket key; `<slug>` is the epic title kebab-cased exactly as `/notion-dev:ticket` Phase 2.1 slugs a branch (lowercase, non-alphanumerics → `-`, collapse repeats, trim, 40 characters). The H1 carries the exact epic title. **Lookup is always `<KEY>-<n>-*.md`, never by slug**, so a title change in Notion cannot orphan the file.

**Branch.** The brief lives on the branch pull requests merge into — `git.prTargetBranch`, falling back to `git.baseBranch` — called `<epicBranch>` below. `read` and `record` use that one branch for every read and every commit; a brief read from one branch and written to another is stale on the next run, and `/notion-dev:next-task` would bootstrap a second, divergent copy.

**Template.** Frontmatter (the epic root concept, OKF v0.2) plus six mandatory sections, always in this order:

```
---
type: Epic
title: "[STO-60] Wallet Indexing"
description: "<the Goal in one line>"
status: stable
epic: STO-60
generated: { by: notion-dev:epic-doc, at: 2026-09-13T00:00:00Z }
sources:
  - { id: epic, resource: "<notion url>", title: "[STO-60] Wallet Indexing" }
---
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
In progress: [STO-72] Backfill v2 — since 2026-09-15
Blocked: STO-22, STO-23 (see Open threads).
```

**Every dynamic frontmatter value is written as a double-quoted YAML string with `"` and `\` escaped — a JSON string literal**: the title, the description, the Notion URL, and the source title. A title carrying a quote, or a Goal that begins `Target: deploy`, would otherwise break the block and fail every later `check`; `migrate` serializes the same four values the same way.

**The title is quoted.** Left unquoted, `[STO-60] Wallet Indexing` opens a YAML flow sequence
and then trails a scalar, so the document has no parseable frontmatter at all and `check` reports
every required property missing — which makes the next `capture` write nothing. The quoted form
above is the only one to write, and `sources[].title` is quoted for the same reason.

**The brief carries an `index.md` bullet.** It is the bundle's root concept and it is
`status: stable`, so `scripts/knowledge.py check` requires one bullet in `<knowledge.dir>/index.md`
resolving to it — and a failing `check` makes `notion-dev:knowledge` `capture` write nothing on
every later merge. So every operation here that writes the brief — `record`, `record --bootstrap`
and `note --apply` — first ensures that bullet exists: when no bullet in `index.md` resolves to
`<brief path>`, add `- [<epic title>](epic/<KEY>-<n>-<slug>.md) — <the Goal in one line>` under
the `# epic/` section, creating that section at the top of the file when it is absent. Nothing
else in `index.md` is touched, and `<knowledge.dir>/index.md` joins the commit's pathspec so the
bullet lands in the same commit as the brief. When the bullet is already there, this writes
nothing.

The `Seeded from` line exists only on a brief distilled from a pre-existing hand-written plan (see "Bootstrap" below). A bullet under `## Decisions & constraints` or `## Open threads` may link a concept plus one clause instead of stating the fact in prose (`- [Offline deploy](../decision/offline-deploy.md) — binds STO-70.`); `record` and `note` write the link form whenever a concept for the fact exists, and the prose form otherwise.

**Rules of content.**

- **Every `## Open threads` bullet names what it blocks or which ticket it informs**, and — for a wait on someone else — what would clear it (`Unblocked by:`). A bullet that names neither is not a thread and is not written.
- **No ticket history, no status table.** Notion is the ledger. The brief holds only what Notion cannot say: why, where we stand, what is waiting on whom, and what is next.
- **`## Next` is an ordered recommendation, not a task list.** Item 1 is the single most recommended **unblocked** ticket with the reason it is first. Further items say what they wait for. The trailing `Blocked:` line names every unresolved child held by an open thread. When the epic is closed, the section reads `epic complete`.
- **The three lists of `## Next` partition the unresolved children with no overlap**: the numbered
  list (runnable now or after a listed dependency), `In progress:` (claimed — every child whose
  live status is `statusMap.inProgress`, comma-separated in numeric-id order, each
  `[<KEY>-<n>] <title> — since <YYYY-MM-DD>`, the date the line first named the key), and
  `Blocked:` (held by an open thread). A child in none of the three is a defect `refresh`
  repairs, never a warning. An in-progress child that a thread also names is `In progress:` —
  the claim wins. Item 1 is never in progress. A stopped run is one thread bullet,
  `- **[<KEY>-<n>] stopped at <phase>** — <cause>; worktree at <path>. Unblocked by: /notion-dev:ticket <KEY>-<n> (resumes).`,
  and its key is `Blocked:` until a `start` removes the bullet.
- **Soft budget: 120 lines.** Over it, `record` prunes before it adds. It never prunes a thread that still names an unresolved ticket.
- **Human edits are first-class.** A person may edit the file (for example, "logs arrived — STO-22 unblocked") and commit it. `record` applies a diff evidenced by its inputs and preserves every line it has no evidence to change.

## `read(<epic-id>, <current-ticket-id>?, KNOWLEDGE_CONTEXT?)` → `EPIC_CONTEXT` or `null`

Read-only. Runs before any worktree exists, so it **writes nothing** — not the brief, not a bootstrap, nothing in the primary checkout. `read` is now a thin parse over a `retrieve` result: the fetch itself lives in `notion-dev:knowledge`, and `read` never runs `iwe` or `git` on its own.

1. `KNOWLEDGE_CONTEXT` supplied by the caller → use it, **no fetch of any kind — not Notion, not git.** Otherwise invoke the `notion-dev:knowledge` skill, operation `retrieve(<epic-id>, <ticket-title>?, <current-ticket-id>)` once — the id goes in the **third** argument; `read` is given no title, so the lexical seed is simply omitted, whereas passing the id where the title belongs makes `--lexical "<ticket id>"` a seed that matches nothing — this applies the epic predicate itself, exactly as `findEpics()`, `getEpicContext` step 2, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply it; not an epic → return `null` — and take its result as `KNOWLEDGE_CONTEXT`.
2. Return `EPIC_CONTEXT` — the root document (`KNOWLEDGE_CONTEXT`'s first fenced document, frontmatter stripped) — plus the fields already parsed from it: `NEXT` (the ordered list from `## Next`, each item's `<KEY>-<n>` and its reason text), `BLOCKED` (the `Blocked:` line's keys), `STATUS` (`open` or `closed` from the header line), `CHILDREN` (one `listEpicChildren(<epic-id>)` call inside `retrieve`, `[{ id, key, title, status, url }]`, for the caller's validation — when `<current-ticket-id>` is given, marked `(this ticket)` as `getEpicContext` does), and `BOOTSTRAP`
   — and `DRIFT`. `read` writes the root document to a temp file, assembles the state JSON
   `refresh` shows from `CHILDREN` and the epic's live status (`status_class` = `resolved` when the status is in
   the resolved set, `in_progress` when it equals `statusMap.inProgress`, else `open`; every
   unresolved child's `## Blocked by` keys, `metadata.phaseProperty`, `metadata.stepProperty`
   from one `fetchTicket` each — the same fetches `record` step 2 makes), and `thread_blocked` — from the current `## Open threads`, for each bullet the keys it says it blocks or holds (`blocks STO-22, STO-23`, `holds STO-x`), never a key after `Unblocked by:`, never a key a bullet merely informs (`revisit in STO-71`), and never a stop bullet (the script adds those from the bullets themselves) — the same judgment `record` step 2 applies when it writes `Blocked:`. Then runs the derivation
   command `refresh` names with no `--reason`, and reads only its stderr: `DRIFT: 0` → `DRIFT:
   false`; otherwise `DRIFT: true` with the `drift:` lines verbatim. `read` still writes nothing —
   not the brief, not a lock, nothing in the primary checkout: it runs before any worktree exists.
   Whoever writes next repairs the drift — `/notion-dev:ticket` through its Phase 2 `start`,
   `/notion-dev:next-task` through `refresh drift`. `BOOTSTRAP: true` (with `SEED: <path>` or `SEED: notion`) means the brief does not exist yet — `retrieve` bootstrapped it **in memory**; the file is created later by the first `record` — a resolution's, or `/notion-dev:next-task`'s `record --bootstrap`.

Callers treat `EPIC_CONTEXT` as **background, not requirements** — the ticket body remains the single source of truth for what to build, exactly as it was when this context came from Notion.

## Bootstrap

Runs inside `read` (in memory, via `retrieve`) and inside `record --bootstrap` (to disk). Produces a complete brief from one of two sources — seed search now also covers `<knowledge.dir>/epic/`, so a bootstrap never mistakes the epic's own brief for the seed it is meant to replace:

1. **Seed search.** On `origin/<epicBranch>`, `git ls-tree -r --name-only origin/<epicBranch> -- docs/` filtered case-insensitively to names containing `<KEY>-<n>` followed by a non-digit or the end of the stem — `STO-6` must match `STO-6-plan.md` and `sto-6.md` but never `STO-60-release-plan.md` — excluding `<knowledge.dir>/epic/`. This matches a hand-written plan such as `docs/STO-67-release-plan.md` or `docs/sto-306-completion-plan.md`. Exactly one hit → the seed. Several → the most recently committed (`git log -1 --format=%ct origin/<epicBranch> -- <path>`), and every candidate is named in the output block. None → the Notion source below.
2. **Distill a seed** into the template. **Every actionable item carries over**: every wait on someone else with its cause and what clears it, every blocked item, every decision and constraint, every recommended order and the reason for it. What is compressed is reasoning and narrative. `## Why` and `## Goal` come from the seed's opening. Items the seed marks done, struck through, or superseded are dropped — they are history, and Notion holds it.
3. **Notion source** (no seed): identity and `## Overview` via `getEpicContext(<epic-id>, <current-ticket-id>)` — this is now that operation's only job — plus `listEpicChildren(<epic-id>)`, and for order the children's `## Blocked by` sections and their Phase/Step values — `metadata.phaseProperty` and `metadata.stepProperty` from `fetchTicket`, ordered by phase then step, ties by numeric id (fetch each unresolved child once; resolved children need no fetch). `## Why` is the Overview; `## Goal` is what closing every child would achieve, stated in one sentence; `## Open threads` is empty; `## Next` is the unresolved children in dependency order, item 1 being the first with no unresolved `## Blocked by`.

## `refresh(<epic-id>, <reason>)` — the derived writer

Recomputes the derived parts of the brief from live state and nothing else: the header's
`Status:` and `Updated:`, the whole `## Next` region, and — for two reasons — one stop bullet
under `## Open threads`.
`<reason>` is one of `start <KEY>-<n>`, `stop <KEY>-<n> <phase> <cause> <worktree-path>`, `create <KEY>-<n>`, `drift`.

| reason | caller | effect beyond `## Next` |
|---|---|---|
| `start <KEY>-<n>` | `/notion-dev:ticket` Phase 2, after `updateStatus(id, "inProgress")` | removes that key's stop bullet when one exists |
| `stop <KEY>-<n> <phase> <cause> <worktree-path>` | `/notion-dev:ticket`'s failure-and-stop path | adds (or replaces) that key's stop bullet |
| `create <KEY>-<n>` | `/notion-dev:create-task` after a ticket gets an epic parent | none |
| `drift` | `/notion-dev:next-task` step 1 on `DRIFT: true` | none |

**Inputs, all live:** `fetchTicket(<epic-id>).status`, `listEpicChildren(<epic-id>)`, and one
`fetchTicket` per unresolved child for its `## Blocked by` keys, `metadata.phaseProperty` and
`metadata.stepProperty` — exactly what `record` step 2 fetches. `refresh` never reads the Notion
epic page body and never runs `iwe`.

**Derivation.** Write the current brief (loaded from `origin/<epicBranch>` by the write path's
step 2) to a temp file, assemble the state JSON (plus `stop: { key, phase,
cause, worktree }` on a `stop`), and run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" next --brief <tmp brief> --state <tmp state.json> --today <YYYY-MM-DD>
```

```json
{
  "epic": { "key": "STO-60", "status_class": "open" },
  "children": [
    { "key": "STO-71", "id": 71, "title": "Cache metrics", "status_class": "open",
      "blocked_by": ["STO-70"], "phase": 2, "step": 1 }
  ],
  "thread_blocked": ["STO-22"],
  "stop": { "key": "STO-70", "phase": "Phase 7", "cause": "review loop stalled",
            "worktree": "../btc-worktrees/btc-STO-70" }
}
```

`status_class` is `resolved | in_progress | open` (resolved set, `statusMap.inProgress`, else); `id` is the numeric `idProperty` value as an integer; `phase` and `step` are integers or `null`; `blocked_by` lists `<KEY>-<n>` strings; `thread_blocked` is assembled as `read` states; `stop` is present only on a `stop` reason.

`` exit 0 = the brief was already true (`unchanged`); exit 1 = the rendered brief differs (the ordinary success path — write stdout over the brief); exit 2 = malformed brief or JSON (`failed`, `CAUSE:` the stderr line). ``

with `--reason <word> <key>` for `start`, `stop` and `create`, and no `--reason` for `drift`. Its
stdout is the new brief in full — the `## Next` region, the header and the stop bullet rewritten,
every other byte preserved; its stderr lists the drift it repaired. The script partitions the
unresolved children, orders the numbered list by phase, step, then numeric id, puts the first
child whose every `## Blocked by` key is resolved at item 1 with its reason preserved when item 1
did not change (else `unblocked; <dep> landed` or `first in phase order`), writes `In progress:`
with each key's `since` preserved, and `Blocked:` from the threads' keys plus every stop bullet's
key. `stop` adds the bullet; `start` removes it. `Status: closed` and `epic complete` exactly when
the epic's live status is in the resolved set. Exit 0 means the brief was already true.

**Outcome.** Byte-identical brief → `unchanged`, no commit, `COMMIT: none`. Otherwise commit
through `## The write path` below with the subject
`docs(epic): <KEY>-<n> start <key>`,
`docs(epic): <KEY>-<n> stop <key>`,
`docs(epic): <KEY>-<n> create <key>` or
`docs(epic): <KEY>-<n> refresh`,
by the pathspec `-- <brief path> <knowledge.dir>/index.md` (the catalog bullet rule of "The file"
applies here too), and return `refreshed`.

**Best-effort**, like every operation here: `failed` is recorded by the caller as
`partial:epic-doc` and never stops a run — except that `/notion-dev:next-task` does not select
from a brief whose drift refresh failed.

## The write path — every commit from the primary checkout

`refresh`, `record`, `record --bootstrap`, `note --apply` and `notion-dev:knowledge` `capture`
(both forms) commit and push from `$REPO_ROOT` through these five steps and no others. Stated
once here; the others cite it.

1. **Lock.** Unless the caller passed `LOCK_HELD`, take the primary lock:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section <name> --wait <seconds>` — `LOCK_HELD` means an enclosing section already holds it.
   Exit 1 → `failed`, `CAUSE: primary lock held by <run> (<section>) since <time>`; a printed
   `stale:` line → record `lock-stale:primary` per `notion-dev:issue-log` and name the old owner
   in the report. Read-only checks of the primary and `git worktree add` never take it.
2. **Establish the base.** `git -C $REPO_ROOT fetch origin <epicBranch>`. The primary must be on
   `<epicBranch>`; the operations whose contract allows a checkout — `refresh` (all reasons) and
   `record --bootstrap` — run `git -C $REPO_ROOT checkout <epicBranch>` when the primary is clean
   outside the exempt paths; when it is not clean, the existing branch assertion applies instead —
   the primary must already be on `<epicBranch>` or the operation is `failed` with `CAUSE: primary
   checkout is dirty and not on <epicBranch>`; the others assert the branch as before. Then
   `git -C $REPO_ROOT pull --ff-only origin <epicBranch>`. A `--ff-only` failure → `failed`,
   `CAUSE: <epicBranch> has diverged from origin` — never stash, never reset a diverged base.
   After this step the three ref assertions of `/notion-dev:ticket` Phase 9 hold by
   construction, and the porcelain check on the operation's pathspec must be empty, as before.
   Under `--branch <noteBranch>` (`/notion-dev:new-info --pr`) the fetch still runs, but in
   place of the on-branch check and the `--ff-only` pull: HEAD's branch must be `<noteBranch>`
   and `git -C $REPO_ROOT merge-base --is-ancestor origin/<epicBranch> HEAD` must exit 0 — the
   branch was cut from the epic branch and still contains it.
3. **Derive and commit.** Write the files, `git add` them, then, if
   `git diff --cached --quiet -- <pathspec>` succeeds → `unchanged`, `COMMIT: none`, go to 5.
   Otherwise `git commit --only -m "<subject>" -- <pathspec>`.
4. **Push, converge on rejection.** `git push origin <epicBranch>`. On a non-fast-forward
   rejection: `git -C $REPO_ROOT fetch origin <epicBranch>`, then assert
   `git rev-list origin/<epicBranch>..HEAD` names **exactly one** commit — this attempt's own.
   Anything else → `failed`, commit left in place, `CAUSE: push rejected — <git's message>`,
   as before. One commit → `git reset --hard origin/<epicBranch>` (safe only here: step 2
   required a clean pathspec and the rev-list proved the sole local commit is ours), re-derive
   against the fresh files, and go back to step 3. **Three attempts.** `record` and `note --apply`
   re-apply their diff *semantically* — the bullets they add and remove, the sentence they
   restate — to the fresh brief; `refresh` and `capture` simply re-derive. The third rejection
   is `failed` with the local commit left in place and the caller's `blocked:` closeout line, as
   before. Under `--branch <noteBranch>` there is no push and no retry.
5. **Unlock.** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>` — skipped when the caller passed `LOCK_HELD`. Report `ATTEMPTS: <n>`, the number of times step 3 ran.

## `record(<id>)` — the single writer

**Args:** `<id>` — the just-resolved ticket's numeric id; or `--bootstrap <epic-id>` (see below).

**Caller-supplied context:** `REPO_ROOT`; `<baseRefName>` and `<merge-commit>` (the branch the PR merged into and the SHA `review-and-merge` returned — `<baseRefName>` must equal `<epicBranch>`; when it does not, the PR merged somewhere the brief does not live: write nothing and return `EPIC-DOC: failed` with `CAUSE: base branch <baseRefName> is not the epic branch <epicBranch>`); `EPIC_REPORT` (the `EPIC-UPDATE:` block — epic identity, `FILED` with the ticket IDs `epic-update` assigned, whether the epic closed); `REVIEW_REPORT` (`BLOCKED` items with external cause and unblocker; `DROPPED` items with rationale); `COMPLETENESS_REPORT` (`not-met` and `unverified` criteria, `TRIAGE` `file` / `drop` entries); `COMPLETION_CLOSEOUT` (the `CLOSEOUT:` block and its `blocked:` / `tracked:` lines from the **completion pass** that ran before the merge); `DECISIONS` (the run's non-interactive decisions); and `DRAFT_REPORT` (the caller's fully composed final report, before its closeout workspace pass). **Any input may be absent; absence is not evidence** — an absent `REVIEW_REPORT` does not mean nothing was blocked.

**Preconditions.** Called from `$REPO_ROOT`, after cleanup, with the primary on the base branch, inside the caller's `record` lock section (`LOCK_HELD`). The write path's step 2 establishes what the post-merge-hook step asserts:

```bash
git -C $REPO_ROOT rev-parse --abbrev-ref HEAD                    # must equal <baseRefName>
git -C $REPO_ROOT merge-base --is-ancestor <merge-commit> HEAD   # must exit 0
test "$(git -C $REPO_ROOT rev-parse HEAD)" = \
     "$(git -C $REPO_ROOT rev-parse origin/<baseRefName>)"       # must be equal
```

Any failure → write nothing, return `EPIC-DOC: failed` with `CAUSE: <the assertion that failed>`. **A fourth check guards the brief and its catalog:** `git -C $REPO_ROOT status --porcelain -- <brief path> <knowledge.dir>/index.md` must be empty — the index rides in the same `--only` commit, so an uncommitted human edit to it would otherwise be published to base unreviewed. The three assertions above inspect refs and ancestry only, so a human who edited the brief in the primary checkout during a long run — an edit the cleanup pull leaves in place whenever the merged PR did not touch the file — would have it silently overwritten when this step reloads the brief from `origin` and writes over the working tree. Human edits are first-class (see "The file"), so on any uncommitted change to the brief or the index: write nothing, return `EPIC-DOC: failed` with `CAUSE: brief or index has uncommitted local edits at <path> — commit or stash them, then re-run /notion-dev:finalize <pr>`. Refusing is the safe move; merging or committing someone's half-finished edit is not. The three lines are the same three for the same reason: a commit made on a stale or diverged primary would publish the wrong thing to base. On `--bootstrap` there is no merge commit, so the second line is omitted and, in its place, `git -C $REPO_ROOT diff --quiet && git -C $REPO_ROOT diff --cached --quiet` must both succeed **after excluding the two exempt paths `/notion-dev:ticket`'s precondition names** (`-- . ':!.claude/notion-dev.config.json' ':!.mcp.json' ':!.claude/settings.local.json'`) — no other tracked modification. Those files may be tracked and modified in a supported setup, and rejecting them here would abort every first-use bootstrap on such a client. Untracked dirt is fine too: the bootstrap commit stages only the brief and the seed (`git add <brief>`, `git rm <seed>`, never `-a`), so it cannot sweep anything else in.

**Steps.**

1. **Resolve the epic.** From `EPIC_REPORT`: `EPIC-UPDATE: none` → return `EPIC-DOC: none` and stop (the ticket has no epic). Otherwise take the epic key and url from its `EPIC:` line, `git fetch origin`, and load the current brief from `origin/<baseRefName>` exactly as `notion-dev:knowledge` `retrieve` step 2 locates the root — against `<baseRefName>`, which by precondition equals `<epicBranch>`. Missing → bootstrap per above; this invocation will create the file.
2. **Apply a diff, not a rewrite.** Touch only lines this run has evidence for:
   - `## Where we stand` — restate in the light of this resolution: what landed (`DRAFT_REPORT`'s PR and ticket lines), what changed the picture.
   - `## Open threads` — **add** one bullet per `REVIEW_REPORT` `BLOCKED` item (cause, what unblocks, which tickets it holds), per `COMPLETION_CLOSEOUT` `blocked:` line, per `not-met` or `unverified` criterion (naming the ticket it belongs to), and per caveat sentence in `DRAFT_REPORT` — the sentences shaped like "worth your attention", "waiting on you", "caveat before you queue it", "note for the next ticket", each rewritten to name what it blocks or informs. **Remove** every bullet this resolution resolved: its `Unblocked by:` happened, or every ticket it named is now resolved. A `tracked:` line and a `FILED` follow-up are tickets, not threads — they appear in `## Next`, never here.
   - `## Decisions & constraints` — add decisions this run made that later tickets must respect: an approach chosen, a version deployed, a `DROPPED` finding whose rationale constrains later work, a `DECISIONS` entry that changed scope.
   - `## Next` — recompute through `refresh`'s derivation: assemble the state JSON from
     `listEpicChildren(<epic-id>)` and one `fetchTicket` per unresolved child, run the
     `knowledge.py next` command `refresh` names with `--reason resolve <ticket key>`, and take
     its `## Next` region and header; the open threads this step wrote decide `thread_blocked`.
   - Header — `Updated: <YYYY-MM-DD> after [<KEY>-<id>]`. Set `Status: closed` and make `## Next` read `epic complete` when the epic is closed — decided by the epic's **live** status (`fetchTicket(<epic-id>).status` in the resolved set), never only by `EPIC_REPORT` reading `EPIC-UPDATE: closed`: a recovery invocation receives `already-recorded` for a close the original run already performed, and the brief must still catch up. The idempotency signal is the brief's **git history on the epic branch**, not its current header: `git log origin/<epicBranch> --format=%s -- <brief path>` already listing `docs(epic): <KEY>-<n> after <ticket key>` for this ticket means this resolution was recorded by an earlier invocation — even if later children have since moved the header past it — so re-apply nothing from this ticket's reports: recompute `## Next` from live children only, add no thread twice, and never move `Updated:` backwards.
3. **Budget.** Over 120 lines, prune before adding: compress `## Where we stand` first, then `## Decisions & constraints` entries no unresolved ticket depends on. Never prune a thread that names an unresolved ticket.
4. **Write and commit.** When this invocation created the brief from a seed, first cite `git rev-parse --short HEAD` — by precondition this equals `origin/<baseRefName>` and is already pushed, so it is the last base commit that still holds `<seed path>` (`git show <sha>:<seed path>` recovers it) — and put `Seeded from <seed path> (last at <sha>) · <date>` on the header. Then write the file — the frontmatter of the template when this creates it, or the existing frontmatter preserved verbatim except `updated: { by, at }` otherwise, the `Status:` header line unchanged — creating the epic directory if absent, `git add` it, and `git rm` the seed in the same commit. **Commit and push through `## The write path`** — subject `docs(epic): <KEY>-<n> after <ticket key>`, pathspec `-- <brief path> <knowledge.dir>/index.md [<seed path>]` (`--only`, for the reason the write path gives). The path's byte-identical test is the existing "already recorded" rule: `THREADS: +0 -0`, no commit, no push.
5. **Push rejected** after the write path's third attempt → leave the local commit in place, **do not force**, and return `EPIC-DOC: failed` with `CAUSE: push rejected — <git's message>`. The caller writes that commit into its report's closeout as a `blocked:` line with this cause — the closeout's workspace pass enumerates the workspace, not unpushed work, so the caller must name it itself.

**`record --bootstrap <epic-id>`** — invoked by `/notion-dev:next-task` when `read` returned `BOOTSTRAP: true`. Preconditions as above minus the ancestor line, with the porcelain check narrowed to tracked modifications outside the caller's exempt paths, as above — the init-generated files and `.claude/settings.local.json` are exempt whether tracked or not, because this step never runs `git add -a`. Resolve the epic via `fetchTicket(<epic-id>)` and the epic predicate exactly as `notion-dev:knowledge` `retrieve` step 1 applies it (there is no `EPIC_REPORT` on this path). Runs the bootstrap to disk: write the distilled brief and its `index.md` bullet, `git rm` the seed when there was one, commit `docs(epic): bootstrap <KEY>-<n>` through `## The write path` by the same pathspec (brief, `<knowledge.dir>/index.md`, seed); its rejected-push outcome is the write path's. Returns `EPIC-DOC: created`. **`--branch <noteBranch>`** — passed by `/notion-dev:new-info --pr`: the first two of the precondition lines above, the primary-on-`<baseRefName>` check and the remote-equality check, are replaced by the two branch checks the `note` section states; the bootstrap commit is made on that branch; nothing is pushed.

**What `record` must never do:** invent a thread not evidenced by an input; restate ticket history Notion already holds; reword an existing line without evidence from this run; delete a human-written line it has no evidence against; write from anywhere but `$REPO_ROOT` on `<baseRefName>`.

## Output block

Return exactly one block for the caller's report:

```
EPIC-DOC: created | updated | closed | refreshed | unchanged | none | failed
PATH: knowledge/epic/STO-60-wallet-indexing.md              (omit on none)
SEED: docs/STO-67-release-plan.md · last at a1b2c3d         (only when created from a seed)
THREADS: +2 -1                                              (bullets added / removed this run)
NEXT: [STO-70] Backfill historic wallets — <reason>         (or `epic complete`, or `blocked: <thread>`)
IN-PROGRESS: STO-72                                         (keys on the In progress line; `none` when empty)
DRIFT: <one line per repaired finding>                      (or `none`)
COMMIT: <sha> | none
ATTEMPTS: 1                                                 (write-path attempts)
CAUSE: <failed assertion, lock timeout, or push rejection>  (only on failed)
```

`closed` means this run set `Status: closed`. `failed` is the only value that carries `CAUSE`, and it is the only value on which the caller records `partial:epic-doc`. A local commit left behind by a rejected push is named in `CAUSE` so the caller's closeout can find it. `refreshed` and `unchanged` are `refresh`'s two success values.

## `note(<fact>, <epic-id>)` and `note --apply <epic-id>` — the fact writer

Invoked only by `/notion-dev:new-info`. Two phases, so the caller can put a diff in front of a person before anything is committed. Both are best-effort in the `epic-update` sense: a failure never fails the caller's run and is stated in its report; the caller records `partial:new-info` per `notion-dev:issue-log`.

**Caller-supplied context:** the fact and its `<short fact>` (the fact truncated to 60 characters at a word boundary); `EPIC_CONTEXT` and `CHILDREN` from `read` — except under `--branch`, where the current brief the caller passes may instead come from `HEAD:<brief path>` on the note branch, because commits there are local until the caller pushes and `read`, which always resolves the brief on `origin/<epicBranch>`, is not the source on that path; for `--apply`, the accepted proposal, `REPO_ROOT`, `<baseRefName>` (must equal `<epicBranch>`, exactly as for `record`), and optionally `--branch <noteBranch>`.

### Propose — `note(<fact>, <epic-id>)`

**Writes nothing.** Fetch each unresolved child once (`fetchTicket`) for its `## Blocked by`, Phase/Step, `## Requirements` and `## Acceptance Criteria`. Apply four relevance tests, in order; every test that fires is recorded, and the first one that fires makes the epic `affected`:

1. **Clears a thread.** An `## Open threads` bullet whose `Unblocked by:` the fact satisfies, or whose wait the fact ends. Effect: remove the bullet; every ticket it named as blocked is `UNBLOCKED` unless another thread still names it.
2. **Adds a constraint.** The fact is something a later ticket must respect and the brief does not already say it — a version now deployed, an environment that now exists, an approach now approved or rejected. Effect: one bullet under `## Decisions & constraints`, dated.
3. **Contradicts a decision.** A `## Decisions & constraints` bullet the fact makes false. Effect: the bullet is **replaced**, not appended to — the old text survives only in git — and the replacement names the fact that changed it.
4. **Changes what is runnable.** After 1–3, recompute `## Next` through `refresh`'s derivation with `--reason new-info`, as `record` step 2 does: `CHILDREN` for live statuses, each unresolved child's `## Blocked by` and its Phase/Step, the remaining threads deciding `Blocked:`. A changed item 1 or a changed `Blocked:` line fires this test even when 1–3 did not. A fact that only *adds* a wait ("the customer asked us to hold STO-71 until their audit") is a thread **added** — the mirror of test 1 — with what it blocks and what would clear it, and it fires here.

A fact that fires none is `unaffected`, with a one-line reason (`no thread, decision, or child mentions <the fact's subject>`), and the brief is untouched.

**Requirements and Acceptance Criteria impact.** For each unresolved child, compare the fact against its `## Requirements` and `## Acceptance Criteria`: a sentence that states an assumption the fact contradicts (a version, an environment, a count, an approach) is listed as `AC-IMPACT: [<KEY>-<n>] <the sentence>`. This is a finding for a person; nothing here edits a ticket.

Then `## Where we stand`: one sentence when the fact changed the picture (a deployment, an approval, a customer decision); nothing when it only touched a thread or a constraint. Header: `Updated: <YYYY-MM-DD> after new-info`. `Status: closed` and `## Next` reading `epic complete` only when the epic's **live** status (`fetchTicket(<epic-id>).status`) is in the resolved set — closure is decided exactly as `record` decides it. Budget: `record`'s rule — over 120 lines, prune before adding, never a thread that names an unresolved ticket.

**Diff discipline is `record`'s, verbatim:** touch only lines the fact evidences; never reword a line without evidence; never delete a human-written line the fact does not contradict; never invent a thread. The one thing `note` does that `record` never does is *replace* a decision bullet (test 3): a fact that contradicts a decision is precisely the evidence `record` lacks.

Return the proposal block:

```
NOTE: affected | unaffected
REASON: <one line — the tests that fired, or why none did>
CLEARED: <thread text> → unblocks STO-22, STO-23        (one line per test-1 hit)
ADDED: <decision or thread bullet text>                  (one line per test-2 hit or thread added)
REPLACED: <old bullet> → <new bullet>                    (one line per test-3 hit)
NEXT: [STO-70] <title> — <reason>  |  unchanged
AC-IMPACT: [STO-71] <the requirement or criterion>       (zero or more lines)
DIFF:
<unified diff of the brief, or `none`>
```

### Apply — `note --apply <epic-id>`

Called from `$REPO_ROOT` with the accepted proposal. **Preconditions are exactly `record --bootstrap`'s precondition block, applied by reference:** the primary on `<baseRefName>`, HEAD equal to the remote, no tracked modification outside the exempt paths, and the brief's own porcelain empty. The three commands are stated once, under `record`, and not repeated here. With `--branch <noteBranch>` (the caller's `--pr` path), HEAD's branch must be `<noteBranch>` and `git merge-base --is-ancestor origin/<epicBranch> HEAD` must exit 0 — the branch was cut from the epic branch and still contains it. Those two checks stand **in place of the first two** inherited lines — the primary-on-`<baseRefName>` check, which HEAD on a note branch cannot satisfy, and the remote-equality check, which cannot hold from the second commit on; the two porcelain checks are unchanged. Any failure → `EPIC-DOC: failed` with `CAUSE:`, nothing written. `record --bootstrap` accepts the same `--branch` form on that path: the same two swapped assertions, commit, no push.

1. Write the brief with the accepted diff — the frontmatter of the template when this creates the file, or the existing frontmatter preserved verbatim except `updated: { by, at }` otherwise, the `Status:` header line unchanged — creating the epic directory if absent, write the brief's `index.md` bullet per "The file" when it is not there yet, and `git add <brief path> <knowledge.dir>/index.md`.
2. If `git diff --cached --quiet -- <brief path> <knowledge.dir>/index.md` succeeds — the brief is byte-identical to the one already on the branch and its catalog bullet was already there, meaning this fact was already applied — commit nothing, skip the push, and return `EPIC-DOC: updated` with `THREADS: +0 -0` and `COMMIT: none`. The caller reads `COMMIT: none` — never the thread count, which is `+0 -0` on a constraint-only commit too — as "nothing landed" and skips its Notion note and ticket comments.
3. Otherwise commit and push through `## The write path` — subject `docs(epic): note <KEY>-<n> — <short fact>`, the same pathspec; skipped push under `--branch`.
4. **Push rejected after the write path's third attempt** → leave the local commit in place, **do not force**, return `EPIC-DOC: failed` with `CAUSE: push rejected — <git's message>`. HEAD now differs from the remote, so the caller must not apply another epic on this run; it reports the rest as skipped and its closeout finds the unpushed commit.

Return the `EPIC-DOC:` block exactly as `record` does — `closed` when this apply set `Status: closed`; `THREADS: +a -r` counting bullets added and removed; `NEXT:` the new item 1 — plus one line `record` never carries:

```
UNBLOCKED: STO-22, STO-23                                   (tickets CLEARED freed; empty when none)
COMMIT: <sha> | none                                        (the note commit made, or none on the byte-identical path)
```
