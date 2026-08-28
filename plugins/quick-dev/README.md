# quick-dev

One-command feature development for Claude Code. `/develop <description>` takes a feature from a single sentence to a squash-merged commit on main — implemented in an isolated git worktree, reviewed in a PR loop, and fully cleaned up afterwards.

## Flow

```
/quick-dev:develop "add rate limiting to the API"
   │
   ├─ 0. Preflight      git repo, gh auth, main branch, build-flow plugins
   │                    (auto-installs feature-dev + superpowers at project scope if missing)
   ├─ 1. Isolate        feature/<slug> branch + worktree at ../<repo>-worktrees/<slug>
   ├─ 2a. Triage        flow-triage: read-only codebase probe → 7-dimension scorecard →
   │                    feature-dev (small–medium) or superpowers (medium-plus); per-repo
   │                    outcome ledger breaks gray-zone ties; confirm or override
   ├─ 2b. Build         feature-dev: explore → clarify → architect → implement → review
   │                    or superpowers: brainstorm → write plan → plan-review (fresh agent
   │                    checks the plan against the codebase; revises it) → approve →
   │                    subagent-driven execution
   ├─ 3. Ship           commit, push, open PR against main
   │                    (plugin repos: semver-bump .claude-plugin/plugin.json —
   │                     major/minor/patch judged from the change, stated in the PR)
   ├─ 4. Review & merge review-and-merge skill: resolve comments, configured-reviewer
   │                    rounds (Codex or Copilot; local code-reviewer fallback if
   │                    unavailable), squash-merge
   ├─ 5. Clean up       delete worktree, local + remote branch; pull main
   └─ 6. Verify         clean tree on up-to-date main, nothing left behind
```

## Usage

```
/quick-dev:develop <feature description>
/quick-dev:develop --non-interactive <feature description>
/quick-dev:develop --flow=feature-dev|superpowers <feature description>
```

- **Default (interactive)**: the triage confirmation and the chosen build flow's natural checkpoints are kept — clarifying questions, architecture or design approval. Everything after implementation (PR, review loop, merge, cleanup) runs unattended.
- **`--non-interactive`**: fully autonomous; every judgment call — including accepting the triage recommendation and the build flow's own checkpoints — is made automatically and reported in the final summary.
- **`--flow=<flow>`**: bypass the triage heuristic and force `feature-dev` or `superpowers`; the override is still recorded in the ledger.
- **The run states its definition of done before it starts.** Triage derives 3-6 observable acceptance criteria from your feature description before any code exists — with a coverage map naming every sentence of the request and which criterion covers it — and the PR body freezes them before review. At merge, the completeness gate checks each one, and anything not met becomes an `absorb` / `file` / `drop` item rather than a silent omission. Locally, unmet criteria land as `Unmet:` trailers on the squash commit, so `git log --grep '^Unmet:'` shows where a definition of done shrank.

The review phase is also usable standalone on any open PR:

```
/quick-dev:review-and-merge <pr-number>
```

## Code reviewer (GitHub mode)

In GitHub mode the review loop drives a configurable reviewer:

- **`codex`** (default) — triggers a review via an `@codex review` comment (requires the Codex GitHub app).
- **`copilot`** — requests the `copilot-pull-request-reviewer[bot]` reviewer via the GitHub API (requires Copilot code review enabled for the repo/org).

Either falls back to the local fresh-agent reviewer when the chosen reviewer is unavailable.

The choice is stored per-clone in `.claude/quick-dev/config.json` (gitignored, alongside the ledger):

```json
{ "reviewer": "codex", "reviewsCap": 15 }
```

The first `/develop` or `/quick-dev:review-and-merge` run in a repo prompts for it (interactive) or defaults to `codex` (non-interactive) and saves it. To change it later, edit the file — or delete the `reviewer` key (or the file) to be prompted again on the next run. Local mode ignores this setting (it always uses the local reviewer).

`reviewsCap` caps how many review rounds the loop will run — default **15** when the key is
absent or invalid. Nothing writes it; add it by hand to change the ceiling. It applies to the
configured-reviewer loop and the local fallback loop independently, so a run that falls back
can do up to twice that number in total. The cap is a runaway backstop — the loop normally
ends far earlier, when the reviewer reports no meaningful issues or the remaining findings
are declined with reasoning.

## Requirements

- `git` and, for the PR flow, the `gh` CLI authenticated against the repo's GitHub remote.
- `jq` on `PATH` — the review loop parses `gh api` JSON responses with it. Not preinstalled on Windows: `winget install jqlang.jq` (or `choco install jq` / `scoop install jq`). Usually already present on macOS/Linux; if not, `brew install jq` / `apt install jq`.
- The [feature-dev](https://github.com/anthropics/claude-code/tree/main/plugins/feature-dev) and [superpowers](https://github.com/obra/superpowers) plugins — installed automatically at **project scope** on first run if missing (a `/reload-plugins` is required after auto-install).
- Optional: a GitHub code reviewer — the Codex app (`@codex review` rounds, the default) or Copilot code review (`reviewer: copilot`). See [Code reviewer](#code-reviewer-github-mode). Without one (or when the chosen reviewer is out of quota, misconfigured, or silent), the review loop falls back to a local review loop — a fresh agent per round applying the plugin's `local-code-review` skill.

Repos without a GitHub remote (or without `gh` auth) use a **local mode**: same flow and same end state, but review runs locally and the branch is squash-merged without a PR.

## Skills

| Skill | Invocation | Purpose |
|-------|-----------|---------|
| `develop` | `/quick-dev:develop [--non-interactive] [--flow=<flow>] <description>` | End-to-end orchestrator: preflight → worktree → triage → build flow → ship → review → cleanup |
| `flow-triage` | `/quick-dev:flow-triage [--advise-only] <description>` | Recommend feature-dev vs superpowers for a task: scout probe → scorecard → ledger tie-break; standalone or invoked by `develop` |
| `review-and-merge` | `/quick-dev:review-and-merge <pr> [--non-interactive]` | Drive an open PR to merged: resolve threads, configured-reviewer (Codex or Copilot) / local review loop (`reviewsCap` rounds, default 15; green-CI gates), squash-merge, delete remote branch |
| `plan-review` | (invoked by `develop` on the superpowers path) | Independent pre-implementation review of a written plan: fresh agent verifies it against the actual codebase, findings triaged and applied with a self-verification pass, machine-parseable verdict |
| `receiving-code-review` | (invoked by the flows above) | Technical-rigor rules for evaluating review feedback — verify before implementing, reasoned pushback, no performative agreement |

## Safety guarantees

- Never merges with failing/pending required checks or unresolved review threads.
- Never deletes a branch or worktree before verifying the merge landed.
- On unrecoverable failure it stops and leaves the worktree/branch/PR intact for inspection, with exact resume/cleanup commands.

## Credits

The `receiving-code-review` skill is vendored from [obra/superpowers](https://github.com/obra/superpowers) (MIT License, © 2025 Jesse Vincent) so the review flows work standalone, without the superpowers plugin installed.

## Installation

This plugin ships from the [pure-dev](https://github.com/forhas/pure-dev) marketplace. Inside Claude Code:

```
/plugin marketplace add forhas/pure-dev
/plugin install quick-dev@pure-dev
```

Or load it directly from a local checkout without registering:

```
claude --plugin-dir /path/to/pure-dev/plugins/quick-dev
```
