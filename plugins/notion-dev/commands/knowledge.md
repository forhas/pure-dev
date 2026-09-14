---
description: Maintain the repo's knowledge bundle — `migrate` moves an existing client bundle onto the plugin's schema (diff first, `--apply` to write), `curate` walks near-duplicate concepts and supersedes the losers. Reading and writing the bundle happen inside a ticket run; this command is for the two things a person decides.
argument-hint: "migrate [--apply] | curate"
disable-model-invocation: true
---

# /notion-dev:knowledge

The two knowledge-bundle operations a person invokes. Everything else the bundle does happens
inside a run: `/notion-dev:ticket` reads it through `retrieve`, the post-merge hook writes it
through `capture`. Both live in the `notion-dev:knowledge` skill, which this command drives.

Args: `migrate [--apply] | curate`

Flag parsing: the first argument selects the operation; anything else → fail with usage.
`--apply` is accepted on `migrate` only, and on nothing else.

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
- `<epicBranch>` = `git.prTargetBranch`, falling back to `git.baseBranch` — the branch the bundle
  lives on. The primary is on it and the tree is clean: `/notion-dev:new-info`'s precondition
  block applied verbatim, including its two exempt dirt kinds and the
  `git -C $REPO_ROOT checkout <epicBranch> && git -C $REPO_ROOT pull --ff-only origin <epicBranch>`
  it ends with, and its diverged-base report on a `--ff-only` failure — never stash or discard.

## `migrate`

Invoke the `notion-dev:knowledge` skill, operation `migrate` — `migrate --apply` when the user
passed `--apply` — passing `REPO_ROOT`, `<epicBranch>`, and the config path.

Without `--apply`, **print the complete diff verbatim**, file by file, and stop. Nothing is
written, nothing is staged, and the run is repeatable: reviewing that diff is the whole point of
the first pass, because it is the only place a client sees what a field-by-field rewrite of its
own bundle will do.

With `--apply`, print the same diff, then what the operation reports: the concepts rewritten, the
brief's new path under `<knowledge.dir>/epic/`, the config keys added and dropped, and the
`check` result. A non-zero check means the operation reverted everything it wrote — report that
as a failure with the findings, not as a partial migration.

Then print the **removal checklist** the operation derived for this client, verbatim and
unticked. This command deletes no client code: the checklist belongs in the body of the client's
own migration PR, which is where each line gets ticked and where every retired check is matched
to the `check` rule that covers it now. Say so in the report, so nobody reads the checklist as
something that already happened.

## `curate`

Invoke the `notion-dev:knowledge` skill, operation `curate`, passing `REPO_ROOT` and
`<epicBranch>`.

Each near-duplicate cluster comes back with both bodies side by side; put it to the user with
`AskUserQuestion` — one question per cluster, the options being each concept in the cluster and
**Keep both**. The answer is passed straight back to the operation; this command never picks a
survivor on the user's behalf, because which of two similar facts is the durable one is exactly
the judgment a person is here for. A cluster the user skips is left untouched and named in the
report.

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

**Closeout — zero tails.** Compose the full draft above first, then invoke the **workspace pass**
of the `notion-dev:session-closeout` skill via the Skill tool and follow it exactly; end the
report with its `CLOSEOUT:` block verbatim, followed by any `tracked:` and `blocked:` lines. An
unpushed commit left by a rejected push is not something that pass finds — there is no completion
pass here — so this command adds that line itself, before invoking the workspace pass, reading
`- blocked: docs(knowledge): <subject> commit <sha> unpushed on <epicBranch> — push rejected:
<git's message>; unblocked by pushing once the branch accepts it`.
