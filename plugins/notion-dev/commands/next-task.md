---
description: Drive an epic from its markdown brief — pick the recommended next unblocked ticket and run /notion-dev:ticket on it, once or repeatedly (--depth), bootstrapping the brief on first use.
argument-hint: "<epic-id> [--depth all|N] [--non-interactive] [--flow=feature-dev|superpowers] [| <optional guidance>]"
disable-model-invocation: true
---

# /notion-dev:next-task

Reads the epic's brief (`notion-dev:epic-doc`), picks the recommended next ticket, and delegates it to `/notion-dev:ticket` — then re-reads the brief the resolution just rewrote and repeats, up to `--depth`.

Args: `<epic-id> [--depth all|N] [--non-interactive] [--flow=feature-dev|superpowers] [| <optional user guidance>]`

`<epic-id>` accepts every form `/notion-dev:ticket` accepts for a ticket id: the Notion page id, a dashed UUID, the page URL, or the logical key (`STO-60`).

Flag parsing:
- `--depth=<value>` (or `--depth <value>`): remove it and record `DEPTH`. `--depth` absent → 1; `all` → unbounded; a positive integer → that many tickets. Anything else: stop immediately, before touching anything, and name the two valid forms.
- `--non-interactive`: remove it, set **non-interactive mode** for this command's own selection prompt, and pass it through to every delegated `/notion-dev:ticket` run.
- `--flow=<value>`: remove it and pass it through unchanged to every delegated run; `/notion-dev:ticket` validates the value.
- Everything after a `|` is optional guidance, appended to the guidance of every delegated run.
- Whatever remains is `<epic-id>`; empty → fail with usage.

**Standing rule — runtime issues.** Anything unexpected at runtime is recorded via `notion-dev:issue-log` at the moment it happens; that skill is authoritative for what counts. A failure to write the log never fails the run.

## Preconditions

Identical to `/notion-dev:ticket`'s precondition block, applied verbatim: `dependencies.superpowers` and `dependencies.featureDev` both `true`; `gh auth status` and `jq --version` succeed; `REPO_ROOT` recorded first as the primary checkout from `git worktree list`; `.claude/notion-dev.config.json` present and read from `$REPO_ROOT`; an `origin` remote; and a clean working tree where the only exempt dirt is the init-generated setup files and the harness-managed `.claude/settings.local.json` — report offending paths and the right remedy (`git stash -u` for untracked) exactly as that block does. This command delegates to `/notion-dev:ticket`, which re-checks all of it; checking here first means a failure surfaces before any epic bookkeeping.

Then the **inverted epic guard**: `fetchTicket(<epic-id>)` via `notion-dev:ticket-system`. The page is an epic when `metadata.parentTaskProperty` is `""` **and** `metadata.epicMarkerProperty` is `true` — the same predicate `/notion-dev:ticket`'s guard applies, read the other way — not an epic → abort: `[<KEY>-<n>] <title> is not an epic container — run /notion-dev:ticket <id> to implement it`. Epic status in the resolved set (`statusMap.implemented` / `done` / `cancelled`) → report `epic closed — nothing to do` and stop. Record `EPIC_KEY`, `EPIC_URL`, `EPIC_TITLE`.

## The loop

`DONE = 0`. Repeat while `DEPTH` is `all` or `DONE < DEPTH`:

### 1. Read the brief

Invoke the `notion-dev:epic-doc` skill, operation `read(<epic-id>)`. It returns `EPIC_CONTEXT`, `NEXT`, `BLOCKED`, `STATUS`, `CHILDREN`, `BOOTSTRAP`, and `SEED`.

`STATUS: closed` → stop: `epic complete` — print the brief's `## Next` and end.

**`BOOTSTRAP: true` — create the brief before doing anything else.** The primary is clean (preconditions), so: `git -C $REPO_ROOT checkout <epicBranch> && git -C $REPO_ROOT pull --ff-only origin <epicBranch>` (`<epicBranch>` = `git.prTargetBranch`, falling back to `git.baseBranch` — the branch the brief lives on, per `notion-dev:epic-doc`) (a `--ff-only` failure stops the run with the same diverged-base report `/notion-dev:ticket` Phase 9 gives — never stash or discard). Then invoke `notion-dev:epic-doc`, operation `record --bootstrap <epic-id>`, passing `REPO_ROOT` and `<epicBranch>` as `<baseRefName>`. It writes `<epicDocs.dir>/<KEY>-<n>-<slug>.md`, removes the seed plan when there was one (`SEED:` names it), commits `docs(epic): bootstrap <KEY>-<n>`, and pushes. Announce the path and the seed. `EPIC-DOC: failed` → stop and report its `CAUSE:`; a brief that could not be committed is not a basis for automated selection. Then re-run `read` so the loop works from the committed file.

Distilling a long hand-written plan is real work; landing it now, rather than holding it in memory across an hour-long ticket run that may stop, is the point of this step.

### 2. Pick

Walk `NEXT` in order. A candidate is **valid** when all of:
- its dependencies are settled: fetch its body (`fetchTicket`) and require every ticket its `## Blocked by` section names to be in the resolved set — the brief's item 1 is unblocked by construction, but a later item such as `[STO-71] — after STO-70` is runnable only once what it waits for has resolved, and the `Blocked:` line covers threads, not order;
- its live status in `CHILDREN` is not in the resolved set;
- its key is not in `BLOCKED`;
- it is not in the configured in-progress status (`statusMap.inProgress`, default `In Progress` — compare the live option name against that, never the literal) **without** a worktree of ours — compute the worktree path exactly as `/notion-dev:ticket` Phase 1.2 does (`$(dirname "$REPO_ROOT")/<repo-name>-worktrees/<worktree.prefix>`) and test for it. That status with no worktree means someone else has it: skip it, and say so in the report.

**Resume first.** Before walking `NEXT`, scan `CHILDREN` for any child in the configured in-progress status (`statusMap.inProgress`) that **does** have our worktree. If one exists, it is the pick regardless of order: resuming an interrupted run is the most valuable next action, and `/notion-dev:ticket` owns the resume (its Phase 1.2). Say `resuming [<key>]` instead of `next`.

**No valid candidate in `NEXT`:**
- interactive → `AskUserQuestion` over the remaining children in `CHILDREN` that pass **every** validity rule above (unresolved, not in `BLOCKED`, dependencies settled, not someone else's in-progress ticket), in Phase/Step order, plus **Stop**;
- non-interactive → the first child in Phase/Step order that passes those same rules, logged as a decision for the report;
- none at all → stop with `epic blocked`, printing the brief's `## Open threads` verbatim — those are what someone must clear.

### 3. Delegate

Announce: `Next: [<key>] <title> — <the reason text from the brief's NEXT item, or "resume" / "fallback: first unblocked child">`.

Then invoke `/notion-dev:ticket <key> [--non-interactive] [--flow=<value>] | selected by next-task from <brief path>: <reason>[; <user guidance>]` via the Skill tool, passing exactly the flags recorded above. Remain in `$REPO_ROOT`; `/notion-dev:ticket` manages its own worktree and returns there.

### 4. After the run

`DONE += 1`. The delegated run's own Phase 10 already ran `record`, so the brief on `origin/<base>` now reflects this resolution; the next iteration's `read` picks it up.

**Stop early** — do not start another iteration — when any of:
- the delegated run ended in a **stop or failure** (its "Failure and stop conditions" path: a worktree, branch, or PR left for inspection). Never pick the next ticket over a worktree left for inspection; report the run's own stop report verbatim.
- its `EPIC_DOC_REPORT` reads `EPIC-DOC: failed` — the brief is now stale, and selection from a stale brief is guessing.
- the re-read brief reads `Status: closed`.

## Report

Print, in this order:
- One line per delegated run: `[<key>] <title> — <merged | stopped | failed> — <PR URL>`.
- When the loop stopped early: the reason, first.
- The brief's final `## Next` section verbatim, with its path — this is the hand-off to whoever runs this command next.
- Non-interactive decisions this command made (fallback picks, skipped `In Progress` tickets).
- The `CLOSEOUT:` block from the **last** delegated run verbatim, followed by its `tracked:` and `blocked:` lines. This command creates no artifacts of its own beyond the bootstrap commit, which that run's closeout already saw pushed.
