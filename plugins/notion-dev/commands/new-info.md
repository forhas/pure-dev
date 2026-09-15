---
description: Route one new fact to every epic brief it affects — judge relevance per brief, apply the change through epic-doc's `note` behind a per-epic gate, commit to the epic branch, note the Notion epic, comment on the tickets it unblocked.
argument-hint: "<information> [--epic <id>]… [--non-interactive] [--pr]"
disable-model-invocation: true
---

# /notion-dev:new-info

Takes one fact — "the customer deployed v1.4.2 on 2026-09-14" — reads every epic brief (`notion-dev:epic-doc`), decides per epic whether and how the fact changes it, applies exactly that change, commits it to the epic branch, tells the Notion epic and the tickets the fact unblocked, and reports what it did and what it skipped. A fact is something a person knows; nothing in the plugin has one to route, which is why this command is user-invoked only.

Args: `<information> [--epic <id>]… [--non-interactive] [--pr]`

Flag parsing:
- `--epic <id>` (repeatable, or `--epic=<id>`): remove each and record `EPICS`. Each accepts every form `/notion-dev:ticket` accepts for a ticket id: the Notion page id, a dashed UUID, the page URL, or the logical key (`STO-60`).
- `--non-interactive`: never pause; apply every `affected` proposal and comment on every `AC-IMPACT` ticket, logging each decision for the report.
- `--pr`: land through one pull request instead of direct commits (see `## \`--pr\`` below).
- Whatever remains is `<information>`, the fact, verbatim; empty → fail with usage. Derive `<short fact>`: the fact truncated to 60 characters at a word boundary — it names the commit subjects, the PR title, and the Notion entries.

**Standing rule — runtime issues.** Anything unexpected at runtime is recorded via `notion-dev:issue-log` at the moment it happens; that skill is authoritative for what counts. A failure to write the log never fails the run.

## Preconditions

- Record `REPO_ROOT` **first**: the first path listed by `git worktree list` — the primary checkout, never a worktree.
- `.claude/notion-dev.config.json` exists in `$REPO_ROOT`; load it. Missing → abort and tell the user to run `/notion-dev:init`. `dependencies.superpowers` and `dependencies.featureDev` are **not** required on the direct-commit path — this command builds nothing. Under `--pr`, `dependencies.superpowers` must be `true` (abort with the re-run-`/notion-dev:init` guidance otherwise): `notion-dev:review-and-merge` handles review feedback through `superpowers:receiving-code-review`, and a pull request opened without it cannot be driven to merge.
- `gh auth status` and `jq --version` succeed — the `--pr` path and the closeout need both; abort with the same install guidance `/notion-dev:ticket`'s precondition block gives.
- Probe `iwe --version` (≥ 0.19) and `python3 --version` — the Apply step's `capture --fact` call needs both. Missing or older `iwe` records `missing-dependency:iwe` per `notion-dev:issue-log` and names the same two install routes `notion-dev:knowledge` documents (`cargo install iwe --root ~/.local`, or `brew install iwe` / `npm i -g @iwe-org/iwe` where the prebuilt binary runs — the GLIBC 2.39 note applies to those). This does **not** abort the run: routing the fact to every affected brief is still worth doing even when the bundle write degrades, exactly as `capture` itself degrades rather than blocking.
- The repo has an `origin` remote.
- The working tree is clean, OR the only dirt is exempt — the clean-tree rule of `/notion-dev:ticket`'s precondition block applied verbatim: exactly two exempt dirt kinds (the init-generated `.claude/notion-dev.config.json` and `.mcp.json`, and the harness-managed `.claude/settings.local.json`), the offending paths reported from `git status --porcelain`, and `git stash -u` named when the dirt is untracked. **Under `--pr` the exemption does not apply**: the run switches the primary onto `<noteBranch>` with that dirt in place, and `notion-dev:review-and-merge` then refuses any non-empty `git status --porcelain` (its fix commits use `git add -A`), stranding the pull request before review — so a `--pr` run requires a completely clean tree, and reports a modified exempt file with the same commit-or-stash remedy.
- `<epicBranch>` = `git.prTargetBranch`, falling back to `git.baseBranch` — the branch the brief lives on, per `notion-dev:epic-doc`. Then `git -C $REPO_ROOT checkout <epicBranch> && git -C $REPO_ROOT pull --ff-only origin <epicBranch>`. A `--ff-only` failure stops the run with the same diverged-base report `/notion-dev:ticket` Phase 9 step 4 gives — never stash or discard.

**Epic guard.** Every id in `EPICS` goes through `fetchTicket` via `notion-dev:ticket-system` and the epic predicate: `metadata.parentTaskProperty` empty **and** `metadata.epicMarkerProperty` true. A page that fails it → stop before touching anything: `[<KEY>-<n>] <title> is not an epic container` — a mistyped id must not silently narrow the scope.

## Scope

With `EPICS` given, the scope is exactly those epics. Otherwise:

1. **Briefs on disk.** `git fetch origin`, then `git ls-tree -r --name-only origin/<epicBranch> -- <knowledge.dir>/epic/` filtered to `<KEY>-<n>-*.md`; each file yields an epic key. This list is authoritative for what enters the scope, not for what survives it: a brief whose epic Notion no longer returns — deleted or re-parented — is still listed here, then skipped at the Read step below with reason `not an epic`, and the report names it so a person can retire or re-parent the file.
2. **Open epics without a brief.** `findEpics()` via `notion-dev:ticket-system`. It returns no status, so for each hit whose key has no brief from step 1, `fetchTicket` it and keep it when its status is not in the resolved set (`statusMap.implemented` / `done` / `cancelled`). When the call returns `null` — the marker or parent slot is unusable on the live DB, and the operation records its own signature — step 2 contributes nothing; say so in the report and continue with step 1's list alone.

Order by numeric epic id. Every epic in scope appears in the report exactly once.

## Per epic

### Read

Invoke the `notion-dev:knowledge` skill, operation `retrieve(<epic-id>)`. It returns `KNOWLEDGE_CONTEXT`, `EPIC_CONTEXT`, `NEXT`, `BLOCKED`, `STATUS`, `CHILDREN`, `BOOTSTRAP`, and `SEED`. `null` (not an epic) → skip with reason `not an epic`. Then fetch the live status (`fetchTicket(<epic-id>).status`) **whatever the header says**, and let it decide: in the resolved set → skip with reason `epic closed` even when the header still reads `open` — a fact that reopens an epic is a Notion status change, not this command's call; not in the resolved set → treat the brief as open even when the header reads `closed`, since the header is stale (the rule `/notion-dev:next-task` applies). `BOOTSTRAP: true` → the in-memory brief is judged below exactly like a committed one; only an affected epic reaches disk.

### Propose

Invoke the `notion-dev:epic-doc` skill, operation `note(<fact>, <epic-id>)`, passing `EPIC_CONTEXT`, `CHILDREN`, and `<short fact>`. It writes nothing and returns the proposal block: `NOTE: affected | unaffected`, `REASON`, `CLEARED`, `ADDED`, `REPLACED`, `NEXT`, `AC-IMPACT`, `DIFF`.

`unaffected` → skip; the report names the epic with its `REASON`. No gate, no write.

### Gate

`affected`, interactive: print the proposal block and `AskUserQuestion` — **Apply** (default), **Skip**, **Revise**. Revise takes the user's text as guidance: re-run the propose step with it and gate again, at most three times, then Apply / Skip only. When `AC-IMPACT` is non-empty, one more question per listed ticket: **Comment** (default) / **Nothing** — this command never edits a ticket body, so editing is never offered.

`affected`, non-interactive: Apply, and Comment on every `AC-IMPACT` ticket; both logged as decisions for the report.

### Apply

**The `apply` section begins here.** Once per run, before the first epic's apply: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section apply --wait 600` (`<run id>` is `new-info`; exit 1 → report every epic as `skipped — primary lock held by <run> (<section>) since <time>`, record `lock-timeout:primary`, and go to the report). Every `record --bootstrap`, `note --apply` and `capture --fact` below receives `LOCK_HELD`.

**`BOOTSTRAP: true` first.** Invoke the `notion-dev:epic-doc` skill, operation `record --bootstrap <epic-id>`, passing `REPO_ROOT` and `<epicBranch>` as `<baseRefName>` — exactly as `/notion-dev:next-task` does: it writes the distilled brief, removes the seed plan when there was one, commits the bootstrap, and pushes (under `--pr`, with `--branch <noteBranch>`: commits without pushing). `EPIC-DOC: failed` → this epic fails with that `CAUSE:`; when the cause is a rejected push, the bootstrap commit is the unpushed commit and the loop stops exactly as the third bullet below describes for a note commit — the closeout line names the bootstrap commit's SHA; any other cause continues with the next epic. Otherwise re-derive the proposal against the bootstrapped brief: on the direct path re-run the Read and Propose steps above. Under `--pr` do **not** invoke `read` — the bootstrap commit is local to `<noteBranch>`, while `read` always resolves the brief on `origin/<epicBranch>`, where it is not yet present — so take `EPIC_CONTEXT` from `git show HEAD:<brief path>` (`<brief path>` is the `PATH:` of the bootstrap's `EPIC-DOC:` block), keep the `CHILDREN` already in hand, and re-run the Propose step alone. Either way, re-enter `### Gate` only when the new `DIFF` differs from the accepted one.

Then invoke the `notion-dev:epic-doc` skill, operation `note --apply <epic-id>`, passing the accepted proposal, `<short fact>` (the commit subject carries it), `REPO_ROOT`, `<epicBranch>` as `<baseRefName>`, `LOCK_HELD`, and under `--pr` `--branch <noteBranch>`. Record its `EPIC-DOC:` block as this epic's `EPIC_DOC_REPORT`. Three outcomes:

- `updated` or `closed` with `COMMIT: <sha>` → continue to the Notion epic and Tickets steps.
- `updated` with `COMMIT: none` — the brief was already byte-identical, nothing was committed; `THREADS: +0 -0` alone is not the signal, since a constraint-only commit also touches no thread — **skip the Notion epic and Tickets steps for this epic**: a re-run must not append a second Notion note or a second comment.
- `failed` → record `partial:new-info` per `notion-dev:issue-log` (once per run) and report the `CAUSE:`. When the cause is a rejected push, **stop the loop**: HEAD now differs from `origin/<epicBranch>`, so every later epic would fail the same precondition; report each remaining epic as `skipped — earlier push rejected`. **This epic's Notion epic and Tickets steps still run** — the block carries `COMMIT: <sha>`, the commit exists and the `blocked:` line below tracks its push; skipping them would lose them for good, because a re-run after the manual push meets `COMMIT: none` and skips them by design. This command then writes the unpushed commit's `blocked:` line into the report's closeout block itself (see `## Report`) — the workspace pass enumerates the workspace, not unpushed work. A `failed` whose cause is *not* a rejected push — a precondition assertion, a bootstrap failure — skips only this epic; the loop continues with the next.

Then, unless this epic's `note --apply` outcome above was `failed`, invoke the `notion-dev:knowledge` skill, operation `capture --fact <fact> <epic-id>`, passing `KNOWLEDGE_CONTEXT`, `REPO_ROOT`, `<epicBranch>`, and `LOCK_HELD` (under `--pr`, `--branch <noteBranch>`). Record its `KNOWLEDGE:` line for this epic's report. `failed` records `partial:knowledge-capture`; capture pushes on this path exactly as `note --apply` does (`knowledge/SKILL.md` capture step 6), so a `failed` whose `CAUSE:` is a rejected push obeys **the same rejected-push rule as the bullet above**: stop the loop, report each remaining epic as `skipped — earlier push rejected`, and this epic's own remaining side effects still run — the closeout writes the `blocked:` line for the unpushed commit exactly as it does for a note or bootstrap commit (see `## Report`). Any other `failed` cause — a precondition assertion, `check` failing — does not stop the loop; the next epic in scope still runs regardless. This runs for both the `COMMIT: <sha>` and `COMMIT: none` cases above: the fact may still be worth capturing into the bundle even when the brief itself did not change.

**The `apply` section ends here:** after the last epic — on every path, including a rejected push that stopped the loop — `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`.

### Notion epic

`appendToSection(EPIC_ID, "Notes", <entry>)` via `notion-dev:ticket-system` — a `divider` block, then:

```
### <YYYY-MM-DD HH:MM UTC> — new info
**Fact:** <the fact, verbatim>
**Brief:** <brief path> — <THREADS> · next: <NEXT>
**Cleared:** <thread> (unblocks STO-22, STO-23)
**Changed:** <ADDED and REPLACED lines>
```

`EPIC_ID` is the epic's page id from the `fetchTicket` that resolved this epic — scope step 2's, or the epic guard's — or its logical key; `appendToSection` accepts either. `Cleared` and `Changed` are omitted when empty. Timestamp from `date -u +"%Y-%m-%d %H:%M UTC"`. Best-effort, like every `epic-update` write: a failure is a warning, the run continues, the epic's report line reads `notion: failed`, and `partial:new-info` is recorded — **and the report prints the entry verbatim under that line, with the `appendToSection` call that failed**, because there is no retry path inside the command: a re-run of the same fact reads the already-updated brief, returns `unaffected`, and never reaches this step, so the printed entry is the only way the note still lands. `## Resolution Log` is never written here — it holds resolutions only.

### Tickets

For each key in the apply block's `UNBLOCKED`, and for each `AC-IMPACT` ticket the gate accepted, `postComment(<id>, <text>)` via `notion-dev:ticket-system` — one comment per ticket even when both apply, `<text>` being the paragraph(s) that apply:

> New information (<date>): <fact>. The thread "<thread text>" in <brief path> is cleared, so this ticket is no longer waiting on it. — /notion-dev:new-info

> New information (<date>): <fact>. This may change "<the requirement or criterion>" — re-check it before the ticket starts; the plugin never edits a ticket body. — /notion-dev:new-info

Best-effort; a failed comment is named in the report and records `partial:new-info`. No ticket section is ever replaced or rewritten from here.

## `--pr`

Same scope, proposal, and gate; only the landing differs:

1. After the preconditions, `git -C $REPO_ROOT checkout -b <noteBranch> origin/<epicBranch>`, where `<noteBranch>` = `notes/new-info-<YYYYMMDD>-<slug>` and `<slug>` is `<short fact>` kebab-cased exactly as `/notion-dev:ticket` Phase 2.1 slugs a branch. Record `<startSha>` = `git rev-parse origin/<epicBranch>` at this moment — the state the run started from, needed in step 5 after the branch is gone. No worktree: the primary is clean by precondition and returns to `<epicBranch>` in step 5.
2. Every apply, capture, and any bootstrap carries `--branch <noteBranch>`: `epic-doc` and `notion-dev:knowledge` then assert HEAD's branch is `<noteBranch>` and that `git merge-base --is-ancestor origin/<epicBranch> HEAD` exits 0 — the branch was cut from the epic branch and still contains it — instead of the primary-on-`<epicBranch>` and remote-equality lines, and commit **without pushing**. Under this form, `capture`'s collision search runs against `<knowledge.dir>` in the note-branch working tree rather than an export of `origin/<epicBranch>`, so a re-run of this command for the same fact before the PR merges sees the earlier capture on `<noteBranch>` and reports `untouched` instead of writing a duplicate concept.
3. No commit after the loop → `git checkout <epicBranch>`, `git branch -D <noteBranch>`, report `nothing to land`, and go to the report. Otherwise `git push -u origin <noteBranch>` — the note branch by now carries both the note (and bootstrap) commits and every epic's capture commit, pushed together, once — and open the pull request — `gh pr create --base <epicBranch> --body-file -` with a heredoc on stdin, as `/notion-dev:ticket` Phase 5 spells it; never `--body` — titled `docs(epic): new info — <short fact>`, the body listing every epic changed with its `REASON`. A rejected push here leaves `<noteBranch>` and its commits local, **never forces**, adds a `blocked:` line of the same shape naming the branch and git's rejection, skips the pull request, and goes to the report.
4. Invoke `notion-dev:review-and-merge <pr> [--non-interactive] --pre-merge-check "<the completion-pass requirement /notion-dev:ticket Phase 7 passes, verbatim>"`. A run that stops before the merge leaves the branch and the PR for inspection, reports both, and runs nothing from the Notion epic and Tickets steps.
5. Merged → `git checkout <epicBranch> && git pull --ff-only origin <epicBranch>`, `git branch -D <noteBranch>`, and confirm the remote branch is gone (`git ls-remote --heads origin <noteBranch>`; delete it if not, as `/notion-dev:ticket` Phase 9 step 3 does). Then, for every epic whose commit landed, **re-derive the side-effect payloads from the merged state, never from the pre-review proposal**: the review loop may have changed a brief (restored a thread, reworded a decision), so `CLEARED`, `ADDED`, `REPLACED`, `UNBLOCKED`, `THREADS` and `NEXT` are recomputed from **the pull request's own landed diff of that brief, never the whole start-to-final interval** — another resolution may have changed the same brief on `<epicBranch>` while this PR was in review, and `<startSha>..origin/<epicBranch>` would attribute its cleared threads to this fact. For `git.mergeStrategy` `squash` or `merge` that diff is `git diff <merge-sha>^1 <merge-sha> -- <brief path>` (`<merge-sha>` is what `notion-dev:review-and-merge` returned); for `rebase` it is `git diff <startSha> <tipSha> -- <brief path>`, with `<startSha>` from step 1 and `<tipSha>` = `git rev-parse <noteBranch>` recorded **before** the `branch -D` above (a merge-base computed after deletion fails). A brief the bootstrap created on this branch diffs against the in-memory bootstrap — a thread the reviewer put back is not cleared and its tickets are not commented. An epic whose recomputed diff is empty — the review fixes reverted its whole change — is treated exactly like `COMMIT: none`: reported `updated` with `THREADS: +0 -0`, no Notion entry, no comments. Only then do the Notion epic and Tickets steps run for the rest, from those recomputed values.

## Report

Print, in this order:
- The fact, `<short fact>`, and the scope: `N briefs, M open epics without a brief`, or the `--epic` list.
- One line per epic in scope: `[<KEY>-<n>] <title> — updated | created+updated | closed | skipped — <REASON> · knowledge: <captured|empty|failed|unavailable>`, then indented `cleared:` / `added:` / `replaced:` / `next:` / `unblocked:` / `commented:` / `notion: ok | failed` / `AC-impact:` lines, each only when non-empty. The ` · knowledge: …` suffix is present for every epic whose `note --apply` outcome was not `failed` (Apply's `capture` call, above) and omitted for a `skipped` or `failed` epic, which never reached it. A failed epic carries its `CAUSE:`.
- When scope step 2's `findEpics` returned `null`: `epic discovery unavailable — <signature recorded>; scope limited to briefs on disk`.
- Non-interactive decisions: every auto-Apply and every auto-Comment.
- Under `--pr`: the PR URL and merge SHA, or where the run stopped.

**Closeout — zero tails.** Compose the full draft above first, then invoke the **workspace pass** of the `notion-dev:session-closeout` skill via the Skill tool and follow it exactly; end the report with its `CLOSEOUT:` block verbatim, followed by any `tracked:` and `blocked:` lines. An unpushed note, bootstrap, or capture commit is not something that pass finds — enumerating unpushed work is the completion pass's job, and there is no completion pass here — so **this command adds that line itself, before invoking the workspace pass**, reading `- blocked: docs(epic): <note | bootstrap> | docs(knowledge): note commit <sha> unpushed on <epicBranch> — push rejected: <git's message>; unblocked by pushing once the branch accepts it` — the first shape for a rejected `note --apply`/`record --bootstrap` push, the second (L10's commit subject) for a rejected `capture` push. There is no completion pass on the direct-commit path — nothing merges; under `--pr` it ran as step 4's pre-merge check.
