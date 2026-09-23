Read `format.md`, `write-path.md` and `output.md` before writing. Load `bootstrap.md` only if the brief is missing. Cross-references to other operations name sibling files here.

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
