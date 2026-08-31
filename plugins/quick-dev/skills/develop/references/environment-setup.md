# Environment setup and edge cases

Detailed reference for the develop skill's preflight phase. Consult when the happy path in SKILL.md fails.

## Installing the build-flow plugins at project scope

The develop flow depends on two plugins: `feature-dev` (skill `feature-dev:feature-dev` plus agents `code-explorer`, `code-architect`, `code-reviewer`) and `superpowers` (the brainstorming → writing-plans → subagent-driven-development chain). Both must be available at preflight regardless of which flow triage picks.

Standard installs:

```bash
claude plugin install feature-dev@claude-plugins-official --scope project
claude plugin install superpowers@claude-plugins-official --scope project
```

- `--scope project` writes the enablement to the repo's `.claude/settings.json` so the whole project gets it, without touching the user's global config. Do not use user scope — the requirement is project scope.
- If the plugin is already installed at **user** scope (skill already available), do nothing — availability is what matters, not scope.

### Marketplace not configured

If the install fails with an unknown-marketplace error, check configured marketplaces:

```bash
claude plugin marketplace list
```

If `claude-plugins-official` is missing, add it and retry the install:

```bash
claude plugin marketplace add anthropics/claude-plugins-official
```

### Reload requirement

A plugin installed mid-session is NOT loaded into the running session. After installing (one or both plugins), always stop ONCE — with a single message covering everything installed — and instruct the user to run `/reload-plugins` (or restart the session) and re-run `/develop`. There is no way to continue in the same turn — attempting to invoke `feature-dev:feature-dev` or any `superpowers:*` skill before a reload will fail.

### Verifying enablement without the CLI

Project-scope enablement can be confirmed in `.claude/settings.json` at the repo root:

```json
{
  "enabledPlugins": {
    "feature-dev@claude-plugins-official": true,
    "superpowers@claude-plugins-official": true
  }
}
```

If the CLI install fails for an unrelated reason, adding this entry manually (Edit tool, preserve existing keys) achieves the same result — then reload.

## Main branch resolution

Order of preference:

1. `git symbolic-ref --short refs/remotes/origin/HEAD` → e.g. `origin/main`; strip the `origin/` prefix. If it errors with "ref does not exist", repair it with `git remote set-head origin --auto` (needs network) and retry, or fall through.
2. `git show-ref --verify --quiet refs/heads/main` → use `main`; else same for `refs/heads/master`.
3. `git show-ref --verify --quiet refs/remotes/origin/main` → use `main`; else same for `refs/remotes/origin/master` (covers single-branch or detached checkouts with no local default branch).
4. Fall back to the currently checked-out branch (`git branch --show-current`) — and tell the user which branch was chosen as the merge target.

## Mode detection details

GitHub mode requires ALL of:

- `git remote get-url origin` succeeds and points at a GitHub host.
- `gh auth status` exits 0.
- `gh repo view --json nameWithOwner` succeeds from the repo (catches remotes gh can't access).

Anything less → local mode. Local mode is a first-class path, not an error: same end state (feature squash-merged onto `$MAIN`, worktree and branch deleted), just without a PR or Codex.

## Worktree edge cases

- **Branch exists but no worktree** (leftover from an aborted run): do not reuse or delete it silently — it may hold unmerged work. Pick a new slug (`-2` suffix), per the uniqueness rule in SKILL.md Phase 1, and mention the leftover branch in the final report so the user can inspect it.
- **Worktree path exists on disk but unregistered**: run `git worktree prune`, and if the directory remains, choose a different slug — never `rm -rf` a directory the flow did not create in this run.
- **`git worktree remove` fails** with "contains modified or untracked files" during cleanup: this happens after a successful merge when build artifacts (node_modules, target/, etc.) remain. Confirm the path matches `$WORKTREE` recorded earlier in this run, then `git worktree remove --force "$WORKTREE"`.
- **Repo uses submodules**: worktrees need `git -C "$WORKTREE" submodule update --init` after creation.

## Dirty primary checkout at cleanup time

Phase 5 runs `git checkout "$MAIN" && git pull --ff-only origin "$MAIN"` in the primary checkout — as its **second-to-last** step (only the `rmdir` follows), after the worktree and branches are already gone. If the user made unrelated edits there mid-run and the checkout fails, or `$MAIN` has diverged and `--ff-only` refuses, do NOT stash or discard anything. Skip that step and report that `$MAIN` should be checked out / pulled manually. Nothing is left waiting on it: the worktree and branch cleanup ran before it precisely so a blocked primary cannot strand them.
