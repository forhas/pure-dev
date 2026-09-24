Read `common.md` once per invocation. Other operations are not prerequisites.

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

`<baseRefName>` is the hook contract's name for `<epicBranch>` (see **Branch** above), and
`<merge-sha>` is its `<merge-commit>`; the lines are quoted in `/notion-dev:ticket`'s form so
the two cannot drift apart silently. **Line 2 belongs to the hook form only.** The direct
`capture --fact <fact> <epic-id>` call `/notion-dev:new-info` makes has no merge commit, so it
asserts lines 1, 3 and 4 and nothing stands in for the second — there is nothing to assert.

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

**Accepted-delta fast path (lean record caller):** when supplied the final accepted review's
`recording.technical_delta`, claim corrections and release obligations, these are the candidate
facts. Start from that delta, the merge SHA, the concept index and `knowledge.py touched` results.
Run Filter/Verify/Collide below; retrieve affected symbols/concepts to answer specific doubts.
Do not load the full ticket, plan, PR comments and review history merely to synthesize the same
facts again. All touched concepts still receive a validity check, including deletion/supersession;
an empty accepted delta does not waive that check. Missing evidence uses the complete fallback
below. This is targeted validation, not permission to trust unsupported author claims.

**Fallback inputs come from the session, never from Notion:** the ticket body, `KNOWLEDGE_CONTEXT`, the
review report and `PLAN_REVIEW` when present, `gh pr view <n> --json body,comments` plus the
review threads, and `git show <merge-sha>`. For `--fact`, the inputs are the fact text and that
epic's `KNOWLEDGE_CONTEXT`, nothing else. The hand re-run is the one exception, and only because
there is no session to read: it takes the ticket body from `fetchTicket(<ticket-id>)` and the pull
request from `gh pr view <n> --json body,comments`, then follows the same six steps.

**1. Filter.** For each candidate fact, one question: *would an engineer reading the merged code
still not know this?* Keep rejected approaches and why, traps that cost time, decisions and what
they rule out, constraints that must hold. Drop what the code says, the diff, the ticket text,
status, and style. **An empty capture is a correct outcome**: append one dated
`- <date> [<KEY>-<n>]: nothing durable (<merge-sha>)` line to `log.md` and return
`KNOWLEDGE: empty` — unless `log.md` already carries that `[<KEY>-<n>]` + `<merge-sha>` line
(a re-run of an already-landed capture, where every candidate reads `untouched`): then append
nothing and return the same `empty` block with `COMMIT: none`, so recovery runs stay idempotent.

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
working tree with `git checkout -- <knowledge.dir>` **and** `git clean -fd -- <knowledge.dir>`,
then fail as the paragraph below describes, carrying the check's first finding line as the cause.
Both halves are needed: a concept this capture **created** is untracked, `git checkout --` does
not remove it, and a survivor breaks precondition 4 on every later capture — one failed capture
would disable the hook until someone cleaned the tree by hand. A check that cannot run and says
nothing is the outcome both clients learned to fear.

Otherwise stage and commit by pathspec — never the whole index, since a caller's precondition
permits an exempt setup file to sit staged:

```
git add -- <knowledge.dir>
git commit --only -m "docs(knowledge): capture <KEY>-<n>" -- <knowledge.dir>
git commit --only -m "docs(knowledge): note <KEY>-<n> — <short fact>" -- <knowledge.dir>   # --fact form
```

This block **is** step 3 ("Derive and commit") of `notion-dev:epic-doc`'s five steps, reached
through `## The write path`, with the two subjects above and the pathspec `-- <knowledge.dir>`;
Load `skills/epic-doc/references/write-path.md` for
steps 1 (lock), 2 (establish the base), 4 (push, converge on rejection, never `--force`) and 5
(unlock) run around it exactly as the write path states them. `capture` re-derives on a rejected
push exactly as `refresh` does, and under `--branch` there is no push. The caller's `LOCK_HELD` is
passed through.

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
