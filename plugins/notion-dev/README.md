# notion-dev

Claude Code plugin that installs a standardized development workflow: `create-task` → `ticket` → `finalize`, with Notion-backed tickets and pluggable input sources.

**Status**: pre-release (0.9.0). MVP = the full ticket pipeline for Notion: dual build flow (feature-dev / superpowers, chosen by flow-triage) and a PR review loop (configurable reviewer — Codex or Copilot — with local fallback), including multi-task mission breakdown, epic containers with a resolution log, and optional ticket assignee. Phase 2 will add develop-branch / release-freeze / hotfix commands.

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
| `/notion-dev:create-task` | Produce a well-formed ticket from a prompt, an existing ticket, or a Notion page. Runs a depth-calibrated interview (`notion-dev:ticket-interviewer`) when requirements need refinement, then decides via `notion-dev:task-breakdown` whether the result is one ticket or a multi-task mission (Epic / Phase / Step / Depends-on). Flags: `--non-interactive` (answers its own interview via a fresh subagent grounded in `--context-file`), `--context-file=<path>`, `--epic=<name>`, `--parent=<id>`, `--assignee=<id>`. |
| `/notion-dev:ticket <ticket-id>` | Full implementation cycle, end to end through merge: worktree → triage (feature-dev or superpowers) → plan review (superpowers path) → build → verify → PR → review loop (Codex or local fallback) → merge → status update → clean up. Also accepts the Notion page id/URL. |
| `/notion-dev:finalize <pr-number>` | Standalone resume/review entry point for an already-open ticket PR: review loop (Codex or local fallback) → merge → run post-merge hooks → update ticket → clean up. |

Ticket titles are prefixed with their ticket ID — `[STO-67] Large-Wallet Stale-Index Incident`. The prefix is applied and stripped automatically; you never type it, and branch names are unaffected.

## Configuration

`.claude/notion-dev.config.json` is git-tracked and validated by `schema/notion-dev.config.schema.json`. Reference the schema via `$schema` for editor-level validation.

Key fields:

- `project.{key, name}` — ticket ID prefix (e.g. `STO`) and short project name (used in worktree naming).
- `ticketSystem` — the Notion ticket-database config: `databaseId` (required) plus optional property-name overrides and `statusMap` / `typeMap` / `staticProperties`. Assignee support adds `assigneeProperty` (the People column, default `"Assignee"`) and `defaultAssignee` (a user id, email, or display name; `""` means create-task prompts each run). `/notion-dev:init` sets both. Epic support adds `parentTaskProperty` (the self-referential Relation linking a ticket to its Epic container page, default `"Parent task"`), `epicMarkerProperty` (the Checkbox that marks a page as an Epic container, default `"Is Epic"` — the **sole** signal used to identify epics; carrying an `Epic` select value alone never makes a page a container), and `creationDateProperty` (default `"Creation Date"`, tolerating either a `Date` property the plugin writes at creation or a `Created time` property Notion auto-fills). All three are absence-tolerant, and each also tolerates a wrong live type by degrading exactly as it does for absence. `epicMarkerProperty` is stricter than a skipped write: when it is unusable — **absent, or present but not a Checkbox** — epics cannot be identified at all, so epic discovery and every epic-aware guard degrade to treating every page as "not an epic" rather than guess from shape, and no operation queries the property.
- `inputSources` — enabled source adapters: any of `"prompt"`, `"existing-ticket"`, `"notion-page"`.
- `git.{baseBranch, prTargetBranch, mergeStrategy, preMergeChecks, postMergeHooks}` — git-flow config; `preMergeChecks` runs as a merge gate inside the review loop (`notion-dev:review-and-merge`), `postMergeHooks` is a phase-2 seam (empty by default).
- `dependencies.{superpowers, featureDev}` — set by `/notion-dev:init` after verifying both build-flow plugins are installed. Both must be `true` for `/notion-dev:ticket` to run.
- `worktree.prefix` — template for worktree directory names. Tokens: `{name}`, `{key}`, `{id}`. Default: `"{name}-{key}-{id}"`.
- `verify.steps[]` — ordered list of `{ name, cmd, retries }` commands run after implementation and before PR.
- `reviewer` — PR reviewer selection: `"codex"` (default) or `"copilot"`. Set during `/notion-dev:init`; can be changed by re-running that command.
- `ticketSystem.statusMap.{done, cancelled}` — **read-only** entries (defaults `"Done"` / `"Cancelled"`). Together with `implemented` they form the *resolved set*: the statuses that count as finished when deciding whether an Epic's children are all done and the Epic should close. No plugin command ever moves a ticket into these states — they exist purely so the Epic-close check understands your board. `/notion-dev:init` asks which of your live Status options belong in the set.
- `reviewsCap` — maximum review rounds the PR review loop runs; default **15** when absent or invalid. Hand-edited (`/notion-dev:init` does not write it). Applies to the configured-reviewer loop and the local fallback loop independently, so a run that falls back can perform up to twice that number in total. It is a runaway backstop — the loop normally ends far earlier.

### Reviewer configuration

The PR review loop uses your configured reviewer. Both options fall back to the local fresh-agent review loop if unavailable.

- **Codex** (`"codex"`, the default): Requires the **Codex GitHub app** to be installed. Codex reviews are triggered by an `@codex review` comment on the PR.
- **Copilot** (`"copilot"`): Requires GitHub Copilot code review to be enabled on your repository or organization. Copilot reviews are requested via the REST API.

Projects upgraded from earlier versions of notion-dev (whose config predates the `reviewer` key) will be prompted to choose a reviewer the next time you run `/notion-dev:ticket` or `/notion-dev:finalize`; that choice applies to the current run only. To persist it, re-run `/notion-dev:init` — the review loop never writes the config itself.

Secrets never belong in this file; MCP auth handles credentials.

The number of rounds either loop will run is capped by `reviewsCap` (default 15). Raise it
for repos where reviews routinely need more iterations; lower it to fail fast. The review
loop never writes this key — edit `.claude/notion-dev.config.json` directly.

## Runtime issue log

When a command or skill hits something unexpected — a configured property missing from your Notion database, an MCP outage, a review that degraded, a step that aborted — the plugin records it in:

```
.claude/notion-dev/notion-dev-issues.md
```

This is automatic. You do not run anything to produce it, and it never interrupts a command: a failure to write the log never fails the run. The file lives in a self-ignored directory, so it never dirties `git status` and never lands in a PR.

**If the plugin misbehaves, send that whole file to whoever maintains the plugin.** It carries identifiers only — property names, command and phase names, a stripped MCP error class/shape (never the raw error text), config shape, plugin version — and never ticket titles, ticket bodies, diffs, PR contents, user ids, or email addresses.

Repeat problems are deduplicated: the same issue collapses to one entry with an occurrence count and a last-seen timestamp, so the file grows with distinct problems rather than with runs. There is no rotation — nothing is ever discarded.

**One caveat worth understanding.** The plugin has no background process. An entry gets written because a running agent recorded it, so quiet degradations are captured well while abrupt failures — a killed process, an interrupt — may leave nothing behind. A short file is not proof that nothing went wrong.

## Ticket system

- `/notion-dev:init` offers to create a new Notion database with the exact schema, or validate/patch an existing one.
- Required properties: `Name` (title), `ID` (number or unique-id), `Status` (select/status), `Type` (select), `PR` (URL).
- Optional: `Assignee` (People) — `/notion-dev:create-task` assigns new tickets to a configured default, or prompts you to pick a workspace user when no default is set.
- Optional: `Creation Date` (Date, or a `Created time` property) — set when a ticket is created.
- Optional: `Parent task` (self-referential Relation) — links a ticket to its Epic container. Required for Epics; without it — or with a same-named column that is **not a self-referential Relation**, which behaves identically (this includes a Relation pointing at a *different* database: the right type, still unusable) — Epic grouping degrades to the `Epic` select tag alone.
- Optional: `Is Epic` (Checkbox) — set automatically by `/notion-dev:create-task` (via `createEpic`) on the container page it creates; never set by hand. This is the **only** thing that makes a page an Epic — carrying an `Epic` select value, or having children, is not enough. Required for Epics; without it — or with a same-named column of any other type, which behaves identically — epics cannot be identified at all and Epic grouping degrades to the `Epic` select tag alone. It must be a **Checkbox**. `/notion-dev:init` reports Epic containers unavailable when no correctly-typed checkbox could be bound at all; if it binds a differently-named checkbox instead, **the marker slot resolves normally** and the mistyped `Is Epic` column is reported as a note. (Epic containers being available needs both slots — the marker *and* `Parent task` — so a resolved marker alone does not settle it.)
- Status options: `Backlog`, `In Progress`, `Implemented`. (The plugin only ever sets `In Progress` and `Implemented`; add `Delivered` or other shipped states yourself if you run a release flow — the plugin doesn't manage them. It *reads* `Done` and `Cancelled` for the Epic-close check — see `statusMap` above.)
- Type options: `Feature`, `Bug`, `Improvement`, `Research`.

## Epics

An **Epic** is a container page in the same ticket database identified by an explicit marker: its `Is Epic` checkbox is `true`, and its own `Parent task` is empty (an epic has no parent of its own). Children point back at it via `Parent task` and typically share the same `Epic` select value, for visual grouping in database views — but that select value is display metadata, not identity. A ticket that merely carries an `Epic` select value — with no children, or even with an ordinary Sub-items child — is **not** a container unless `Is Epic` is checked.

This marker exists because shape alone is ambiguous: on a database upgraded to use Notion's native Sub-items relation for `Parent task`, a legacy `Epic`-tagged *ticket* that picks up an ordinary sub-item satisfies every structural signal an Epic does (empty parent, Epic tag, a child) without actually being one. Only `Is Epic` tells them apart. As of `0.8.0` (unreleased), no prior version of this plugin has ever created an Epic container, so there is nothing to migrate — every install starts clean with the marker already in place.

- **Missions always get one.** When `/notion-dev:create-task` breaks a request into multiple tickets, it reuses a matching Epic page or creates one, and parents every task to it.
- **Single tickets are offered attachment only when an existing Epic plausibly matches** the work — an incident, feature, or investigation already underway. With no plausible match there is no prompt, so routine single-ticket runs stay quiet.
- **Follow-ups land in the same Epic.** When a review defers an item, `/notion-dev:ticket` and `/notion-dev:finalize` file it as a real ticket under the same Epic (always, in `--non-interactive` mode; on confirmation otherwise).
- **`/notion-dev:ticket` refuses to implement an Epic** and lists its children instead — a container is not implementable work.
- **`/notion-dev:ticket` reads its Epic before planning.** A starting ticket pulls the epic's `## Overview`, live sibling statuses (not the `## Tasks` snapshot), and the 3 most recent `## Resolution Log` entries as context — background for its reasoning, never requirements; the ticket body stays the single source of truth for what to build.

An Epic page carries three sections:

| Section | Content |
|---|---|
| `## Overview` | What the initiative or incident is. Written once, at creation. |
| `## Tasks` | Each child with its status: `- [x] [STO-67] Fix stale index — Implemented`. **Refreshed only when a child resolves**, so between resolutions it lags — the live view is Notion's `Parent task` relation column. |
| `## Resolution Log` | Append-only history. Every time a child resolves, a divider and a dated entry are added with what was done, follow-ups filed, how many tasks remain, and what's next. |

When the last unresolved child resolves and no follow-ups are outstanding, the Epic's own status moves to `Implemented`.

**A note on Notion Sub-items.** `/notion-dev:init` can create the `Parent task` relation for you, but the Notion API cannot enable Notion's native *Sub-items* feature — so an API-created relation renders as an ordinary relation column rather than nested sub-rows. Grouping and every plugin behavior work identically either way. For the native nested rendering, enable Sub-items in the Notion UI **before** running `/notion-dev:init`, and init will bind to it instead of creating its own.

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
│   ├── local-code-review/    # fallback reviewer contract (used by review-and-merge)
│   ├── plan-review/          # pre-implementation plan review: fresh agent vs. the codebase (used by ticket)
│   ├── epic-update/          # records a resolved ticket against its epic (used by ticket, finalize)
│   └── issue-log/            # durable, redacted runtime deviation log (used by all four commands, ticket-system)
├── schema/
│   └── notion-dev.config.schema.json
├── LICENSE
└── README.md
```

## Credits

`skills/flow-triage/`, `skills/review-and-merge/`, `skills/local-code-review/`, and `skills/plan-review/` are vendored and adapted from the `quick-dev` plugin. `local-code-review` was itself originally adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills/blob/main/skills/code-review-and-quality/SKILL.md) `code-review-and-quality` (MIT License, © 2025 Addy Osmani).

## License

MIT
