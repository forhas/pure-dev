# Brief freshness and parallel tickets

**Date:** 2026-09-15 · **Plugin:** `notion-dev` 0.24.0 → 0.25.0 (PR 1) → 0.26.0 (PR 2) · **Status:** approved design

## Problem

The epic brief (`notion-dev:epic-doc`) is written at three moments only: a resolution
(`record`), a fact (`note`), and first use (`record --bootstrap`). Between those moments the
epic keeps changing and the brief does not:

- A ticket **starts**: Phase 2 of `/notion-dev:ticket` sets Notion `In Progress`, and `## Next`
  still lists that ticket as item 1. `/notion-dev:ticket` never checks whether another session
  already holds the ticket; only `/notion-dev:next-task` does.
- A ticket is **created** under the epic by `/notion-dev:create-task`: `## Next` does not know it.
- A run **stops or fails** with a worktree left for inspection: the brief says nothing.
- A **human changes Notion** (cancels a child, closes one by hand, edits a `## Blocked by`,
  reopens the epic): nothing reconciles until the next resolution.
- Two writers **collide**: a rejected push is a hard `EPIC-DOC: failed`, which makes
  `/notion-dev:next-task` stop. With parallel sessions this is the common case.

And every commit to the epic branch is made from the **primary checkout**, which two sessions
on one machine would fight over: Phase 9 checks it out and pulls it, `record`, `capture` and
`note --apply` commit and push from it and require it equal to `origin`.

## Goal

Two things, in this order, verified one before the other:

1. **The brief is true after every change that affects the epic**, and its `## Next` section
   is always a correct, minimal answer to "what should the next session start". The brief stays
   concise: it exists so nothing falls between the cracks and so the order of resolution is
   clear. Nothing else is added to it.
2. **Several tickets of one epic resolve in parallel on one machine**, each in its own session
   and worktree, without stepping on each other's brief, bundle, primary checkout, Notion epic
   page, version bump, or pick.

## Decisions

| # | decision | chosen |
|---|---|---|
| 1 | scope of parallelism | **one machine**; the claim is local (the worktree), Notion status is the mirror, no cross-machine claim |
| 2 | which events write the brief | start, stop-or-fail, resolve, create, new-info, and Notion drift detected at read time; **nothing else** (no PR-opened, no review-stall lines) |
| 3 | delivery | **one spec, two PRs**: PR 1 = freshness + lock, verified on a client; PR 2 = parallel picking, claim liveness, rebase-before-merge |
| 4 | mechanism | **re-derive, don't patch**: `## Next` and the header status are derived from live state by one operation, `refresh`; retries re-derive instead of replaying a patch |
| 5 | determinism | the `## Next` rendering is a **script** (`knowledge.py next`), so two sessions produce identical bytes and `unchanged` is decidable |
| 6 | Notion drift | reconciled **at the next read**, never by polling or a sweep (consistent with the valid-until-superseded rule of the 2026-09-14 spec) |
| 7 | primary-checkout contention | a **directory lock** taken with `mkdir`, implemented by `knowledge.py lock`, held only for the sections that commit from the primary or rewrite the Notion epic page |
| 8 | merge contention | **rebase once at the merge gate**; the version-bump conflict resolves itself, every other conflict stops the run as today |

---

## §1 The brief

**One addition to `## Next`: an `In progress:` line**, between the numbered list and `Blocked:`.

```
## Next
1. **[STO-71] Cache metrics** — unblocked; STO-70 landed. Why now: …
2. [STO-73] Alerting — after STO-71 (reads its metrics).
In progress: [STO-72] Backfill v2 — since 2026-09-15
Blocked: STO-22, STO-23 (see Open threads).
```

- The `In progress:` line lists every unresolved child whose live status is
  `statusMap.inProgress`, comma-separated in numeric-id order, each as
  `[<KEY>-<n>] <title> — since <YYYY-MM-DD>`. `since` is the date the line first named the key;
  `refresh` preserves it from the existing line and uses today's date for a key that is new to
  the line. The line is omitted when empty.
- **The three lists partition the unresolved children with no overlap**: numbered (runnable now
  or after a listed dependency), `In progress:` (claimed), `Blocked:` (held by an open thread).
  Every unresolved child appears in exactly one. An in-progress child that an open thread also
  names goes to `In progress:` — the claim wins, the thread remains in `## Open threads`. A child
  in none of the three is a defect `refresh` repairs, never a warning.
- **Item 1 is never in progress.** It is the first numbered child whose every `## Blocked by`
  key is in the resolved set. Under parallel sessions this is what makes item 1 "the next thing a
  new session can start".
- **A stopped run is an open thread**, one bullet under `## Open threads`:
  `**[STO-70] stopped at Phase 7** — <cause>; worktree at <path>. Unblocked by: /notion-dev:ticket STO-70 (resumes).`
  The ticket leaves `In progress:` and appears on `Blocked:`. A later `start` of the same key
  removes the bullet. The bullet names what it blocks (the ticket itself) and what clears it, so
  it satisfies the existing rule of content for threads.
- **The header line** keeps `Status:` and `Updated: <YYYY-MM-DD> after <what>`; `<what>` gains
  `start [<KEY>-<n>]`, `stop [<KEY>-<n>]`, `create [<KEY>-<n>]` and `refresh`, alongside the
  existing `[<KEY>-<n>]` (a resolution) and `new-info`.
- **Nothing else is added**: no session ids, no PR links, no timestamps beyond the date, no
  history. `## Why`, `## Goal`, `## Where we stand` and `## Decisions & constraints` are never
  touched by `refresh`; `record` and `note` write them under their existing evidence rules.
- The 120-line soft budget and the "human edits are first-class" rule are unchanged. `refresh`
  replaces exactly one region — the `## Next` section from its heading to the line before the
  next heading or end of file — plus the header line's `Updated:` and `Status:` values, plus the
  one stop bullet on a `stop` or `start` reason. Every other byte is preserved.

**No migration.** A brief without the `In progress:` line is ordinary drift; the first `refresh`
writes it. `knowledge.py check` does not validate `## Next`.

## §2 `refresh(<epic-id>, <reason>)` — the derived writer

A fourth `epic-doc` operation. `<reason>` is one of:

| reason | who calls it | extra input |
|---|---|---|
| `start <KEY>-<n>` | `/notion-dev:ticket` Phase 2, after `updateStatus(id, "inProgress")` | — |
| `stop <KEY>-<n> <phase> <cause> <worktree-path>` | `/notion-dev:ticket`'s failure-and-stop path | the stop bullet's fields |
| `create <KEY>-<n>` | `/notion-dev:create-task` when the ticket got an epic parent | — |
| `drift` | `/notion-dev:next-task` step 1 when `read` reported `DRIFT: true` | — |

**Inputs, all live:** `fetchTicket(<epic-id>).status`; `listEpicChildren(<epic-id>)`; for each
unresolved child one `fetchTicket` for its `## Blocked by` keys, `metadata.phaseProperty`,
`metadata.stepProperty`. This is exactly what `record` step 2 fetches today, so a `refresh`
costs what a resolution's `## Next` recompute already costs. `refresh` never reads the Notion
epic page body and never runs `iwe`.

**Derivation** is `knowledge.py next` (§5). The skill assembles the input JSON, runs the script
against the current brief, and replaces the `## Next` region with the script's output. Item 1's
reason text is preserved when item 1's key is unchanged; otherwise it is templated by the script.
`Status: closed` and `## Next` reading `epic complete` exactly when the epic's live status is in
the resolved set — the rule `record` and `note` already apply.

**Reasons with side effects on `## Open threads`:** `stop` adds the §1 bullet for its key (once;
re-running a stop for the same key replaces the bullet's cause and phase). `start` removes the
stop bullet for its key when one exists. No other reason touches threads.

**Outcome.** Byte-identical brief → `unchanged`, no commit. Otherwise the write path (§3) commits
`docs(epic): <KEY>-<n> <reason-word> [<key>]` — `start STO-70`, `stop STO-70`, `create STO-74`,
`refresh` — and returns `refreshed`.

**`record` and `note` are unchanged at their entry points** but their `## Next` recompute (record
step 2 fourth bullet; note test 4) is now defined as "the derivation of `refresh`", and their
commits go through the write path. That removes the second and third copies of the recipe.

**Drift detection is `read`'s.** `read` already holds the parsed lists and live `CHILDREN`. It
reports `DRIFT: true` with one line per finding when: an unresolved child is in none of the three
lists; a child is in the wrong list for its live status (resolved but listed; in progress but
numbered or blocked; numbered but held by a thread); the header `Status:` disagrees with the
live epic status; `## Next` lacks the `In progress:` line while some child is in progress. `read`
still writes nothing — it runs before any worktree exists. Whoever writes next repairs it:
`/notion-dev:ticket` through its Phase 2 `start`, `/notion-dev:next-task` through `refresh drift`.

**Best-effort, like every `epic-doc` operation.** A `failed` refresh is recorded as
`partial:epic-doc` per `notion-dev:issue-log` and stated in the caller's report; it never stops
a run. The one exception is stated in §7: `/notion-dev:next-task` does not select from a brief
whose drift refresh failed.

**Output block** (the `EPIC-DOC:` block, extended):

```
EPIC-DOC: created | updated | closed | refreshed | unchanged | none | failed
PATH: knowledge/epic/STO-60-wallet-indexing.md
THREADS: +1 -0
NEXT: [STO-71] Cache metrics — <reason>  |  epic complete  |  blocked: <thread>
IN-PROGRESS: STO-72                                          (keys; `none` when empty)
DRIFT: <one line per repaired finding>  |  none
COMMIT: <sha> | none
ATTEMPTS: 1                                                  (write-path attempts, §3)
CAUSE: <failed assertion, lock timeout, or push rejection>   (only on failed)
```

## §3 The write path — every commit from the primary checkout

Used by `refresh`, `record`, `record --bootstrap`, `note --apply` and `notion-dev:knowledge`
`capture` (both forms). Stated once, in `epic-doc`, and referenced by the others.

1. **Lock.** Take the primary lock (§4) unless the caller passed `LOCK_HELD`.
2. **Establish the base.** `git -C $REPO_ROOT fetch origin <epicBranch>`. The primary must be
   on `<epicBranch>`; when the operation's contract allows a checkout (`refresh start|stop|create`,
   `record --bootstrap`, `refresh drift`) and the primary is clean outside the exempt paths,
   `git checkout <epicBranch>`; otherwise the existing branch assertion applies. Then
   `git pull --ff-only origin <epicBranch>`. A `--ff-only` failure is `failed` with
   `CAUSE: <epicBranch> has diverged from origin` — never stash, never reset a diverged base.
   After this step the three ref assertions of `/notion-dev:ticket` Phase 9 hold by construction
   (branch name; merge ancestor, where a merge is involved; HEAD equals `origin/<epicBranch>`),
   and the porcelain check on the operation's pathspec must be empty, as today.
3. **Derive and commit.** Write the files, `git add` them, `git commit --only -- <pathspec>`.
   `git diff --cached --quiet -- <pathspec>` succeeding before the commit → `unchanged`,
   `COMMIT: none`, skip to step 5.
4. **Push, converge on rejection.** `git push origin <epicBranch>`. On a non-fast-forward
   rejection: assert `git rev-list origin/<epicBranch>..HEAD` names exactly the one commit this
   attempt made (anything else → `failed`, commit left in place, `CAUSE: push rejected — <git's
   message>`, as today); `git fetch origin <epicBranch>`; stash the dirty exempt setup files when
   there are any, `git reset --hard origin/<epicBranch>`, pop the stash with `--index`;
   go back to step 3 against the fresh files. **Three attempts.** `record` and `note --apply`
   re-apply their diff *semantically* — the bullets they add and remove, the sentence they
   restate — to the fresh brief; `refresh` and `capture` simply re-derive. The third rejection is
   `failed` with the local commit left in place and the existing `blocked:` closeout line.
   Under `--branch <noteBranch>` (`/notion-dev:new-info --pr`) there is no push and no retry.
5. **Unlock**, unless `LOCK_HELD`. Report `ATTEMPTS:`.

The reset is `--hard`, but the three exempt setup files are stashed across it. Step 2 required a
clean *pathspec*, not a clean tree, and the preconditions permit tracked dirt outside it (the
init-generated setup files, `.claude/settings.local.json`) — which the `rev-list` assertion does
not license discarding. A softer reset is not the answer: it leaves every path an upstream commit
changed sitting in the index as a staged reversion. Hard reset for correctness of the fetched
tree, stash for the user's permitted edits.

## §4 The primary lock

- **Form:** the directory `$REPO_ROOT/.claude/notion-dev/locks/primary/`, created with `mkdir`
  (atomic on Linux, macOS, WSL and Windows). Inside it one file, `owner`, three lines:
  `run: <run id>`, `section: <name>`, `since: <ISO-8601 UTC>`. The `.claude/notion-dev/`
  directory is already self-ignored.
- **Run ids:** `<KEY>-<n>` for a ticket run, `next-task <KEY>-<n>`, `new-info`, `knowledge`,
  `finalize <pr>`, `create-task`.
- **Command:** `knowledge.py lock take --run <id> --section <name> [--wait <seconds>]`,
  `lock release --run <id>`, `lock status`. `take` exits 0 when taken or already held by the
  same run id (re-entrant), 1 on timeout (printing the holder), 2 on a bad invocation.
  `release` removes the directory only when `owner` names the same run id; exit 1 otherwise.
  `status` prints the holder or `free`.
- **Sections that hold it:**

  | flow | section | span |
  |---|---|---|
  | `/notion-dev:ticket` | `start` | Phase 2: `updateStatus(inProgress)` → `refresh start` |
  | `/notion-dev:ticket` | `record` | Phase 8.2 (`epic-update`) → Phase 9 cleanup → post-merge hooks → Phase 10 `record` |
  | `/notion-dev:ticket` | `stop` | the failure path's one `refresh stop` |
  | `/notion-dev:finalize` | `record` | Phase 3 → Phase 4 → Phase 5 `record` |
  | `/notion-dev:next-task` | `bootstrap` / `drift` | the one `record --bootstrap` or `refresh drift` |
  | `/notion-dev:new-info` | `apply` | every `note --apply` and `capture --fact` of the run |
  | `/notion-dev:knowledge` | `capture` / `migrate` | the whole command |
  | `/notion-dev:create-task` | `create` | the one `refresh create` |

  Read-only checks of the primary (`git status --porcelain`, `git rev-parse`), `git worktree add`
  and all work inside a worktree never take it.
- **Re-entrancy:** the outermost caller takes and releases; an operation invoked with `LOCK_HELD`
  in its context takes nothing and releases nothing. `record` inside the `record` section and
  `create-task` inside `epic-update` are the two nested cases.
- **Waiting:** `take` polls every 15 seconds. Best-effort sections pass `--wait 600` and, on
  timeout, return `failed` with `CAUSE: primary lock held by <run> (<section>) since <time>`.
  The `record` sections of `ticket` and `finalize` pass `--wait 3600`; a timeout there is the
  flow's ordinary stop report (cleanup not run, worktree left), because cleanup cannot be skipped.
- **Stale locks:** `take` treats an `owner` older than 30 minutes as abandoned — no section is
  designed to hold it that long — removes it, takes the lock, and prints `stale: <old owner>`.
  The caller records `lock-stale:primary` per `notion-dev:issue-log` and names it in its report.
  Nothing else ever removes another run's lock.
- **Release on every path:** success, `failed`, and the stop path all release before the run
  ends. A run's report names any wait it did: `waited 3m for STO-71 (record)`.

## §5 Script surface — `knowledge.py next` and `knowledge.py lock`

Both stdlib-only, no YAML parsing, exit 0/1/2 like the existing subcommands.

**`knowledge.py next --brief <path> --state <json> [--reason <word> <key>] [--today YYYY-MM-DD]`**

Input JSON:

```json
{
  "epic": { "key": "STO-60", "status_class": "open" },
  "children": [
    { "key": "STO-71", "id": 71, "title": "Cache metrics", "status_class": "open",
      "blocked_by": ["STO-70"], "phase": 2, "step": 1 },
    { "key": "STO-72", "id": 72, "title": "Backfill v2", "status_class": "in_progress",
      "blocked_by": [], "phase": 2, "step": 2 }
  ],
  "thread_blocked": ["STO-22", "STO-23"],
  "stop": { "key": "STO-70", "phase": "Phase 7", "cause": "review loop stalled",
            "worktree": "../btc-worktrees/btc-STO-70" }
}
```

`status_class` is one of `resolved | in_progress | open`, computed by the skill from
`statusMap`. The script:

1. Parses the existing `## Next` region and header from `--brief` (item 1's key and reason, the
   `In progress:` `since` dates, `Blocked:`).
2. Partitions the unresolved children: `in_progress` → `In progress:`; keys in `thread_blocked`
   (and a `stop` key) → `Blocked:`; the rest → numbered, ordered by phase, then step, then
   numeric id; item 1 is the first numbered child whose `blocked_by` are all resolved
   (`status_class: resolved` or absent from `children`). Later items carry
   `— after <keys>` for unresolved dependencies. Item 1's reason: the existing reason when the
   key is unchanged; else `unblocked; <dep> landed` when a dependency resolved since the
   existing brief, else `first in phase order`.
3. Prints, to stdout, the new brief in full — the region and header replaced, every other byte
   preserved, LF endings — and, to stderr, one line per drift finding and `DRIFT: n`. Exit 0 when
   the output equals the input (no drift), 1 when it differs, 2 on a malformed brief or JSON.
   With `--reason stop`, the §1 bullet is added under `## Open threads`; with `--reason start`,
   the bullet for that key is removed. `epic.status_class: resolved` renders `epic complete` and
   `Status: closed`.

`read` calls it with the retrieved brief written to a temp file and reads only the stderr
findings; `refresh`, `record` and `note` write its stdout over the brief.

**`knowledge.py lock take | release | status`** — §4. The stale threshold and poll interval
are constants in the script, not config.

## §6 Call sites (PR 1)

- **`/notion-dev:ticket` Phase 2** — after `updateStatus(id, "inProgress")`, from `$REPO_ROOT`,
  section `start`: `refresh(<epic-id>, start <key>)`. Runs only when the ticket has an epic
  (`metadata.parentTaskProperty` non-empty). Its output joins the final report as
  `EPIC_DOC_START`. The worktree is created first (2.1), the status second, the refresh third,
  so the claim precedes every mirror of it.
- **`/notion-dev:ticket` failure-and-stop path** — before the stop report, section `stop`:
  `refresh(<epic-id>, stop <key> <phase> <cause> <worktree-path>)`. Runs from `$REPO_ROOT`
  after confirming the primary is clean outside the exempt paths; when it is not, skip with the
  reason in the stop report (the primary is dirty — the report already diagnoses that). The stop
  report prints the `EPIC-DOC:` block.
- **`/notion-dev:ticket` Phase 8.2 → Phase 10** — one section `record` around `epic-update`,
  cleanup, hooks and `record`; `record` and the `notion-dev:knowledge` hook receive `LOCK_HELD`.
- **`/notion-dev:finalize`** — the same `record` section around Phases 3–5.
- **`/notion-dev:next-task` step 1** — on `DRIFT: true`: section `drift`, `refresh(<epic-id>,
  drift)`, then **splice**: replace the root document of the held `KNOWLEDGE_CONTEXT` with the
  refreshed brief and re-parse, no second `retrieve`. `EPIC-DOC: failed` → stop with its
  `CAUSE:` (§7). The bootstrap path is unchanged except that it now runs inside the write path.
- **`/notion-dev:create-task`** — after the page is created with a `parentTaskProperty`
  relation, section `create`: `refresh(<epic-id>, create <key>)`. Skipped, with the reason
  stated, when: invoked with `LOCK_HELD` (it is `epic-update` filing follow-ups; the enclosing
  `record` recomputes `## Next` moments later), the epic has no brief on `origin/<epicBranch>`
  (bootstrap will list it), or the primary is dirty outside the exempt paths. `create-task`
  gains the same `REPO_ROOT` recipe as `ticket` for this one step.
- **`/notion-dev:new-info`** — one section `apply` around its apply phase; `note --apply` and
  `capture --fact` receive `LOCK_HELD`.
- **`/notion-dev:knowledge`** — section `capture` or `migrate` around the command.
- **`epic-doc` `record` step 2, `note` test 4** — reworded to invoke the §2 derivation.

## §7 Parallel picking, claim liveness (PR 2)

- **The claim is the worktree.** `git worktree add <path> origin/<base> -b ticket/<KEY>-<id>-<slug>`
  fails when the branch exists on this machine, so the second session to try loses. No further
  claim file. Notion `In Progress` (Phase 2) and the brief's `In progress:` line (`refresh start`)
  are the mirrors, written immediately after.
- **Run marker:** `$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json`:

  ```json
  { "run": "STO-70", "worktree": "/abs/path", "branch": "ticket/STO-70-backfill",
    "phase": "Phase 7", "heartbeat": "2026-09-15T10:42:00Z", "state": "running",
    "cause": null }
  ```

  Written at the claim; `phase` and `heartbeat` rewritten at every phase boundary and every
  review round; `state: stopped` with `cause` on the failure path; deleted in Phase 9 step 1
  right after the worktree is removed. A JSON file the flow writes directly; no script.
- **`/notion-dev:ticket` Phase 1.1 ownership check**, new, after the epic guard: live status
  equals `statusMap.inProgress` and no worktree of ours at the computed path → abort
  `[<key>] is In Progress and has no worktree here — held elsewhere`. Interactive mode may
  proceed on explicit confirmation; non-interactive mode never does.
- **`/notion-dev:ticket` Phase 1.2 resume rules**, replacing "worktree exists → resume":
  - marker `running` and heartbeat younger than 2 hours → `held by a live session — <phase>
    since <heartbeat>`; abort. Interactive mode offers take-over (which rewrites the marker
    with this run's id); non-interactive never takes over.
  - marker `stopped`, heartbeat older than 2 hours, or no marker → resume as today.
- **`claimed-elsewhere`:** when 2.1's `git worktree add` fails because the branch exists and
  1.2 found no worktree (the race window between 1.2 and 2.1), the run ends with the outcome
  `claimed-elsewhere` before any status change, ledger line or brief write. A stop report of
  one line; nothing to clean.
- **`/notion-dev:next-task`:** a delegated run that returned `claimed-elsewhere` is neither a
  stop nor a resolution — the loop records the decision, does not increment `DONE`, and picks
  the next valid candidate from the same `NEXT` (no re-read needed; the brief did not change).
  Validity rules gain the marker: an in-progress child with a `running` marker is never a
  resume candidate; one with `stopped` or no marker still is. The "resume first" rule reads the
  marker, not just the worktree. A drift `refresh` that returned `failed` stops the loop with
  its `CAUSE:` — selection from a brief that could not be repaired is guessing, the same rule
  the bootstrap path already applies.
- **Two loops on one epic** interleave with no further rule: each re-reads the brief after its
  own resolution, item 1 excludes everything in progress, and the claim settles a tie.

## §8 Merging in parallel (PR 2)

- **`review-and-merge` step 5, before the merge command:** read `mergeStateStatus`. `BEHIND` or
  `DIRTY` → in the worktree: `git fetch origin <base>`, `git rebase origin/<base>`, re-run the
  project's verify, `git push --force-with-lease`, re-read `mergeStateStatus`, then merge. A
  clean rebase changes no diff and triggers no new review round; the report states the rebase
  and the new head sha. Done once, at the gate, never per review round.
- **The version-bump conflict resolves itself.** When the rebase's only conflicting hunk is
  `version` in `.claude-plugin/plugin.json`: take the base's value, re-apply this PR's bump class
  (the class Phase 6.1 recorded — patch, minor or major), continue the rebase, and re-run the
  Phase 6.1 rule "strictly greater than base". Two minor PRs against 0.24.0 land as 0.25.0 and
  0.26.0. Any other conflict → the existing `PR unmergeable` stop with worktree and PR left; no
  automatic resolution of code.
- **No manifest** (a client repo) → the rebase and nothing else.
- **Notion contention is under the lock** (§4): `epic-update`'s read-modify-write of the epic
  page's `## Tasks` and `## Resolution Log` runs inside the `record` section. Per-ticket writes
  touch distinct pages and need nothing.
- **Local append-only files need nothing:** `ledger.jsonl` and `notion-dev-issues.md` are
  single-line appends; follow-up packets are named per ticket.
- **Out of scope:** merge queues, cross-machine claims, any change to squash-merge semantics.

## §9 Signatures

| signature | severity | source | when |
|---|---|---|---|
| `partial:epic-doc` | degraded | `ticket.md`, `finalize.md`, `next-task.md`, `create-task.md` | now also a `refresh` that returned `failed` |
| `lock-stale:primary` | unexpected | any locked section | `lock take` broke an abandoned lock; the report names the old owner |
| `lock-timeout:primary` | degraded | any best-effort section | `lock take` timed out; the section was skipped |
| `claimed-elsewhere` | info | `ticket.md` (PR 2) | the worktree claim lost a race; nothing written |

## §10 Verification

**`scripts/verify-knowledge-py.sh`** (PR 1):

- `next` fixtures under `scripts/fixtures/knowledge/next/`: partition coverage (a child in no
  list is placed), ordering by phase/step/id, item-1 reason preservation and both templates,
  the `In progress:` line with preserved `since` dates, `Blocked:` from threads, `stop` adds
  and `start` removes the bullet, `epic complete`, a brief without the line (drift = 1), and
  **re-render byte-identical** (`next` on its own output exits 0 with `DRIFT: 0`).
- `lock` cases: take, second take by another run exits 1 with the holder, same run re-enters,
  release by the wrong run exits 1, a 31-minute-old owner is broken with `stale:` printed.
- **Two-clone convergence:** a bare origin, clones A and B, both cut the same brief; A commits
  and pushes; B's push is rejected; B runs the §3 recipe (`rev-list` assertion, fetch, reset,
  re-derive with `next`, commit, push) and origin ends with both changes and B's `ATTEMPTS: 2`.
  Proves the git recipe the skill states, with the script as the deriver.

**Prose harnesses** (PR 1): `verify-epic-doc.sh` anchors `refresh`, the four reasons, the
write path's five steps, the `rev-list` assertion, three attempts, `LOCK_HELD`; `verify-knowledge.sh`
anchors `capture` through the write path; `verify-ticket-system.sh` untouched. A new
`verify-primary-lock.sh` asserts every §4 section has a `lock take` and a `lock release` in
each command file, `--wait 600` on best-effort sections and `--wait 3600` on the two `record`
sections, and that `read` contains no `lock take`. Mutation proof for every new assertion:
break the file, confirm `FAIL`, restore, commit before mutating.

**PR 2:** anchors for the marker writes at every phase boundary, the ownership check, the
resume rules' three outcomes, `claimed-elsewhere` in `ticket.md` and its handling in
`next-task.md`, the rebase step and the version-conflict rule in `review-and-merge`; a `next`
fixture where two candidates tie on phase and step and the lower id wins.

**Regression proof on real data:** capture the live children of one client epic (STO-67 or
STO-306) as a redacted JSON fixture, run `next` against a scratch copy of that client's bundle,
and hand-check the partition. Every 0.24.0 fixture reruns unchanged.

## §11 Release and order of operations

1. **PR 1 — `notion-dev` 0.25.0**: §1–§6, §9 (first three rows), §10 PR 1. README: the
   `In progress:` line and the lock directory. Client action: update the plugin; nothing else.
   Verify on a client: run one ticket and confirm three brief commits (`start`, `after`, and a
   `refresh` or `unchanged` on the next `next-task`), then stop a run on purpose and confirm the
   stop bullet appears and disappears on resume.
2. **PR 2 — `notion-dev` 0.26.0**: §7, §8, §9 last row, §10 PR 2. README: running two sessions.
   Verify on a client: two sessions, `/notion-dev:next-task <epic> --depth 2` in each, and confirm
   distinct picks, no `failed` brief writes, and both PRs merged with distinct versions.
3. Both PRs follow this repo's rules: one PR per session, version bumped once, `review-and-merge`
   with the completion pass as the pre-merge check, `session-closeout` before reporting.
