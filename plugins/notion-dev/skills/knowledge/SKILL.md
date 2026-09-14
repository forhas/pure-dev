---
name: knowledge
description: Use when a run needs the repo's knowledge bundle — `retrieve` assembles one budgeted context block from the epic's root concept, `capture` writes what a merge or a new fact taught, `curate` resolves near-duplicate concepts, and `migrate` moves a client's existing bundle onto this schema; besides `scripts/knowledge.py` this skill is the only part of the plugin that invokes `iwe`.
---

# knowledge

One OKF v0.2 bundle per repo, owned by this skill: one fact per file, the epic brief as the
bundle's root concept, and exactly one read path into a run. Every operation is **best-effort**
in the `epic-update` sense — a failure never fails the caller's run, never blocks a merge or a
resolution, and is always stated in the caller's final report.

```
<knowledge.dir>/                       # default `knowledge`
  .iwe/config.toml                     # plugin-owned; migrate/init install, check compares
  .iwe/schemas/okf.yaml, okf-index.yaml, okf-log.yaml
  index.md                             # hand-curated catalog: one bullet per concept, by type
  log.md                               # append-only, dated
  epic/<KEY>-<n>-<slug>.md             # the brief — the epic's root concept
  ticket/ decision/ gotcha/ component/ spec/ domain/ release/     # canonical types
  <extra>/                             # client extension dirs, declared in knowledge.extraTypes
```

**Config.** The `knowledge` block of `.claude/notion-dev.config.json`:

- `dir` — the bundle root, default `knowledge`, carrying the path pattern `epicDocs.dir` had
  (relative, forward slashes, no `..`).
- `retrieveBudget` — the read-time token budget, integer ≥ 1000, default 8000.
- `warnBytes` — the per-concept size above which `check` warns; it never fails, default 8192.
- `extraTypes` — client type directories `check` accepts beyond the canonical set, for example
  `["commitment", "node"]`. Dot-directories (`.mirror/`, `.record/`, `.okf/`) are ignored entirely.

**Branch.** The bundle lives on the branch pull requests merge into — `git.prTargetBranch`,
falling back to `git.baseBranch` — called `<epicBranch>` below, the one name `epic-doc` gives it.
Every read, every commit and every push here uses that one branch. `<baseRefName>`, in the hook
lines `capture` quotes from `/notion-dev:ticket`, is the same branch: `epic-doc record` fails the
run when a PR merged anywhere else.

**Read once.** Each fact enters a run exactly once. The bundle arrives as `KNOWLEDGE_CONTEXT`
from one `retrieve` before any worktree exists, and nothing downstream reads it again: no second
search, no catalog read, no recursive grep over the tree, and never the Notion epic page for what
the brief already holds. The table under `retrieve` is that rule in full, and it is the reason a
caller that already holds `KNOWLEDGE_CONTEXT` passes it in instead of triggering a second fetch.

**Dependencies.** `iwe` ≥ 0.19 on `PATH`, probed at each command's preconditions with
`iwe --version`. Missing or older → the precondition message names both install routes:
`cargo install iwe --root ~/.local` (works wherever Rust does; required on hosts whose GLIBC is
older than 2.39, which includes Ubuntu 22.04 under WSL), and `brew install iwe` /
`npm i -g @iwe-org/iwe` where the prebuilt binary runs. The signature is
`missing-dependency:iwe`. Nothing here depends on the LSP (`iwes`) or the MCP server (`iwec`).
`python3` on `PATH` runs `${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py` — standard library only,
no `pip` step.

**This skill and `scripts/knowledge.py` are the plugin's only iwe callers.** The skill touches
`iwe retrieve`, `iwe find`, `iwe stats similarity` and `iwe rename`; the script touches
`iwe find -f json` for frontmatter and `iwe schema validate` for shape. No command, no other
skill invokes the binary, so the dependency can be swapped by editing one skill and one script.

## `retrieve(<epic-id>, <ticket-title>?, <ticket-id>?)` → `KNOWLEDGE_CONTEXT` or `null`

Read-only. It writes nothing and runs before any worktree exists.

### Read-once

| fact | read from | never from |
|---|---|---|
| requirements | the ticket body, `fetchTicket` | bundle, brief |
| children statuses | `listEpicChildren` | bundle, brief (neither stores status) |
| epic identity (key, title, url) | `fetchTicket(<epic-id>)`, properties only | the Notion epic page body |
| why / where we stand / threads / decisions / next | the brief, as the root of the retrieve | Notion epic page |
| ruled-out approaches, gotchas, constraints | the retrieve result | a recursive grep, `index.md`, a second query |
| the merge's content | `git show <merge-sha>`, `gh pr view` | Notion |

### Steps

1. `fetchTicket(<epic-id>)` via `notion-dev:ticket-system`, then the epic predicate
   (`metadata.parentTaskProperty` empty **and** `metadata.epicMarkerProperty` true — the one
   `findEpics()` and `/notion-dev:ticket`'s epic guard apply). Not an epic → return `null`.
2. `git fetch origin`, then locate the root on `origin/<epicBranch>` with
   `git ls-tree -r --name-only origin/<epicBranch> -- <knowledge.dir>/epic/` filtered to
   `<KEY>-<n>-*.md`. Missing → bootstrap **in memory** exactly as `epic-doc` "Bootstrap"
   describes, its seed search now also covering `<knowledge.dir>/epic/`; return the brief alone
   with `BOOTSTRAP: true` and `SEED: <path>` or `SEED: notion`, and skip step 3. A failing
   fetch or an `ls-tree` error — no network, no such branch — is not "missing": it takes step 5's
   degrade path, since a bundle that cannot be reached must not be reported as absent.
3. One call, run from a temporary export of the bundle at `origin/<epicBranch>` so a stale local
   checkout never answers (`git archive origin/<epicBranch> <knowledge.dir> | tar -x -C <tmp>`,
   then run from `<tmp>/<knowledge.dir>`, and remove `<tmp>` once the call returns, whether it
   succeeded or not):

   ```
   iwe retrieve -k epic/<KEY>-<n>-<slug> --expand-references 1 \
     --lexical "<ticket title>" --filter 'status: stable' --max-tokens <knowledge.retrieveBudget> -f markdown
   ```

   The root is always first and never trimmed; the lexical seed is omitted when no ticket title
   is given (`/notion-dev:next-task`, `/notion-dev:new-info`). `deprecated` and `draft` concepts
   are excluded by the filter. Reference expansion is the only expansion this plugin relies on;
   inclusion expansion is never requested, so a concept is never pulled in whole by another.
4. Return `KNOWLEDGE_CONTEXT` — the retrieve output verbatim — plus the fields `epic-doc read`
   returns, parsed from the root: `EPIC_CONTEXT`, `NEXT`, `BLOCKED`, `STATUS`, `CHILDREN` (one
   `listEpicChildren(<epic-id>)` call, since no concept stores a live status), `BOOTSTRAP` and
   `SEED`.
5. `iwe` missing or the call failing → read the root alone with
   `git show origin/<epicBranch>:<root path>` as `EPIC_CONTEXT`, return
   `KNOWLEDGE_CONTEXT: unavailable`, and record `partial:knowledge-retrieve` per
   `notion-dev:issue-log`. **The run continues** —
   a bundle that cannot be read costs context, not the ticket.

**The parse of the root.** `-f markdown` emits one fenced block per document, each opening with
a ```` ```markdown #<key> ```` line and carrying a YAML frontmatter block (`title`, `references`,
…) before the body, the seed document first:

````
```markdown #epic/STO-60-wallet-indexing
---
title: "[STO-60] Wallet Indexing"
references: [decision/offline-deploy, gotcha/cache-ttl]
---
# [STO-60] Wallet Indexing
…
```
````

`EPIC_CONTEXT` is that **first fenced document with its frontmatter stripped** — the brief as
`epic-doc` writes it, nothing more. `NEXT`, `BLOCKED` and `STATUS` are parsed out of it exactly
as `epic-doc read` step 3 parses them, which is all `epic-doc read` now is: a name for this parse
over a retrieve result. Callers treat the whole block as **background, not requirements**, exactly
as `EPIC_CONTEXT` is treated today; the ticket body remains the source of truth for what to build.

**Budget.** `retrieveBudget` bounds the bundle's share of a run's context. The root is ≤ 120 lines
by `epic-doc`'s rule; the remainder is the concepts one reference hop away plus the lexical seeds,
with the periphery trimmed first by iwe. Raising the budget is a config change, never an extra
call.

## `capture(<ticket-id>, <merge-sha>)` and `capture --fact <fact> <epic-id>`

The bundle's only writer. Invoked by the hook, by `/notion-dev:new-info` on two paths, and by
hand — one procedure behind all of them:

- **As the post-merge hook.** A client's `git.postMergeHooks` names `notion-dev:knowledge`; the
  hook contract in `/notion-dev:ticket` Phase 9 and `/notion-dev:finalize` runs this operation
  with `<ticket-id>` and `<merge-sha>`. A hook the flow skipped — a precondition it could not
  assert — or one that failed is re-run by hand, unchanged, as
  `/notion-dev:knowledge capture <ticket-id> <merge-sha>`.
- **From `/notion-dev:new-info`**, as `capture --fact <fact> <epic-id>`, once the brief note for
  that epic has been applied and committed.
- **Under `/notion-dev:new-info --pr`**, as `capture --fact <fact> <epic-id> --branch <noteBranch>`:
  HEAD's branch must be `<noteBranch>` and
  `git -C $REPO_ROOT merge-base --is-ancestor origin/<epicBranch> HEAD` must exit 0 — the branch
  was cut from the epic branch and still contains it. Those two checks stand **in place of the
  first and third lines below**, which HEAD on a note branch cannot satisfy; the second has no
  merge to assert on this path, and the fourth is unchanged. The commit is made on `<noteBranch>`
  and **nothing is pushed** — `/notion-dev:new-info` pushes once, exactly as `epic-doc`'s
  `note --apply --branch` behaves. Its Collide step (step 3 below) also runs against
  `<knowledge.dir>` in this note-branch working tree, not an export of `origin/<epicBranch>`, so
  a re-run of the same fact before the branch merges sees the earlier capture and reports
  `untouched` rather than writing a duplicate concept.

**Preconditions** — exactly the three assertions `/notion-dev:ticket` Phase 9 makes before
invoking any hook, in its form, plus a fourth that guards the bundle:

```bash
git -C $REPO_ROOT rev-parse --abbrev-ref HEAD                    # must equal <baseRefName>
git -C $REPO_ROOT merge-base --is-ancestor <merge-sha> HEAD      # must exit 0
test "$(git -C $REPO_ROOT rev-parse HEAD)" = \
     "$(git -C $REPO_ROOT rev-parse origin/<baseRefName>)"       # must be equal
git -C $REPO_ROOT status --porcelain -- <knowledge.dir>          # must be empty
```

`<baseRefName>` is the hook contract's name for `<epicBranch>` (see **Branch** above); the lines
are quoted in `/notion-dev:ticket`'s form so the two cannot drift apart silently.

Line 1 puts the write on the branch the merge landed on rather than a worktree or a leftover
ticket branch; line 2 proves the merge this capture reads is present whatever a stale
remote-tracking ref says; line 4 keeps a revert of this operation's own writes from discarding
someone's uncommitted edit. Any failure → write nothing and return `KNOWLEDGE: failed` naming the
assertion that failed.

**Line 3 is not optional here, because this operation pushes.** A primary carrying local-only
commits satisfies lines 1 and 2 — right branch, merge present — and `git push` publishes history,
not a subset, so the capture commit would carry every unreviewed local commit onto the epic branch
with it. Ordinary drift is answered by re-running the operation by hand after a successful
checkout and fast-forward pull, never by loosening the assertion; the report names the re-run
command so nobody has to reconstruct it.

**Inputs come from the session, never from Notion:** the ticket body, `KNOWLEDGE_CONTEXT`, the
review report and `PLAN_REVIEW` when present, `gh pr view <n> --json body,comments` plus the
review threads, and `git show <merge-sha>`. For `--fact`, the inputs are the fact text and that
epic's `KNOWLEDGE_CONTEXT`, nothing else. The hand re-run is the one exception, and only because
there is no session to read: it takes the ticket body from `fetchTicket(<ticket-id>)` and the pull
request from `gh pr view <n> --json body,comments`, then follows the same six steps.

**1. Filter.** For each candidate fact, one question: *would an engineer reading the merged code
still not know this?* Keep rejected approaches and why, traps that cost time, decisions and what
they rule out, constraints that must hold. Drop what the code says, the diff, the ticket text,
status, and style. **An empty capture is a correct outcome**: append one dated
`- <date> [<KEY>-<n>]: nothing durable` line to `log.md` and return `KNOWLEDGE: empty`.

**2. Verify before citing.** A specific claim — a count, an order, a location — is checked against
the file it names before it is written. `sources[]` cites the PR and the ticket by URL and any
code path by relative path; `applies_to` carries the globs a later merge should re-read this
concept against.

**3. Collide.** Dedupe against `KNOWLEDGE_CONTEXT` first, then one call per surviving candidate:

```
iwe find --lexical "<key phrase>" --filter 'status: stable' -f json
```

Exactly one outcome per candidate:

- **untouched** — an existing concept already says it; nothing is written.
- **updated** — an existing concept is refined, not contradicted: edit it in place, set
  `updated`, and append one dated line to its trailing `## Updates` section
  (`- 2026-09-14 [STO-140]: …`).
- **superseded** — an existing concept is contradicted: write the new concept, set the old one
  `status: deprecated` and `superseded_by: <new path>`, and give the old one its own dated line
  naming the ticket or the fact that retired it.
- **created** — nothing collides: a new file under its type directory, with the frontmatter the
  shipped `okf.yaml` requires.

**4. Re-read touched concepts** (hook form only):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" touched <merge-sha> --dir <knowledge.dir>
```

It lists every `stable` concept whose `applies_to` globs intersect the merge's changed paths.
Each listed concept is read against the diff and resolved with the same four outcomes. **Nothing
else in the bundle is examined** — the retrieve and this list are the whole working set.

**5. Index and log.** Every created or superseded concept gets its `index.md` bullet added,
moved, or marked; `log.md` gets one dated entry for this capture, naming the ticket or the fact.

**6. Check, commit, push.**

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" check --dir <knowledge.dir> \
  --plugin-root "${CLAUDE_PLUGIN_ROOT}" --extra-types <knowledge.extraTypes joined with commas> \
  --warn-bytes <knowledge.warnBytes>
```

`--extra-types` takes one comma-separated string, not the config's JSON array: `["commitment",
"node"]` is passed as `commitment,node`. Passing the array verbatim makes every declared type
directory read as undeclared, which fails `check` and — by the rule below — silently discards the
whole capture on every merge.

**Write nothing** when `check` exits non-zero, and never downgrade its exit 2: restore the
working tree with `git checkout -- <knowledge.dir>`, then fail as the paragraph below describes,
carrying the check's first finding line as the cause. A check that cannot run and says nothing is
the outcome both clients learned to fear.

Otherwise stage and commit by pathspec — never the whole index, since a caller's precondition
permits an exempt setup file to sit staged:

```
git add -- <knowledge.dir>
git commit --only -m "docs(knowledge): capture <KEY>-<n>" -- <knowledge.dir>
git commit --only -m "docs(knowledge): note <KEY>-<n> — <short fact>" -- <knowledge.dir>   # --fact form
```

Then push as `epic-doc record` pushes — skipped under `--branch`, where the caller pushes once. A
push git rejects leaves the local commit in place, **never forces**, and fails the same way,
carrying git's rejection message and the commit SHA so the caller's closeout can name it as
blocked.

**Either failure of this step records `partial:knowledge-capture`** per `notion-dev:issue-log` —
this skill's signature, never `epic-doc`'s — and returns `KNOWLEDGE: failed` with the cause on the
output block's `CAUSE:` line: the check's first finding, or git's rejection.

Output block:

```
KNOWLEDGE: captured | empty | failed | unavailable
CREATED: <paths> · UPDATED: <paths> · SUPERSEDED: <old → new> · UNTOUCHED: <n>
COMMIT: <sha> | none
CAUSE: <the failed assertion, the check's first finding, or git's rejection>   (only on failed)
```

## `curate`

Dedupe only, user-invoked through `/notion-dev:knowledge curate`. Nothing runs on a schedule and
nothing here reads Notion.

1. Run the check:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" check --dir <knowledge.dir> \
     --plugin-root "${CLAUDE_PLUGIN_ROOT}" \
     --extra-types <knowledge.extraTypes joined with commas> \
     --warn-bytes <knowledge.warnBytes>
   ```

   The same four flags `capture` step 6 passes, comma-joined the same way: a client with
   `extraTypes` gets a finding its bundle does not have when they are left off.
   Non-zero → stop and print the findings; a bundle that fails its own rules is not one to merge
   concepts in.
2. `iwe stats similarity -t <threshold>` directly — text output, one pair per line; the script
   wraps nothing here because the command has no structured output. `<threshold>` starts at `0.8`
   and is lowered only when the user asks for a wider net.
3. Present each cluster with both bodies side by side and let the user name the survivor, or
   `keep both`. `keep both` is a real answer: two concepts that read alike may hold two facts.
4. The loser is superseded exactly as `capture` step 3 supersedes — `status: deprecated`,
   `superseded_by`, one dated line — and its links are left pointing at a live successor.
5. Index, log, check again, then commit `docs(knowledge): curate — <n> clusters resolved` by
   pathspec and push, as `capture` step 6 does. Returns `capture`'s output block, with
   `SUPERSEDED` naming each resolved cluster.

## `migrate [--apply]`

Once per client, through `/notion-dev:knowledge migrate [--apply]`.
Without `--apply` it prints the complete diff and writes nothing.

1. **Preconditions.** The primary on `<epicBranch>`, a clean tree, `iwe` and `python3` present —
   the command's precondition block, which is where a missing binary is reported.
2. **Install the plugin-owned files.** `.iwe/config.toml` and `.iwe/schemas/` are copied from
   `${CLAUDE_PLUGIN_ROOT}/skills/knowledge/references/iwe/`, overwriting whatever the client had:
   a bundle cannot silently loosen the schema it is checked against.
3. **Rewrite every concept** under `<knowledge.dir>` outside dot-directories: map the `current`
   status — one client's local vocabulary — to `stable`; drop `stale_after`, `reconciled`,
   `verified` and `vouch`; add `sources` when missing, from a ticket or PR reference in the body,
   else `{ id: migrated, resource: <own path> }` with `status: draft`; collect any
   `## Reconciliation notes` under `## Updates`. Every other field and all prose are left alone.
   Reshape `log.md` to the shipped `okf-log.yaml` form (one title section, `## YYYY-MM-DD` groups
   newest first, bullets only) and `index.md` to `okf-index.yaml` (sections of link bullets only)
   — both clients' logs fail that schema today.
4. **Move the brief.** `docs/epics/<KEY>-<n>-<slug>.md`, or whatever `epicDocs.dir` named, moves
   to `<knowledge.dir>/epic/` with the `type: Epic` frontmatter added. A hand-written seed plan
   is left where it is, for `next-task`'s bootstrap, which now writes into `epic/`.
5. **Rewrite the links the moves broke** — `iwe rename` per moved file, so no relative link is
   repaired by hand.
6. **Config.** Drop `epicDocs` from `.claude/notion-dev.config.json`, add the `knowledge` block
   with `extraTypes` set to the non-canonical directories found, and replace the client's own
   `postMergeHooks` entry with `notion-dev:knowledge`.
7. **Check the result:**

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" check --dir <knowledge.dir> \
     --plugin-root "${CLAUDE_PLUGIN_ROOT}" \
     --extra-types <the extraTypes step 6 wrote, joined with commas> \
     --warn-bytes <knowledge.warnBytes>
   ```

   Non-zero under `--apply` → revert everything this operation wrote, restoring the bundle to the
   state it started from, and report the findings. The migration is all-or-nothing.
8. **Print the removal checklist** for this client, derived from what step 3 found: the skill
   directory the old hook entry named, every script under `scripts/knowledge/`, every workflow and
   Makefile target that invokes one, and the CLAUDE.md lines that route to them. This operation
   **never deletes client code** — the client's own migration PR does, pasting this checklist into
   its body with each line ticked and, for every retired check, the `check` rule that covers it
   now.

The invocation is one call:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" migrate [--apply] --dir <knowledge.dir> \
  --config .claude/notion-dev.config.json --plugin-root "${CLAUDE_PLUGIN_ROOT}"
```

Steps 4 and 8 are this skill's work over what the script reports; steps 2, 3, 5, 6 and 7 are the
script's. Returns `capture`'s output block with `COMMIT: none` — `migrate` stages nothing and
commits nothing; the client's migration PR carries the diff.

## Failure handling

Every operation is best-effort against the ticket flow, and the two directions are not symmetric:
**fail closed on checks, degrade on reads.** A check that fails or cannot run means nothing is
written. A read that fails serves the brief alone and lets the run continue — the ticket body,
not the bundle, is what the work is built from.

Signatures, recorded through `notion-dev:issue-log` at the moment they happen; failing to write
the log never fails the run:

- `partial:knowledge-retrieve` — `iwe` missing or `retrieve` failed; the brief was served alone.
- `partial:knowledge-capture` — `check` failed or the push was rejected; nothing was written, or
  a commit is unpushed.
- `missing-dependency:iwe` — `iwe` absent or below 0.19, at the preconditions of
  `/notion-dev:ticket`, `/notion-dev:next-task`, `/notion-dev:new-info` and
  `/notion-dev:knowledge`.
