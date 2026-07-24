# notion-dev

Claude Code plugin that installs a standardized development workflow: `create-task` → `ticket` → `finalize`, with Notion-backed tickets and pluggable input sources.

**Status**: pre-release (0.5.0). MVP = the full ticket pipeline for Notion: dual build flow (feature-dev / superpowers, chosen by flow-triage) and a PR review loop (configurable reviewer — Codex or Copilot — with local fallback), including multi-task mission breakdown and optional ticket assignee. Phase 2 will add develop-branch / release-freeze / hotfix commands.

## Prerequisites

- **`superpowers` and `feature-dev` plugins** — **both required**. `/notion-dev:ticket` triages each ticket to one of two build flows: `superpowers` (`superpowers:writing-plans` + `superpowers:subagent-driven-development`) or `feature-dev` (`feature-dev:feature-dev`); the review loop also uses `superpowers:receiving-code-review`. `/notion-dev:init` verifies both are installed and auto-installs whichever is missing at project scope (requires a `/reload-plugins` before continuing).
- **`gh` CLI, authenticated** (`gh auth login`) — **required**. The review loop in `/notion-dev:ticket` and `/notion-dev:finalize` uses `gh` for paginated comment reads and GraphQL review-thread resolution, which the GitHub MCP cannot perform.
- **GitHub MCP server** — optional. `/notion-dev:init` patches the entry into `.mcp.json`; when present, commands prefer it for the operations it supports (PR create, metadata reads, merge) and fall back to `gh`.
- **Codex GitHub app** — optional. Powers the PR review loop's Codex rounds. Without it, `/notion-dev:ticket` and `/notion-dev:finalize` fall back to a local independent-context reviewer (`notion-dev:local-code-review`) — merges still happen, but without cross-model review.
- **Notion MCP** — **required**. `/notion-dev:init` patches the entry into `.mcp.json`.
- `git` on the standard PATH.

## Install

This plugin ships from the [pure-dev](https://github.com/forhas/pure-dev) marketplace. Pick one of the paths below.

### Option 1: Install directly from GitHub (recommended)

Inside Claude Code:

```
/plugin marketplace add forhas/pure-dev
/plugin install notion-dev@pure-dev
```

(For a private repo, Claude Code reuses your existing git credential helper — HTTPS via `gh auth login` or SSH via `ssh-agent`. See [Plugin marketplaces — private repositories](https://docs.claude.com/en/docs/claude-code/plugin-marketplaces#private-repositories).)

Pin to a tag or branch with `@ref`:
```
/plugin marketplace add forhas/pure-dev@<tag>
```

### Option 2: Install from a local clone

```bash
git clone git@github.com:forhas/pure-dev.git
cd pure-dev
```

Then inside Claude Code:

```
/plugin marketplace add /absolute/path/to/pure-dev
/plugin install notion-dev@pure-dev
```

Best when you're actively editing the plugin — changes to command and skill files are picked up when Claude Code reloads (run `/reload-plugins` after edits that affect skill loading).

### Option 3: Load without registering (quick test)

Start Claude Code with an ephemeral plugin path:

```bash
claude --plugin-dir /absolute/path/to/pure-dev/plugins/notion-dev
```

Useful for one-off testing without adding the marketplace to your user config. The flag is per-invocation; nothing is persisted.

### Verify the install

```
/plugin list                # confirms "notion-dev" is installed and enabled
/plugin validate .          # from inside the repo root, checks the manifest
```

If commands don't show up, run `/reload-plugins` or restart Claude Code.

### Uninstall

```
/plugin uninstall notion-dev@pure-dev
/plugin marketplace remove pure-dev
```

## Quick start

In a target project:

```
/notion-dev:init
```

Answer the prompts. The plugin will:
1. Patch your `.mcp.json` — always adds the GitHub MCP server (keyed `github`, skipped if already present); also adds the Notion MCP server.
2. Check that GitHub access will work — the `gh` CLI (required by the review loop) plus the GitHub MCP (optional, preferred where supported). Warns if `gh` isn't installed/authenticated.
3. Bootstrap the ticket database (create a new Notion database, or validate an existing one).
4. Detect a verify suite from your project (Foundry / Node / Python / …).
5. Write `.claude/notion-dev.config.json`.
6. Offer to commit.

Then:

```
/notion-dev:create-task Implement rate limiting on /api/messages
# → creates a ticket in the configured system

/notion-dev:ticket STO-42
# → pass the Notion page id/URL or the ticket key
#   (the Notion page id/URL, or STO-42)
# → worktree, triage (feature-dev|superpowers), build, verify, PR,
#   review loop (Codex or local fallback), merge, status update, clean up

# If /notion-dev:ticket was interrupted after the PR was opened, resume with:
/notion-dev:finalize 42
# → pass the PR number
# → review loop (Codex or local fallback), merge, update ticket, clean up
```

## Commands

| Command | Purpose |
|---|---|
| `/notion-dev:init` | One-time (or re-runnable) setup. Writes config, patches `.mcp.json`, bootstraps the ticket database. |
| `/notion-dev:create-task` | Produce a well-formed ticket from a prompt, an existing ticket, or a Notion page. Runs a depth-calibrated interview (`notion-dev:ticket-interviewer`) when requirements need refinement, then decides via `notion-dev:task-breakdown` whether the result is one ticket or a multi-task mission (Epic / Phase / Step / Depends-on). |
| `/notion-dev:ticket <ticket-id>` | Full implementation cycle, end to end through merge: worktree → triage (feature-dev or superpowers) → build → verify → PR → review loop (Codex or local fallback) → merge → status update → clean up. Also accepts the Notion page id/URL. |
| `/notion-dev:finalize <pr-number>` | Standalone resume/review entry point for an already-open ticket PR: review loop (Codex or local fallback) → merge → run post-merge hooks → update ticket → clean up. |

## Configuration

`.claude/notion-dev.config.json` is git-tracked and validated by `schema/notion-dev.config.schema.json`. Reference the schema via `$schema` for editor-level validation.

Key fields:

- `project.{key, name}` — ticket ID prefix (e.g. `STO`) and short project name (used in worktree naming).
- `ticketSystem` — the Notion ticket-database config: `databaseId` (required) plus optional property-name overrides and `statusMap` / `typeMap` / `staticProperties`. Assignee support adds `assigneeProperty` (the People column, default `"Assignee"`) and `defaultAssignee` (a user id, email, or display name; `""` means create-task prompts each run). `/notion-dev:init` sets both.
- `inputSources` — enabled source adapters: any of `"prompt"`, `"existing-ticket"`, `"notion-page"`.
- `git.{baseBranch, prTargetBranch, mergeStrategy, preMergeChecks, postMergeHooks}` — git-flow config; `preMergeChecks` runs as a merge gate inside the review loop (`notion-dev:review-and-merge`), `postMergeHooks` is a phase-2 seam (empty by default).
- `dependencies.{superpowers, featureDev}` — set by `/notion-dev:init` after verifying both build-flow plugins are installed. Both must be `true` for `/notion-dev:ticket` to run.
- `worktree.prefix` — template for worktree directory names. Tokens: `{name}`, `{key}`, `{id}`. Default: `"{name}-{key}-{id}"`.
- `verify.steps[]` — ordered list of `{ name, cmd, retries }` commands run after implementation and before PR.
- `reviewer` — PR reviewer selection: `"codex"` (default) or `"copilot"`. Set during `/notion-dev:init`; can be changed by re-running that command.

### Reviewer configuration

The PR review loop uses your configured reviewer. Both options fall back to the local fresh-agent review loop if unavailable.

- **Codex** (`"codex"`, the default): Requires the **Codex GitHub app** to be installed. Codex reviews are triggered by an `@codex review` comment on the PR.
- **Copilot** (`"copilot"`): Requires GitHub Copilot code review to be enabled on your repository or organization. Copilot reviews are requested via the REST API.

Projects upgraded from earlier versions of notion-dev (whose config predates the `reviewer` key) will be prompted to choose a reviewer the next time you run `/notion-dev:ticket` or `/notion-dev:finalize`; that choice applies to the current run only. To persist it, re-run `/notion-dev:init` — the review loop never writes the config itself.

Secrets never belong in this file; MCP auth handles credentials.

## Ticket system

- `/notion-dev:init` offers to create a new Notion database with the exact schema, or validate/patch an existing one.
- Required properties: `Name` (title), `ID` (number), `Status` (select/status), `Type` (select), `PR` (URL).
- Optional: `Assignee` (People) — `/notion-dev:create-task` assigns new tickets to a configured default, or prompts you to pick a workspace user when no default is set.
- Status options: `Backlog`, `In Progress`, `Implemented`. (The plugin only ever sets `In Progress` and `Implemented`; add `Delivered` or other shipped states yourself if you run a release flow — the plugin doesn't manage them.)
- Type options: `Feature`, `Bug`, `Improvement`, `Research`.

## Input sources

| Source | Ref format | Notes |
|---|---|---|
| `prompt` | free text | Default; used when no source prefix is given. |
| `existing-ticket` | ticket id or `PREFIX-n` | Fetches the configured ticket system; useful for elaborating thin tickets. |
| `notion-page` | Notion URL or page id | Read any Notion page as seed input. Requires Notion MCP. |

Add a new source by creating `skills/input-source/<name>.md` matching the output shape in `skills/input-source/SKILL.md`.

## Phase-2 seams

The following configuration field exists today but accepts an empty list by default. Phase 2 will ship skills and extra commands that populate it:

- `git.postMergeHooks` — skills invoked after merging (e.g. hotfix-sync, epic-progress-report), run by `/notion-dev:ticket` and `/notion-dev:finalize`.
- Additional commands planned: `prepare-release`, `hotfix`, `hotfix-sync`, `release-fix`, `resume-merges`, `prod-deploy`.

No v1 refactor required to adopt phase 2.

## Layout

```
.
├── .claude-plugin/
│   ├── plugin.json           # plugin manifest
│   └── marketplace.json      # self-contained single-plugin marketplace
├── commands/                 # slash commands (init, create-task, ticket, finalize)
├── skills/
│   ├── ticket-system/        # Notion ticket operations (single SKILL.md)
│   ├── input-source/         # input adapters (SKILL.md + prompt.md + existing-ticket.md + notion-page.md)
│   ├── ticket-interviewer/   # depth-calibrated requirements interview (used by create-task)
│   ├── task-breakdown/       # single-vs-mission split analysis (used by create-task)
│   ├── flow-triage/          # build-flow chooser: bug hard rule, scorecard, ledger (used by ticket)
│   ├── review-and-merge/     # PR review loop: Codex rounds, local fallback, merge gates
│   └── local-code-review/    # fallback reviewer contract (used by review-and-merge)
├── schema/
│   └── notion-dev.config.schema.json
├── LICENSE
└── README.md
```

## Credits

`skills/flow-triage/`, `skills/review-and-merge/`, and `skills/local-code-review/` are vendored and adapted from the `quick-dev` plugin. `local-code-review` was itself originally adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills/blob/main/skills/code-review-and-quality/SKILL.md) `code-review-and-quality` (MIT License, © 2025 Addy Osmani).

## License

MIT
