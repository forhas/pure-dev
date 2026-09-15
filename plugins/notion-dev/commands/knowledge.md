---
description: Maintain the repo's knowledge bundle — `capture` re-runs by hand the post-merge write a ticket run skipped or failed, `migrate` moves an existing client bundle onto the plugin's schema (diff first, `--apply` to write), `curate` walks near-duplicate concepts and supersedes the losers. Reading the bundle happens inside a ticket run; these three are what a person invokes.
argument-hint: "capture <ticket-id> <merge-sha> | migrate [--apply] | curate"
disable-model-invocation: true
---

# /notion-dev:knowledge

The three knowledge-bundle operations a person invokes. Reading the bundle is not one of them:
`/notion-dev:ticket` does that through `retrieve`, once per run. Writing normally happens through
the post-merge hook — `capture` here is the same operation run by hand when the hook was skipped
or failed. All three live in the `notion-dev:knowledge` skill, which this command drives.

Args: `capture <ticket-id> <merge-sha> | migrate [--apply] | curate`

Flag parsing: the first argument selects the operation; anything else → fail with usage.
`capture` takes exactly two positional arguments, the ticket id (every form `/notion-dev:ticket`
accepts) and the merge commit SHA; `--apply` is accepted on `migrate` only, and on nothing else.

**Standing rule — runtime issues.** Anything unexpected at runtime is recorded via
`notion-dev:issue-log` at the moment it happens; that skill is authoritative for what counts. A
failure to write the log never fails the run.

## Preconditions

- Record `REPO_ROOT` **first**: the first path listed by `git worktree list` — the primary
  checkout, never a worktree.
- `.claude/notion-dev.config.json` exists in `$REPO_ROOT`; load it. Missing → abort and tell the
  user to run `/notion-dev:init`. Read the `knowledge` block; on `migrate` the block may be
  absent, since writing it is what step 6 of that operation does.
- `iwe --version` succeeds and reports ≥ 0.19. Missing or older → abort, naming both install
  routes: `cargo install iwe --root ~/.local` (works wherever Rust does; required on hosts whose
  GLIBC is older than 2.39, which includes Ubuntu 22.04 under WSL), or `brew install iwe` /
  `npm i -g @iwe-org/iwe` where the prebuilt binary runs. Record `missing-dependency:iwe`.
- `python3 --version` succeeds — the shipped script is Python 3.8+, standard library only.
- `python3` in every `knowledge.py` line below stands for `knowledge.python` from `.claude/notion-dev.config.json` (default `python3`; `python` or `py -3` on Windows, as `/notion-dev:init` recorded).
- `<epicBranch>` = `git.prTargetBranch`, falling back to `git.baseBranch` — the branch the bundle
  lives on. The tree is clean: `/notion-dev:new-info`'s precondition block's clean-tree rule
  applied verbatim — exactly two exempt dirt kinds, the offending paths reported from
  `git status --porcelain`, and `git stash -u` named for untracked dirt. The primary is put on
  `<epicBranch>` below, right after the lock is taken, never here — checking out before the lock
  would let a second run's checkout race this one's.
- On `capture` only, and **after** the checkout and pull that section runs right after taking the
  lock (below): the skill's own four precondition lines, which it asserts itself and which this
  command reports verbatim when one fails. That checkout and pull is what makes the
  remote-equality line assertable by hand; a primary holding unpushed local commits fails it, and
  the remedy is to push or reset them, never to skip the check.
- `<run id>` = `knowledge-$(date -u +%Y%m%dT%H%M%SZ)-<4 hex>` (e.g. `knowledge-20260915T101500Z-a3f9`;
  the hex from `head -c2 /dev/urandom | od -An -tx1 | tr -dc '0-9a-f'`), generated once at the start of
  this command and carried through every `lock take` and `lock release` of this run — so a second
  concurrent invocation is a different holder, while this run's own re-takes stay re-entrant.

## `capture <ticket-id> <merge-sha>`

The post-merge write, run by hand: use it when a ticket run reported that hooks were skipped, or
when the hook returned `KNOWLEDGE: failed` and the cause has since been fixed. It is the same
operation the hook runs, with the same four preconditions and the same write-nothing rule.

First: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section capture --wait 600` (`<run id>` from the preconditions; exit 1 → stop with
`CAUSE: primary lock held by <run> (<section>) since <time>`).

Then `git -C $REPO_ROOT checkout <epicBranch> && git -C $REPO_ROOT pull --ff-only origin <epicBranch>`
(a `--ff-only` failure → release the lock and stop with the diverged-base report).

Invoke the skill `notion-dev:knowledge`, operation `capture(<ticket-id>, <merge-sha>)`, passing
`REPO_ROOT`, `<epicBranch>`, and `LOCK_HELD`. There is no session to draw on here, so the
operation reads its inputs from `fetchTicket(<ticket-id>)` and `gh pr view <n> --json
body,comments` instead — the ticket body and the pull request with its review comments.
Everything else, including the four collision outcomes and the `check`-gated commit, is
unchanged.

Re-running a capture that already landed is safe: every candidate collides with the concept the
first run wrote and resolves as **untouched**, so the result is `KNOWLEDGE: empty` with
`COMMIT: none`. Report the block as it comes back.

Last: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`.

## `migrate`

First: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section migrate --wait 600` (`<run id>` from the preconditions; exit 1 → stop with
`CAUSE: primary lock held by <run> (<section>) since <time>`).

Then `git -C $REPO_ROOT checkout <epicBranch> && git -C $REPO_ROOT pull --ff-only origin <epicBranch>`
(a `--ff-only` failure → release the lock and stop with the diverged-base report).

Invoke the `notion-dev:knowledge` skill, operation `migrate` — `migrate --apply` when the user
passed `--apply` — passing `REPO_ROOT`, `<epicBranch>`, the config path, and `LOCK_HELD`.

Without `--apply`, **print the complete diff verbatim**, file by file, release the lock (the
`Last:` line below) and stop. Nothing is written, nothing is staged, and the run is repeatable:
reviewing that diff is the whole point of the first pass, because it is the only place a client
sees what a field-by-field rewrite of its own bundle will do.

With `--apply`, print the same diff, then what the operation reports: the concepts rewritten, the
brief's new path under `<knowledge.dir>/epic/`, the config keys added and dropped, and the
`check` result. A non-zero check means the operation reverted everything it wrote — report that
as a failure with the findings, not as a partial migration.

Then print the **removal checklist** the operation derived for this client, verbatim and
unticked. This command deletes no client code: the checklist belongs in the body of the client's
own migration PR, which is where each line gets ticked and where every retired check is matched
to the `check` rule that covers it now. Say so in the report, so nobody reads the checklist as
something that already happened.

Last: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`.

## `curate`

**The clusters are put to the user before the lock is taken** — `new-info`'s rule applied here:
no interactive gate is ever held under the primary lock. The lock goes stale after 60 minutes
and deciding which of two similar facts is the durable one is exactly the judgment a person
takes their time over, so a lock held across the questions is a live lock another run breaks;
both writers then believe they hold it and their commits race.

First, holding no lock, invoke the `notion-dev:knowledge` skill, operation `curate`, passing
`REPO_ROOT` and `<epicBranch>`. Its check and its similarity pass read the bundle and write
nothing, and it returns the near-duplicate clusters.

Each cluster comes back with both bodies side by side; put it to the user with `AskUserQuestion`
— one question per cluster, the options being each concept in the cluster and **Keep both**. This
command never picks a survivor on the user's behalf, because which of two similar facts is the
durable one is exactly the judgment a person is here for. A cluster the user skips is left
untouched and named in the report.

Only once every answer is in: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section curate --wait 600` (`<run id>` from the preconditions; exit 1 → stop with
`CAUSE: primary lock held by <run> (<section>) since <time>`).

Then `git -C $REPO_ROOT checkout <epicBranch> && git -C $REPO_ROOT pull --ff-only origin <epicBranch>`
(a `--ff-only` failure → release the lock and stop with the diverged-base report).

Hand the answers back to the operation with `LOCK_HELD` so it supersedes the losers, commits and
pushes. **Re-read the bundle under the lock before applying**: the pull may have landed another
writer's curate, so a cluster whose two concepts are no longer both live, or whose bodies have
changed since they were shown, is skipped and named in the report rather than applied to a file
the user never saw.

Last: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`.

## Report

Print, in this order:

- The operation and its arguments, and the bundle it ran against (`<knowledge.dir>` on
  `<epicBranch>`).
- The `KNOWLEDGE:` line the skill returned, with its `CREATED` / `UPDATED` / `SUPERSEDED` /
  `UNTOUCHED` line and its `COMMIT: <sha> | none`. A `failed` line carries the first `check`
  finding or the git error that caused it.
- On `migrate` without `--apply`: `nothing written — re-run with --apply once the diff is
  reviewed`.
- On `migrate --apply`: the removal checklist, and the reminder that the client PR is what
  deletes the code it lists.
- On `curate`: one line per cluster — `resolved: <survivor> ← <loser>`, `kept both`, or
  `skipped`.
- On `capture`: the ticket key and the merge SHA it read, and — when a precondition failed — which
  of the four lines it was, the branch and HEAD the primary was found on, and the checkout and
  fast-forward pull that make it assertable.

**Closeout — zero tails.** Compose the full draft above first, then invoke the **workspace pass**
of the `notion-dev:session-closeout` skill via the Skill tool and follow it exactly; end the
report with its `CLOSEOUT:` block verbatim, followed by any `tracked:` and `blocked:` lines. An
unpushed commit left by a rejected push is not something that pass finds — there is no completion
pass here — so this command adds that line itself, before invoking the workspace pass, reading
`- blocked: docs(knowledge): <subject> commit <sha> unpushed on <epicBranch> — push rejected:
<git's message>; unblocked by pushing once the branch accepts it`.
