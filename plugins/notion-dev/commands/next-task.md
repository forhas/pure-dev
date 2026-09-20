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

**Continuous execution — non-interactive mode is *never hand back*, not only *never ask*.** Do not end your turn between steps, between delegated `/notion-dev:ticket` runs, or after any skill or subagent returns. A message that ends with `Next: <the thing you were about to do>` and then stops is the exact failure this rule names, and the self-answer rule above does not reach it: no question was asked, so nothing was left unanswered — the run simply handed back, and in a non-interactive run nobody is watching to type "continue". Announcing what comes next is fine; announcing it *instead of doing it* is the defect. This binds the `--depth` loop in particular: a delegated run returning is the cue to re-read the brief and start the next ticket, never the cue to report and stop. The only things that end a non-interactive run are the stop conditions this command names explicitly and its final report.

**Standing rule — runtime issues.** Anything unexpected at runtime is recorded via `notion-dev:issue-log` at the moment it happens; that skill is authoritative for what counts. A failure to write the log never fails the run.

## Preconditions

Identical to `/notion-dev:ticket`'s precondition block, applied verbatim: `dependencies.superpowers` and `dependencies.featureDev` both `true`; `gh auth status` and `jq --version` succeed; `REPO_ROOT` recorded first as the primary checkout from `git worktree list`; `.claude/notion-dev.config.json` present and read from `$REPO_ROOT`; an `origin` remote; and a clean working tree where the only exempt dirt is the init-generated setup files and the harness-managed `.claude/settings.local.json` — report offending paths and the right remedy (`git stash -u` for untracked) exactly as that block does. This command delegates to `/notion-dev:ticket`, which re-checks all of it; checking here first means a failure surfaces before any epic bookkeeping.

- `<run id>` = `next-task-$(date -u +%Y%m%dT%H%M%SZ)-<4 hex>` (e.g. `next-task-20260915T101500Z-a3f9`; the hex from `head -c2 /dev/urandom | od -An -tx1 | tr -dc '0-9a-f'`), generated once at the start of this command and carried through every `lock take` and `lock release` of this run — so a second concurrent invocation is a different holder, while this run's own re-takes stay re-entrant. **Not** `next-task <KEY>-<n>`: two loops on one epic is the workflow this command advertises, and that label is identical for both, so `lock take` would read the second as a re-entrant acquisition by the first — putting both in the bootstrap or drift write path at once, each able to release the other's lock while both check out, commit, reset and push from the primary.

`python3` in every `knowledge.py` line below stands for `knowledge.python` from `.claude/notion-dev.config.json` (default `python3`; `python` or `py -3` on Windows, as `/notion-dev:init` recorded).

Then the **inverted epic guard**: `fetchTicket(<epic-id>)` via `notion-dev:ticket-system`. The page is an epic when `metadata.parentTaskProperty` is `""` **and** `metadata.epicMarkerProperty` is `true` — the same predicate `/notion-dev:ticket`'s guard applies, read the other way — not an epic → abort: `[<KEY>-<n>] <title> is not an epic container — run /notion-dev:ticket <id> to implement it`. Epic status in the resolved set (`statusMap.implemented` / `done` / `cancelled`) → report `epic closed — nothing to do` and stop. Record `EPIC_KEY`, `EPIC_URL`, `EPIC_TITLE`.

## The loop

`DONE = 0`. Repeat while `DEPTH` is `all` or `DONE < DEPTH`:

### 1. Read the brief

Invoke the `notion-dev:knowledge` skill, operation `retrieve(<epic-id>)`. It returns `KNOWLEDGE_CONTEXT`, `EPIC_CONTEXT`, `NEXT`, `BLOCKED`, `STATUS`, `CHILDREN`, `BOOTSTRAP`, `DRIFT`, and `SEED`.

**One retrieve per iteration.** This is the loop's only read of the bundle: step 4 hands its result back here, so an iteration that follows another starts from what step 4 already fetched rather than fetching again. Two full-budget retrieves back to back, against the same brief, is exactly the second read the "read once" rule exists to prevent.

`STATUS: closed` → stop: `epic complete` — print the brief's `## Next` and end — **unless the epic's live status (from the preconditions' `fetchTicket`) is not in the resolved set**: the epic was reopened in Notion after the brief closed, so the header is stale, not authoritative. Say so, continue as if `STATUS` were `open` (the next `record` repairs the header), and pick from `CHILDREN` under the rules below.

**`BOOTSTRAP: true` — create the brief before doing anything else.** The primary is clean (preconditions), so: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section bootstrap --wait 600` (`<run id>` from the preconditions; exit 1 → stop with `CAUSE: primary lock held by <run> (<section>) since <time>` — a brief that cannot be committed is not a basis for selection). On either stop below — the `--ff-only` diverged-base stop or `EPIC-DOC: failed` — release the lock first (the same `lock release` line below), then report. Then `git -C $REPO_ROOT checkout <epicBranch> && git -C $REPO_ROOT pull --ff-only origin <epicBranch>` (`<epicBranch>` = `git.prTargetBranch`, falling back to `git.baseBranch` — the branch the brief lives on, per `notion-dev:epic-doc`) (a `--ff-only` failure stops the run with the same diverged-base report `/notion-dev:ticket` Phase 9 gives — never stash or discard). Then invoke `notion-dev:epic-doc`, operation `record --bootstrap <epic-id>`, passing `REPO_ROOT`, `<epicBranch>` as `<baseRefName>`, and `LOCK_HELD`. It writes `<knowledge.dir>/epic/<KEY>-<n>-<slug>.md`, removes the seed plan when there was one (`SEED:` names it), commits `docs(epic): bootstrap <KEY>-<n>`, and pushes. Announce the path and the seed. `EPIC-DOC: failed` → stop and report its `CAUSE:`; a brief that could not be committed is not a basis for automated selection.

Then re-run step 1's `retrieve`, and `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>` first so the loop works from the committed file.

**`DRIFT: true` — repair the brief before picking.** `read` compared the brief's three lists and header against the live children and found them apart (a resolved child still listed, a child in the wrong list, a missing child, a header status that disagrees). From `$REPO_ROOT`: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section drift --wait 600` (exit 1 → stop with `CAUSE: primary lock held by <run> (<section>) since <time>`, exactly as the bootstrap path above stops — handing `LOCK_HELD` to `refresh` after a take that timed out would tell the write path it holds a lock it does not, and let its commit, reset and push race the run that actually holds it; a brief that cannot be repaired is not a basis for selection), then invoke the `notion-dev:epic-doc` skill, operation `refresh(<epic-id>, drift)`, passing `REPO_ROOT`, `<epicBranch>` and `LOCK_HELD`.

Then `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`, and **splice, do not re-read**: replace the root document of the held `KNOWLEDGE_CONTEXT` with the refreshed brief and re-parse `NEXT`, `BLOCKED`, `STATUS` from it — no second `retrieve`; the bundle's other concepts did not change. A drift refresh that returns `EPIC-DOC: failed` → stop with its `CAUSE:` — selection from a brief that could not be repaired is guessing, the same rule the bootstrap applies. `unchanged` cannot occur here (`read` found drift), but is handled as `refreshed` if it does.

Distilling a long hand-written plan is real work; landing it now, rather than holding it in memory across an hour-long ticket run that may stop, is the point of this step.

### 2. Pick

Walk `NEXT` in order. A candidate is **valid** when all of:
- its key matches an entry in `CHILDREN` exactly — a key the live child list does not contain (a mistyped edit to the brief, or a ticket since re-parented elsewhere) is skipped and named in the report, never fetched or delegated;
- its dependencies are settled: fetch its body (`fetchTicket`) and require every ticket its `## Blocked by` section names to be in the resolved set — the brief's item 1 is unblocked by construction, but a later item such as `[STO-71] — after STO-70` is runnable only once what it waits for has resolved, and the `Blocked:` line covers threads, not order;
- its live status in `CHILDREN` is not in the resolved set;
- its key is not in `BLOCKED`;
- it is not in the configured in-progress status (`statusMap.inProgress`, default `In Progress` — compare the live option name against that, never the literal) **without** a worktree of ours — compute the worktree path exactly as `/notion-dev:ticket` Phase 1.2 does (`$(dirname "$REPO_ROOT")/<repo-name>-worktrees/<worktree.prefix>`) and test for it. That status with no worktree means someone else has it: skip it, and say so in the report. With our worktree, read the run marker `$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json`: a `running` marker with a heartbeat younger than 2 hours (compared against `date -u` now — the marker stores UTC) means a live session holds it and it is never a candidate here; `stopped`, an older heartbeat, or no marker keeps it a resume candidate.

**Resume first.** Before walking `NEXT`, scan `CHILDREN` for any child in the configured in-progress status (`statusMap.inProgress`) that **does** have our worktree and whose marker allows a resume (`stopped`, a heartbeat older than 2 hours, or none — never `running` with a fresh heartbeat) **and still passes the other validity rules** — not in `BLOCKED`, its `## Blocked by` dependencies settled. If one exists, it is the pick regardless of order: resuming an interrupted run is the most valuable next action, and `/notion-dev:ticket` owns the resume (its Phase 1.2). Say `resuming [<key>]` instead of `next`. An in-progress worktree whose ticket has since become blocked is not resumed; say so in the report, and leave the worktree for `/notion-dev:ticket`'s resume once the blocker clears.

**No valid candidate in `NEXT`:**
- interactive → `AskUserQuestion` over the remaining children in `CHILDREN` that pass **every** validity rule above (unresolved, not in `BLOCKED`, dependencies settled, not someone else's in-progress ticket, not held by a live `running` marker, not in `LOST`), in Phase/Step order, plus **Stop**;
- non-interactive → the first child in Phase/Step order that passes those same rules, logged as a decision for the report;
- none at all → stop with `epic blocked`, printing the brief's `## Open threads` verbatim — those are what someone must clear.

### 3. Delegate

The selected ticket owns its per-invocation `RUNTIME_STATE` and gates; do not share one state across successive tickets. Preserve the returned runtime evidence path in this command's final report. A child awaiting an asynchronous result has not returned a completed ticket: honor its runtime wait/resume protocol, never increment `DONE` or select another ticket on a launch acknowledgement. A runtime-authorized yield is the narrow waiting exception to continuous execution.

Announce: `Next: [<key>] <title> — <the reason text from the brief's NEXT item, or "resume" / "fallback: first unblocked child">`.

Then invoke `/notion-dev:ticket <key> [--non-interactive] [--flow=<value>] | selected by next-task from <brief path>: <reason>[; <user guidance>]` via the Skill tool, passing exactly the flags recorded above, plus `KNOWLEDGE_CONTEXT` (Step 1) as context so its own 1.1 skips the fetch and the bundle is read once for the whole run. Remain in `$REPO_ROOT`; `/notion-dev:ticket` manages its own worktree and returns there.

### 4. After the run

`DONE += 1` on a merged run.

**`claimed-elsewhere` first.** A delegated run whose last line is `OUTCOME: claimed-elsewhere` is neither a stop nor a resolution: another session claimed the ticket between this loop's read and the worktree add. Do not increment `DONE`, do not re-read the brief (it did not change), record the decision for the report, and pick the next valid candidate from the same `NEXT` — step 2's rules, skipping every key lost this iteration (keep a `LOST` set; it resets when the brief is re-read) — so at most `|NEXT|` lost claims can occur before the no-valid-candidate fallback. A delegated run that aborted at its 1.2 with `held by a live session` is handled like `claimed-elsewhere`: no `DONE`, add the key to `LOST`, pick the next candidate.

The delegated run's own Phase 10 already ran `record`, so the brief on `origin/<epicBranch>` now reflects this resolution. **Re-read it now** — one `retrieve(<epic-id>)` after every delegated run that reaches this point — a merged or stopped run, never a `claimed-elsewhere` one, which returned to step 2 above — whether or not another iteration follows: with the default `--depth 1` there is no next iteration, and the closed-status check and the final `## Next` in the report must come from the rewritten brief, never from the pre-delegation copy still in memory. **That result is the next iteration's step 1**: pass it forward as `KNOWLEDGE_CONTEXT` and step 1 skips its own fetch, so one iteration costs one retrieve, not two. Parse the fields out of it exactly as `epic-doc` `read` parses them — handing that `KNOWLEDGE_CONTEXT` to `read` is the name for that parse, and on that path `read` fetches nothing.

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
