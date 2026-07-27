---
name: develop
description: This skill should be used when the user runs "/develop", "/quick-dev:develop", asks to "develop a feature end to end", "quick develop", or wants a complete feature flow (branch, worktree, implementation, review, merge, cleanup) driven from a single feature description.
argument-hint: "[--non-interactive] [--flow=feature-dev|superpowers] <feature description>"
disable-model-invocation: true
---

# develop — end-to-end feature flow

Drive a feature from a one-line description to a merged, cleaned-up result on the main branch. The flow: preflight checks → isolated branch + git worktree → flow triage → build (feature-dev or superpowers) → PR → review loop → squash-merge → full cleanup. When the flow finishes, the repository must be on an up-to-date main branch with no leftover worktree, branch, or open PR.

## Input

Arguments: `$ARGUMENTS`

- If the arguments contain the flag `--non-interactive`, remove it and set **non-interactive mode**: never pause for user input; whenever any step (including the build flow's own checkpoints) calls for asking the user, choose the most reasonable option autonomously and record the decision for the final summary.
- If the arguments contain `--flow=<value>`, remove it and record the value as `FLOW_OVERRIDE`. Valid values: `feature-dev`, `superpowers`. Any other value: stop immediately and report the two valid values — before creating any branch or worktree.
- Everything remaining is the **feature description**. If it is empty, stop and ask the user what to develop. Do not guess.

Track progress with the task/todo tools — create one task per phase below and update status as phases start and complete.

## Phase 0 — Preflight

Run all checks before creating anything:

1. **Git repo**: `git rev-parse --show-toplevel`. If not a repo, stop and report. Record the absolute repo root as `REPO_ROOT`, the repo directory name as `REPO_NAME`, and the current UTC time as `RUN_START` (`date -u +%FT%TZ`).
2. **Main branch**: resolve via `git symbolic-ref --short refs/remotes/origin/HEAD` (strip `origin/`). If that fails, use the first that exists (`git show-ref`) of: local `main`, local `master`, remote-tracking `origin/main`, `origin/master`. Only if none exist fall back to the current branch — and tell the user which branch was chosen as the merge target. Record as `MAIN`.
3. **Mode detection**: GitHub mode requires all three: an `origin` remote (`git remote get-url origin`), authenticated `gh` (`gh auth status`), and confirmed reachability of the repo on GitHub (`gh repo view --json nameWithOwner` succeeds — this catches non-GitHub remotes and repos the authenticated user cannot access). If any check fails, use **local mode** (no PR, local review + local squash-merge). Announce the selected mode.
4. **Dirty tree**: if `git status --porcelain` is non-empty, uncommitted changes will NOT be part of the feature (the worktree branches from the last commit). Exception: if the only change is `.claude/settings.json` left by this flow's own plugin bootstrap (step 5 of a prior run), commit it with `git add .claude/settings.json && git commit --only .claude/settings.json -m "chore: enable build-flow plugins"` (the `add` first — the file may be untracked, and `git commit --only` errors on paths git doesn't know) and continue — it is part of the setup, not user work. In **local mode**, stop and ask the user to commit or stash first — the local squash-merge (Phase 4) runs in the primary checkout and must not mix in unrelated changes (non-interactive: stop and report; do not stash on the user's behalf). In **GitHub mode**: interactive — ask whether to proceed anyway or stop; non-interactive — proceed and note it in the summary. When proceeding, save the `git status --porcelain` output as `PREEXISTING_DIRTY` — these changes will still be present after the merge, and cleanup/verification must account for them.
5. **Build-flow plugins**: both flows must be available regardless of which one triage will pick. Check the available-skills list for `feature-dev:feature-dev` (feature-dev plugin) and `superpowers:brainstorming` (superpowers plugin). For each plugin whose skill is missing:
   - Install at project scope: `claude plugin install feature-dev@claude-plugins-official --scope project` and/or `claude plugin install superpowers@claude-plugins-official --scope project`
   - The installs write enablement to `.claude/settings.json` — commit that change once with `git add .claude/settings.json && git commit --only .claude/settings.json -m "chore: enable build-flow plugins"` so the bootstrap does not trip the dirty-tree gate on the re-run. The `add` is required: a freshly created settings file is untracked and `git commit --only` errors on untracked paths; `--only` still keeps any paths the user had staged out of the bootstrap commit. Exception: if the repo gitignores the path (`git check-ignore -q .claude/settings.json` succeeds), skip the add/commit entirely — an ignored file never shows in `git status`, so it cannot trip the dirty-tree gate the commit exists to protect; do not force-add over the project's ignore rules.
   - Then STOP with **one** combined message naming everything that was installed: "<plugin(s)> installed at project scope (settings change committed). Run `/reload-plugins`, then re-run `/quick-dev:develop <description>`." Newly installed plugins only load after a reload — do not attempt to continue without them, and never stop twice when both were missing.
   - For marketplace edge cases and install troubleshooting, consult `references/environment-setup.md`.
6. **Reviewer (GitHub mode only)**: run the **reviewer resolution procedure** in `../review-and-merge/references/reviewer-config.md` now, so the choice is made before the build rather than mid-review. It reads the gitignored per-clone config (`$REPO_ROOT/.claude/quick-dev/config.json`); if `reviewer` is unset it prompts (interactive) or defaults to `codex` (non-interactive) and persists it. Record the resolved reviewer for the final summary. **Skip entirely in local mode** — there is no GitHub reviewer to configure; the local fresh-agent reviewer is always used.

## Phase 1 — Branch and worktree

1. Derive a kebab-case slug from the feature description: lowercase, alphanumerics and hyphens only, max ~40 chars, meaningful (e.g. "Add rate limiting to the API" → `add-api-rate-limiting`). Record it as `SLUG` and record `BRANCH=feature/$SLUG`.
2. Ensure uniqueness: if the local branch, the worktree directory, or — in GitHub mode — the remote branch (`git ls-remote --heads origin "feature/$SLUG"` non-empty) already exists, append `-2`, `-3`, … to the slug (leftover-state details in `references/environment-setup.md`, "Worktree edge cases"). Checking the remote up front prevents a post-implementation `git push -u` rejection or an accidental update of someone else's branch/PR.
3. Set the start point: GitHub mode — `git fetch origin` and record `BASE=origin/$MAIN`; local mode — record `BASE=$MAIN` if a local branch by that name exists, else `BASE=origin/$MAIN` (when Phase 0 resolved `MAIN` from a remote-tracking ref only — never pass a branch name the repo cannot resolve as a start point).
4. Create the worktree as a sibling of the repo:
   ```bash
   git worktree add "$(dirname "$REPO_ROOT")/${REPO_NAME}-worktrees/$SLUG" -b "$BRANCH" "$BASE"
   ```
   Record the absolute worktree path as `WORKTREE`.
5. `cd "$WORKTREE"` and perform **all** subsequent work there. Use absolute paths under `$WORKTREE` for every file read/write/edit until cleanup. Never modify files under `$REPO_ROOT` during the feature work — with one sanctioned exception: ledger writes under `$REPO_ROOT/.claude/quick-dev/` (Phases 2a and 6, and failure handling), a self-ignored directory that never appears in `git status`.

## Phase 2 — Triage and build

### 2a — Triage (choose the flow)

Invoke the `quick-dev:flow-triage` skill via the Skill tool from inside `$WORKTREE`, with args built as follows, then the feature description:

- always: `--ledger-root="$REPO_ROOT" --run-id="$SLUG"`
- non-interactive mode: add `--auto`
- `FLOW_OVERRIDE` set: add `--forced-flow=$FLOW_OVERRIDE`

From its final output block record `FLOW` (the `FLOW:` line), `MICRO_PLAN` (the `MICRO-PLAN:` block), and `SCOUT_FINDINGS` (the `SCOUT-FINDINGS:` block). Triage handles its own confirmation prompt, ledger decision record, and degradation (see that skill); do not re-ask the user here.

### 2b — Build

**`FLOW=feature-dev`**: invoke the `feature-dev:feature-dev` skill via the Skill tool, passing the feature description plus `MICRO_PLAN` as seed context for its exploration and architecture steps. Follow its full flow (explore → clarify → architect → implement → review) from inside `$WORKTREE`.

**`FLOW=superpowers`**: run the chain from inside `$WORKTREE`, in order:

1. `superpowers:brainstorming` — pass the feature description plus `MICRO_PLAN` and `SCOUT_FINDINGS` as seed context so it does not re-discover them. Interactive mode: its question-by-question dialogue and design/spec approval gates run normally. It writes the spec under `docs/superpowers/specs/` on the branch.
2. `superpowers:writing-plans` — produces the implementation plan under `docs/superpowers/plans/`, committed on the branch. (Spec and plan land in the squash merge.) Brainstorming's own hand-off already invokes this skill after spec approval — when that happened, this step is complete; never invoke it a second time to produce a duplicate plan. **Record the plan's path as `PLAN_PATH`** and the spec's path as `SPEC_PATH` — the next step needs both, and this flow uses writing-plans' default location rather than a fixed filename.
3. `quick-dev:plan-review` — independent review of the plan before any of it is built. Invoke via the Skill tool with `--plan="$PLAN_PATH" --spec-file="$SPEC_PATH"` (add `--auto` in non-interactive mode), and a context packet whose `INTENT:` block is the feature description, `SCOUT-FINDINGS:` and `MICRO-PLAN:` are the blocks recorded in Phase 2a, and `VERIFY:` lists the project's test/build commands if any exist — discover them from the repo at this point (the same suite Phase 2c will run); no earlier phase records them. It dispatches a fresh reviewer against the plan **and the codebase**, triages the findings, revises the plan, and returns a `PLAN-REVIEW:` output block. Record its whole output block — `PLAN-REVIEW`, `FINDINGS`, `ACCEPTED`, `DECLINED`, `UNRESOLVED-CRITICAL`, `UNRESOLVED-REQUIRED`, `NOT-IN-SCOPE`, `DECLINED-WITH-REASONING`, and `UNRESOLVED` — for the ledger (Phase 6) and the final report; carry `NOT-IN-SCOPE` into the PR body in Phase 3.

   **`--auto` and `PLAN-REVIEW: blocked`** (≥1 unresolved Critical): STOP per "Failure handling" below — leave the worktree, branch, and plan intact and report the blockers. Do not implement a plan already known to be Critically flawed. `proceed-with-warnings`, `clean`, and `degraded` all continue.
4. **Hard gate — plan approval** (interactive only; skipped entirely under `--non-interactive`, where step 3's rule already decided). Present a short summary — not the whole plan file: what the review changed, what it declined and why (`DECLINED-WITH-REASONING`), and anything still unresolved. Then ask via `AskUserQuestion`: **Approve** — proceed to step 5; **Revise** — capture the user's feedback, edit the plan, and re-ask **this gate**. Do not re-invoke `quick-dev:plan-review`: it has already run, and human iteration is deliberately outside it. Blocking: do not implement without approval. When `PLAN-REVIEW: blocked`, say so plainly and make Revise the recommended option.
5. `superpowers:subagent-driven-development` — executes the plan in-session, fresh subagent per task with per-task review.

Explicit deviations from stock superpowers — state them when invoking so the flows do not fight: skip `superpowers:using-git-worktrees` (Phase 1 already made the worktree); skip `superpowers:finishing-a-development-branch` (Phases 3–6 own ship/review/merge/cleanup); superpowers' end-of-branch code review is not a substitute for the Phase 4 review loop, which runs identically for both flows.

Either flow, non-interactive mode: at every checkpoint — clarifying questions, brainstorming dialogue, design/spec/plan approval gates, per-task review pauses — self-answer with the most reasonable choice and log the decision. Automated self-reviews (e.g. brainstorming's spec self-review) still run; only *user* gates are auto-passed.

### 2c — Verify

After the build flow completes, verify the working state: run the project's tests/build if they exist and confirm they pass before shipping. Fix failures before continuing.

## Phase 3 — Ship

**Plugin version bump**: if the target repo is itself a Claude Code plugin (`.claude-plugin/plugin.json` exists at the worktree root), the manifest `version` must change exactly once per `/develop` run before the commit:

1. Skip only if the feature work already **increased** it: parse `version` from `git show "$BASE":.claude-plugin/plugin.json` and from the worktree manifest, and compare as semver. Strictly greater → the bump exists; never double-bump. Equal, lower, or merely a reformatted line → not a bump; continue to step 2. (Compare the working tree, not committed history — at this point the feature edits are still uncommitted.) If the manifest does not exist at `$BASE` — this run created the plugin — the manifest's initial version **is** the release version: skip the bump and report it as `new plugin @ <version>`.
2. Otherwise classify this run's change and bump semver accordingly: breaking behavior for existing users → **major**; new capability (command, skill, option, mode) → **minor**; fix, docs, refactor, internal-only → **patch**.
3. Record `old → new` and the classification; state it in the PR body and the final summary so the user can override it before merge.

Non-plugin repos skip this entirely.

Commit any remaining uncommitted work in the worktree with a clear conventional message describing the feature (one commit is fine; the merge will squash anyway). If `git status --porcelain` is already empty — normal on the superpowers path, whose tasks commit as they go — skip the commit rather than failing on "nothing to commit"; the branch's existing commits are the feature.

**GitHub mode**:
1. `git push -u origin "$BRANCH"`
2. Create the PR against `$MAIN`:
   ```bash
   gh pr create --base "$MAIN" --head "$BRANCH" --title "<feature title>" --body "<summary of what was built and why>"
   ```
3. Record the PR number.

**Local mode**: make the commit as above, then skip the push and PR — continue to Phase 4's local path.

## Phase 4 — Review and merge

**GitHub mode**: invoke the `quick-dev:review-and-merge` skill via the Skill tool with args `<pr-number>` (append `--non-interactive` if set). It resolves the configured reviewer (Codex or Copilot — already set in Phase 0 for this flow), handles review comments, reviewer rounds with a local-reviewer fallback, the squash-merge, and remote branch deletion. Remain in `$WORKTREE` while it runs so review fixes land on the branch.

**Plugin repos — stale-bump guard**: the base branch can move while the review loop runs, and git merges identical version-line changes without conflict — so the bump computed in Phase 3 can go stale. Since review-and-merge performs the merge itself, pass the guard through its `--pre-merge-check` argument, e.g.:

```
quick-dev:review-and-merge <pr-number> --pre-merge-check "the manifest version in .claude-plugin/plugin.json on this branch must be strictly greater, as semver, than in git show origin/<MAIN>:.claude-plugin/plugin.json (missing at base = new plugin, check passes) — if equal or lower, the base moved: first update the branch with the current base (merge origin/<MAIN> into the branch; editing the version line without updating first would conflict with the base's change to the same line), then recompute the semver bump against the current base version, commit, and push"
```

Never merge a plugin PR whose manifest version equals the base's current version.

**Local mode**:
1. Spawn a fresh `general-purpose` reviewer agent (synchronous) with a self-contained prompt: apply the `quick-dev:local-code-review` skill (shipped with this plugin) exactly, including its output contract (severity-graded findings and a final `VERDICT: CLEAN` / `VERDICT: NOT-CLEAN` line). Material: the branch diff (`git diff "$BASE"...HEAD` in `$WORKTREE` — `BASE` from Phase 1 is always a resolvable ref, unlike `$MAIN`, which may exist only as a remote-tracking branch), the feature description (the intent to judge correctness against), and the current HEAD sha to echo as `Reviewed commit: <sha>`. The reviewer is review-only: it must not edit files, commit, or push.
2. Evaluate findings with technical rigor using the `quick-dev:receiving-code-review` skill — agree/partially agree/disagree per finding, never apply blindly. Apply justified fixes, re-run tests, commit.
3. If any fixes were committed this round — whatever the verdict (a `VERDICT: CLEAN` round can still carry applied Optional/Nit fixes) — spawn one more fresh reviewer on the new HEAD (same contract) — at most 2 re-reviews total. Apply the same judgment bar as the review loop: a well-reasoned decline beats a low-confidence edit, and findings that are theoretical or insignificant end the loop rather than extend it. If Critical/Required findings remain after that, list them in the final summary.
4. **Merge gate**: findings the flow declined with reasoning (step 2) are resolved and do not block; if any *accepted-but-unfixed* Critical/Required finding remains, do not proceed to the merge silently — interactive: ask the user (merge anyway / stop and leave the branch + worktree for manual follow-up); non-interactive: stop and report, leaving the branch and worktree intact — never land a known Critical/Required defect on `$MAIN` autonomously (the local squash has no PR where the finding would stay visible).
5. Squash-merge locally from the primary checkout — first confirm it is still clean (`git -C "$REPO_ROOT" status --porcelain`); if not, stop and report rather than mixing unrelated changes into the squash commit:
   ```bash
   git -C "$REPO_ROOT" checkout "$MAIN"
   git -C "$REPO_ROOT" merge --squash "$BRANCH"
   git -C "$REPO_ROOT" commit -m "<feature title>"
   ```

## Phase 5 — Cleanup

Only start cleanup after confirming the merge landed: GitHub mode — `gh pr view <pr> --json state` reports `MERGED`; local mode — the squash commit exists on `$MAIN`. **Never delete unmerged work.**

From `$REPO_ROOT` (leave the worktree first):

1. GitHub mode: `git checkout "$MAIN" && git pull origin "$MAIN"` so the primary checkout contains the merged feature. This step is **best-effort**: if it fails (e.g. `PREEXISTING_DIRTY` changes conflict with the update), do not stash or discard anything — continue with the remaining cleanup steps and report that `$MAIN` needs a manual checkout/pull. The merge already landed; a blocked local update must not strand the worktree and branch cleanup below.
2. Remove the worktree: `git worktree remove "$WORKTREE"` (add `--force` only if it fails on untracked leftovers, after confirming the path is the worktree this flow created — see "Worktree edge cases" in `references/environment-setup.md`). Then `git worktree prune`.
3. Delete the local branch: `git branch -D "$BRANCH"` (`-D` is required — squash merges are not detected by `-d`; safe because the merge was verified above).
4. GitHub mode: verify the remote branch is gone (`git ls-remote --heads origin "$BRANCH"`); delete it if the merge step didn't: `git push origin --delete "$BRANCH"`.
5. Remove the `<repo>-worktrees` parent directory if now empty: `rmdir` (not `rm -rf`).

## Phase 6 — Verify and report

Confirm the end state, with evidence:

- `git -C "$REPO_ROOT" status` → on `$MAIN`, clean — or, if `PREEXISTING_DIRTY` was recorded at preflight, containing exactly those pre-existing changes and nothing else. Report them as untouched user changes, not as flow leftovers.
- `git -C "$REPO_ROOT" log --oneline -1` → shows the squash commit for the feature.
- `git worktree list` → no longer contains `$WORKTREE` (pre-existing unrelated worktrees are the user's — leave them alone and do not count them as leftovers).
- `git branch --list "$BRANCH"` → empty; GitHub mode: remote branch gone and PR state `MERGED`.

**Ledger outcome**: append one outcome line to `$REPO_ROOT/.claude/quick-dev/ledger.jsonl` per the schema in `../flow-triage/references/ledger.md`: `{"event":"outcome","run_id":"<SLUG>","ts":"<UTC now>","result":"merged","review_rounds":<n>,"fix_commits":<n>,"files_changed":<n>,"insertions":<n>,"deletions":<n>,"duration_minutes":<n>,"plan_review_findings":<n>,"plan_review_accepted":<n>,"plan_review_declined":<n>,"plan_review_unresolved":<n>}`. Review rounds and fix commits come from Phase 4's loop (what review-and-merge or the local loop reported); diff stats from the squash commit (`git -C "$REPO_ROOT" show --shortstat --format= <squash-sha>`); duration from `RUN_START` to now. Plan-review metrics come from Phase 2b step 3's output block (`FINDINGS`, `ACCEPTED`, `DECLINED`, and `UNRESOLVED-CRITICAL` + `UNRESOLVED-REQUIRED` summed); all four are `null` wherever there is no review signal to record — the `feature-dev` path, which has no plan to review, and a `degraded` review, where the reviewer never ran. On a degraded review write `null`, **not** the zeros its output block carries: `0` findings would be indistinguishable from a review that ran and found nothing, and that is exactly the distinction this ledger exists to preserve. Any metric that cannot be determined is `null` — and a ledger problem never fails the run.

Report: what was built (files changed, tests), which flow triage chose and why (score, confidence, any override), the merged PR URL (GitHub mode), review rounds summary, any non-interactive decisions taken, and confirmation that the workspace is clean. On the `superpowers` path, also report the plan-review outcome — status, findings, accepted vs. declined counts — and list any unresolved blockers the run proceeded past explicitly; a `proceed-with-warnings` run must not bury them. State `degraded` plainly when the reviewer could not run.

## Failure handling

On any unrecoverable failure (tests can't pass, PR unmergeable, review loop stopped, conflicts):

- STOP. Do not force anything and do not run cleanup — leave the worktree, branch, and PR intact for inspection.
- Report exactly what state remains (worktree path, branch name, PR number) and the exact commands to either resume or manually clean up.
- Best-effort, before stopping: append a ledger outcome line (schema in `../flow-triage/references/ledger.md`) with `result` `"failed"` (unrecoverable failure) or `"stopped"` (user abort) and `null` metrics — **except** the `plan_review_*` fields, which carry their real values from the plan-review output block whenever the review ran. A `blocked` exit is the single most valuable case to calibrate on, and the schema reserves `null` for *no review signal*, which is not what happened here. If the append itself fails, ignore it — never let ledger bookkeeping mask the real failure report.

## Additional Resources

- **`references/environment-setup.md`** — build-flow plugin installation details, marketplace troubleshooting, main-branch and remote resolution, worktree edge cases (leftover branches, failed removal, submodules), and dirty-primary-checkout handling at cleanup time.
