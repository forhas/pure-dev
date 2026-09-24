# notion-dev

Claude Code plugin that installs a standardized development workflow: `create-task` → `ticket` → `finalize`, with Notion-backed tickets and pluggable input sources.

**Status**: pre-release (0.40.0). The default ticket pipeline is now **lean**: one cohesive
implementation owner, one combined independent code/completeness review, configured external
review, and one shared journaled recording routine. Windows-native Git Bash and Ubuntu/WSL2
remain supported; Python 3.8+ and configured `knowledge.python` remain the floor.

## Review convergence and recording recovery (0.40.0)

- `workflow.py review-prepare` verifies the committed revision before dispatching full/delta
  review. Declare generated reports with `verify.steps[].outputs` or `--output STEP=PATH`;
  reviewers cite immutable archives with revision/command provenance, not mutable coverage files.
- `record-reconcile` binds an already-landed Notion write to its actual call and fresh readback.
  Narrow serialization differences can be reconciled without undoing/replaying provider writes;
  Notion reformatting requires an explicit adapter judgment. Ambiguous outcomes still stop.
- Delta review reuses applicable evidence; empirical claims reference measured results rather
  than repeating speculative test histories. Required validation/review remains intact.
- Ticket recording omits duplicate requirement paragraphs. Knowledge uses accepted deltas;
  complete reviewed follow-ups avoid a second proxy interview; epic recording labels unexamined
  dependencies pending rather than fetching every sibling. Selection still verifies candidates live.

These changes address observed workflow failures; real-ticket token/time savings remain unmeasured.
Both native Windows Git Bash and Ubuntu/WSL2 use the same configured-interpreter commands.

## Scoped execution (0.39.0)

Delta packets include exact changed-input diffs. Worker packets supply submission skeletons,
publication commands and canonical result locations, with an explicit host-return route when
worker report writes are prohibited. Scoped consume/result views avoid global-state discovery.
PR bodies render from stable implementation facts; review status stays in its canonical result.
Common ticket recording derives mapped status, exact AC ticks and resolution sections from
accepted evidence and real live captures. Other host writes accept flat recipes through the
same journal. No provider credentials, new agents or weaker merge gates. Existing packets and
resumptions retain their contracts. See [recording commands](references/boundaries.md).
Sanitized failure-shape regressions cover these mechanisms; live token/time savings remain
unmeasured until the next real ticket. Native Windows Git Bash and Ubuntu/WSL2 are both required.

## Deterministic boundaries (0.38.0)

New lean invocations use schema 5: actual Claude Code tool exchanges supply full-ticket
captures; accepted worker IDs supply recording facts; scoped recording operations bind host
calls or run explicitly planned local hooks after journaling. New delta workers can reference
unchanged judgments instead of reauthoring a complete report. Existing schema 1–4 runs and
already-prepared contracts keep their protocols and budgets. See
[`references/boundaries.md`](references/boundaries.md) for commands, trust boundaries and
measurement. These mechanisms are regression-tested, not a claim of measured live savings.

## Efficient handoffs (0.37.0)

The lean architecture stays intact. New contracts use structured correction verdicts, preserve
resolved evidence before deltas, inherit unchanged named inputs, and carry independently reviewed
corrections at unchanged code/dependencies. New invocations require a full authoritative Notion
fetch receipt immediately before merge; this is host-captured evidence, not provider attestation
(`blocked` on the provider).

Knowledge, epic and ticket skills load operation-specific references. `next-task` selects from
the brief/live children before ticket-scoped knowledge retrieval. Recording deduplicates frozen
evidence, carries canonical accepted claims, declares independently recoverable writes, and uses
one outcome/validated-completion interface. No additional agent or review stage is introduced.
Existing invocations/packets retain their contracts. See [handoff design and measurement](references/handoffs.md).

## Lean workflow (0.36.1)

Patch 0.36.1 closes three recording/review gaps: provider inputs consume frozen evidence,
new review contracts enforce claims/caveats/triage audits, and stable child operations inherit
their parent's completion policy. Already-dispatched workers retain their original contract.
No additional review stage is introduced; live-ticket token/time savings remain unmeasured.

`next-task → ticket → implementation/validation → review-and-merge → shared record`.
`finalize` resumes that same sequence at its first incomplete stage. Superpowers/feature-dev
are optional explicit `--flow` overrides, not prerequisites of the default path. Older runs
retain their runtime contract and legacy recovery path; their budgets are not reset.

New workers receive a generated result contract; invalid output is repaired before publication.
Questions use durable runtime state, one waiter owns each worker, and safe yield permits host
delivery. Current-head verification receipts are shared across validation, review and closeout.
The reviewer returns both code-quality and whole-ticket requirement evidence; scoped deltas
reuse unaffected evidence. Two full/two delta attempts are enforced; unresolved mandatory work
still blocks merge. The lean external-review default is three rounds (explicit reviewsCap wins).

Recording uses immutable payloads and a journal: confirmed work skips, uncertain writes reconcile
before retry, and malformed reports never re-execute provider operations. Follow-up creation
instructions load only when filing/recovery requires them. No disposable client project is needed
to update; actual speed/token improvement must be measured on real tickets, not inferred from
instruction size or unit tests. See [runtime](references/runtime.md) and
[recording](references/record.md).

The historical release notes and dual-flow details below describe the opt-in legacy paths where
they differ from this default. Legacy instruction contracts remain regression-tested separately;
the lean path has behavioral lifecycle, reuse, recording and command-routing tests.

## Reliability fixes (0.34.0)

Commands check live build-flow skills, with read-only diagnostics for stale setup flags
and disabled local plugins; init does not reinstall over intentional disablement.
Runtime state locks release on process death without stale-PID guessing, while live
holders remain protected. Terminal-sweep corrections receive an explicit hash-bound
code verdict from the already-budgeted independent completeness worker, including on
its first pass. No extra agent round or weaker requirement gate is introduced.
See [dependency diagnostics](references/dependencies.md) and
[runtime protocol and legacy lock recovery](references/runtime.md).

## Review convergence and scoped handoffs (0.33.0)

Review-and-merge stabilizes the base, version and mutating pre-merge checks before
completeness. Bounded independent correction reviews can reuse applicable evidence
after a small fix or late rebase; they still return every requirement verdict and
must stop for broad changes, stale inputs, or unresolved mandatory work. The runtime
limits correction attempts to two; the workflow retains its two-full-pass bound.

Workers receive a file-based context packet with frozen inputs instead of another
inline inventory. Implementation and whole-branch reviewers from both build flows
participate in the durable lifecycle; pending delivery cannot silently drop a reviewer.
`next-task` hands off artifact references and preserves resumed ticket state.

These are generic notion-dev changes, not client-project patches. Python 3.8+, the
configured interpreter, explicit Git Bash resolution on Windows, and Bash on Ubuntu
WSL2 remain supported. No check of external or live state, and no check following a
code or environment change, is served from a cache; a deterministic check may reuse
its successful output only on unchanged inputs. Actual token/time savings require a
measured Claude Code canary; this release does not claim the <200K target has already
been achieved. See [rollout and measurement](references/convergence.md).

## Runtime reliability and evidence (0.32.0)

Ticket/finalize runs now retain per-invocation lifecycle state and timing under
`.claude/notion-dev/runtime/`. Background agents publish durable results; pending
delivery is not failure, and cancellation must be confirmed before recovery.
Mandatory prerequisites outside AC also gate readiness. Merge requires a consumed,
current independent completeness result with resolved evidence for every mandatory
requirement; degraded or stale checks stop with the work preserved.

The standard-library helpers `scripts/runtime.py` and `scripts/telemetry.py` use
`knowledge.python`. Verification records real exit status, a log hash and a toolchain
signature, and indexes every receipt with why it is or is not reusable now; reuse is an
explicit `--reuse`, never a silent cache, and a moved revision, an edited log or a
failure is always rerun. Evidence is recorded per requirement as each review result is
consumed, with the source files each receipt depends on, so a second review round reuses
what still applies instead of re-deriving it — the merge gate still requires every
mandatory requirement resolved with intact evidence. Raw JSONL telemetry separates cache
reads, cache creation, uncached input, output and peak context, correlates each child
log to its worker's role, and reports missing and unattributable logs as unknown rather
than absorbing them. See
[the runtime protocol](references/runtime.md). This changes notion-dev's gates;
quick-dev's independent workflow is not opted into this protocol.

## Prerequisites

- **`superpowers` and `feature-dev` plugins** — optional for explicit legacy build flows only. The default lean flow does not need them; init does not auto-install them unless you select legacy setup.
- **`gh` CLI, authenticated** (`gh auth login`) — **required**. The review loop in `/notion-dev:ticket` and `/notion-dev:finalize` uses `gh` for paginated comment reads and GraphQL review-thread resolution, which the GitHub MCP cannot perform.
- **`jq` on `PATH`** — **required**. The same review loop parses `gh api` JSON responses with it (`gh api`'s own `--jq` flag does not substitute for the standalone binary). Not preinstalled on Windows: `winget install jqlang.jq` (or `choco install jq` / `scoop install jq`). Usually already present on macOS/Linux; if not, `brew install jq` / `apt install jq`.
- **`iwe` ≥ 0.19 on `PATH`** — **required**. `notion-dev:knowledge` uses it for budgeted search-plus-graph retrieval and dedupe over the knowledge bundle. Two install routes: `cargo install iwe --root ~/.local` (works wherever Rust does; required on hosts whose GLIBC is older than 2.39, which includes Ubuntu 22.04 under WSL); or `brew install iwe` / `npm i -g @iwe-org/iwe` where the prebuilt binary runs. On Windows `npm i -g @iwe-org/iwe` (win32-x64 binary).
- **Python 3.8+** — **required** for `scripts/knowledge.py`, the bundle's shape validator, migrator, and touched-concept finder. Standard library only; no `pip` step. `/notion-dev:init` records which interpreter it found (`python3`, `python`, or `py -3`) as `knowledge.python`; every command uses that.
- **Git for Windows** — required on Windows. Claude Code's Bash tool runs through Git Bash there, and the commands use its `dirname`, `mktemp`, `od`, `tr`, `tar` and `/dev/urandom`. WSL 2 Ubuntu needs nothing extra.
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
# → worktree, cohesive implementation, verify, PR,
#   external + combined independent review, merge, journaled record and cleanup

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
| `/notion-dev:ticket <ticket-id>` | Full implementation cycle, end to end through merge: intake/readiness → worktree → cohesive implementation → verify → PR → external + combined independent review → merge → journaled record. Also accepts the Notion page id/URL. |
| `/notion-dev:finalize <pr-number>` | Standalone resume/review entry point for an already-open ticket PR: review loop (Codex or local fallback) → merge → update ticket → clean up → post-merge hooks. |
| `/notion-dev:next-task <epic-id>` | Drive an epic from its markdown brief: read `<knowledge.dir>/epic/<KEY>-<n>-<slug>.md`, pick the recommended next unblocked ticket, run `/notion-dev:ticket` on it, re-read, repeat. Flags: `--depth all|N` (default 1), `--non-interactive`, `--flow=…`. Bootstraps the brief on first use — from an existing `docs/*<KEY>-<n>*.md` plan when one exists (which it then removes), else from the Notion epic. So it can chain into `/notion-dev:ticket`, that command is no longer marked user-only in its frontmatter; its body carries an invocation guard instead. |
| `/notion-dev:new-info <information>` | Route one new fact ("the customer deployed v1.4.2") to every epic brief it affects: judges each brief, shows the proposed diff per epic (Apply / Skip / Revise), commits it straight to the epic branch, appends a dated entry to the Notion epic's `Notes`, and comments on the tickets a cleared thread unblocked. Never edits a ticket's requirements. The same fact reaches the knowledge bundle through `capture --fact`. Flags: `--epic <id>` (repeatable), `--non-interactive`, `--pr` (land through one reviewed pull request instead). |
| `/notion-dev:knowledge capture <ticket-id> <merge-sha> \| migrate [--apply] \| curate` | Person-invoked knowledge-bundle maintenance. `capture` re-runs by hand the post-merge write a ticket run skipped or failed; `migrate` moves an existing client bundle onto the plugin's schema (prints the diff, `--apply` to write, then a removal checklist); `curate` walks near-duplicate concepts and supersedes the losers, one `AskUserQuestion` per cluster. Reading the bundle happens automatically inside `/notion-dev:ticket`, not through this command. |

`--non-interactive` means two things, not one: the run never **asks** you anything, and it never
**hands back**. It does not stop between phases to announce what it is about to do next, so one
invocation carries the work through to its final report or to one of the stop conditions the
command names.

**The second half is enforced by a `Stop` hook this plugin ships** (`hooks/stop-guard.sh`), not
by instructions alone. 0.28.1 shipped it as instructions and a run stopped mid-`Phase 8` anyway,
then quoted the rule it had just broken when asked why — ending a turn is the *absence* of an
action, so only the harness can gate it. The guard blocks the stop while the project has a live
`--non-interactive` run marker **that belongs to the stopping session**, and names the phase to
resume at. Ownership comes from a second hook: a `SessionStart` hook
(`hooks/session-env.sh`) publishes the session id as `NOTION_DEV_SESSION_ID`, the run stamps it
into its marker, and the guard matches the two. That hook also captures the primary checkout as
`NOTION_DEV_PRIMARY_ROOT`, because on the no-argument resume path the session is launched inside
the ticket worktree and Phase 9 deletes it mid-run — after which nothing derived from where the
session started can still find the markers. Both halves are needed — without the
`SessionStart` half every marker records an empty owner and the guard skips all of them.

It is bounded in both directions so it can never wedge a session: at most **3 blocks per marker per
session** — so up to six across a run that spends the cap in Phase 1 and again later, in two
disjoint windows, because the two marker shapes below count separately — and it ignores a marker more than **2 hours** stale — the same threshold
`/notion-dev:ticket` already uses, and for the same reason: a heartbeat is written *between*
units of work, never inside one, so the window has to exceed the longest single build task,
verify command or reviewer round. A shorter window looks safer and is not: a Phase 7 review loop
routinely runs past it, so the guard would go quiet at exactly the boundary it exists to cover.
An abandoned run still blocks nobody, because a marker can only ever block the session that
created it. It fails open on anything unexpected, and it blocks **only the session that
owns the run** — a second parallel ticket, or an interactive session in the same checkout, is
never refused its stop. It never fires on an interactive run at all, since those end a turn to
ask, which is correct; and it does not cover `/notion-dev:finalize`, which writes no run
marker.

**The whole of `/notion-dev:ticket` carries a marker, including Phase 1.** Two shapes do that
work. From Phase 2 on it is `runs/<KEY>-<id>.json`, written once the ticket id is known. Phase 1
cannot use that name — the id is not resolved until the ticket is fetched, and the argument may
be a page id, a UUID, a URL or a logical key — so the preconditions gate writes
`runs/preflight-<session>-<invocation>.json` instead — keyed by the session id, which is what
scopes the guard's counter, plus a per-invocation token, which is what stops a second ticket run
in the same session inheriting the first one's spent counter — and Phase 2.1 deletes it the
moment it writes the other. Every stop before that handover writes `state: stopped` into the
preflight marker first, which is what lets a documented hard abort — the epic guard, the
`held elsewhere` ownership check, the under-spec gate — actually stop. Before 0.30.0 the
preconditions gate, the fetch, knowledge retrieval, the resume protocol and the clarification
gate were all unguarded.

**In `/notion-dev:ticket` only**, a run that ends mid-phase anyway — past the guard's bounds, or
under it — is recorded as
`unexpected:run-ended-mid-phase` in the [runtime issue log](#runtime-issue-log) by the next
resume — the ending run cannot observe its own ending, so a resume is the only place that
condition is visible, and `/notion-dev:ticket` is the one command with a run marker and a resume
path to observe it from. The other commands get the rule and not the detection: a mid-phase end
there is visible only on screen.

Ticket titles are prefixed with their ticket ID — `[STO-67] Large-Wallet Stale-Index Incident`. The prefix is applied and stripped automatically; you never type it, and branch names are unaffected.

## Configuration

`.claude/notion-dev.config.json` is git-tracked and validated by `schema/notion-dev.config.schema.json`. Reference the schema via `$schema` for editor-level validation.

Key fields:

- `project.{key, name}` — ticket ID prefix (e.g. `STO`) and short project name (used in worktree naming).
- `ticketSystem` — the Notion ticket-database config: `databaseId` (required) plus optional property-name overrides and `statusMap` / `typeMap` / `staticProperties`. Assignee support adds `assigneeProperty` (the People column, default `"Assignee"`) and `defaultAssignee` (a user id, email, or display name; `""` means create-task prompts each run). `/notion-dev:init` sets both. Epic support adds `parentTaskProperty` (the self-referential Relation linking a ticket to its Epic container page, default `"Parent task"`), `epicMarkerProperty` (the Checkbox that marks a page as an Epic container, default `"Is Epic"` — the **sole** signal used to identify epics; carrying an `Epic` select value alone never makes a page a container), and `creationDateProperty` (default `"Creation Date"`, tolerating either a `Date` property the plugin writes at creation or a `Created time` property Notion auto-fills). All three are absence-tolerant, and each also tolerates a wrong live type by degrading exactly as it does for absence. `epicMarkerProperty` is stricter than a skipped write: when it is unusable — **absent, or present but not a Checkbox** — epics cannot be identified at all, so epic discovery and every epic-aware guard degrade to treating every page as "not an epic" rather than guess from shape, and no operation queries the property. `findEpics` likewise returns `null` when `Parent task` is unusable: epic containers need both columns, so discovery never reports a container that could not actually take children.
- `knowledge.dir` — directory for the knowledge bundle, whose root concept is the per-epic markdown brief (default `knowledge`). See "Knowledge bundle".
- `knowledge.retrieveBudget` — `--max-tokens` passed to `iwe retrieve` (integer ≥ 1000, default `8000`): the bundle's share of a run's context.
- `knowledge.warnBytes` — per-concept size above which `knowledge.py check` warns; never fails (default `8192`).
- `knowledge.extraTypes` — client-specific concept type directories `check` accepts beyond the canonical set (default `[]`, e.g. `["commitment", "node"]`).
- `knowledge.python` — the Python 3 interpreter every notion-dev command runs `scripts/knowledge.py` with (default `python3`). Written by `/notion-dev:init` from its probe: `python3`, `python`, or `py -3` on Windows, where `python3` does not resolve.
- `inputSources` — enabled source adapters: any of `"prompt"`, `"existing-ticket"`, `"notion-page"`.
- `git.{baseBranch, prTargetBranch, mergeStrategy, preMergeChecks, postMergeHooks}` — git-flow config; `preMergeChecks` runs as a merge gate inside the review loop (`notion-dev:review-and-merge`). `postMergeHooks` is set to `["notion-dev:knowledge"]` by `/notion-dev:init` (the knowledge-bundle capture hook); additional phase-2 hooks (e.g. `hotfix-sync`, `epic-progress-report`) will be appended to it.
- `dependencies.{superpowers, featureDev}` — optional setup-time hints written by `/notion-dev:init`. Only opt-in legacy flows require those current live skills; lean does not. Cached booleans are not availability checks; mismatches are diagnosed without changing enablement. See [dependency diagnostics](references/dependencies.md).
- `worktree.prefix` — template for worktree directory names. Tokens: `{name}`, `{key}`, `{id}`. Default: `"{name}-{key}-{id}"`. Worktrees are created at `<parent-of-repo>/<repo-name>-worktrees/<prefix>`; the `-worktrees` container is what cleanup's `rmdir` removes once the last worktree is gone.

  **Changed in 0.20.0.** Before that, worktrees were created directly under the repository's parent directory, with no container — which made cleanup's "remove the worktrees parent directory" step name the directory holding the primary checkout, so it could never succeed. If you have a worktree from an in-flight pre-0.20 run, it is at the old path (`<parent-of-repo>/<prefix>`); finish or remove it by hand (`git worktree remove <path>`), since `/notion-dev:finalize` now resolves the new location.
- `verify.steps[]` — ordered list of `{ name, cmd, retries }` commands run after implementation and before PR.
- `reviewer` — PR reviewer selection: `"codex"` (default) or `"copilot"`. Set during `/notion-dev:init`; can be changed by re-running that command.
- `ticketSystem.statusMap.{done, cancelled}` — **read-only** entries (defaults `"Done"` / `"Cancelled"`). Together with `implemented` they form the *resolved set*: the statuses that count as finished when deciding whether an Epic's children are all done and the Epic should close. No plugin command ever moves a ticket into these states — they exist purely so the Epic-close check understands your board. `/notion-dev:init` asks which of your live Status options belong in the set.
- `reviewsCap` — maximum external review rounds on the lean path; default **3**, with explicit positive values honored. Internal review has two full/two delta attempts per invocation, including failed attempts. No budget waives required work. Legacy workflows retain their documented 15-round default. Init and review never rewrite this key.

### Reviewer configuration

The PR review loop uses your configured reviewer. Both options fall back to the local fresh-agent review loop if unavailable.

- **Codex** (`"codex"`, the default): Requires the **Codex GitHub app** to be installed. Codex reviews are triggered by an `@codex review` comment on the PR.
- **Copilot** (`"copilot"`): Requires GitHub Copilot code review to be enabled on your repository or organization. Copilot reviews are requested via the REST API.

Projects upgraded from earlier versions of notion-dev (whose config predates the `reviewer` key) will be prompted to choose a reviewer the next time you run `/notion-dev:ticket` or `/notion-dev:finalize`; that choice applies to the current run only. To persist it, re-run `/notion-dev:init` — the review loop never writes the config itself.

Secrets never belong in this file; MCP auth handles credentials.

External review waits at most 15 minutes per lean round before authorized local fallback;
late feedback is still checked before merge. Required approvals are never waived. The same
combined independent code/completeness seat performs fallback, without another overlapping
reviewer. Edit `.claude/notion-dev.config.json` only when you want an explicit `reviewsCap`.

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
- **Most review findings never become tickets.** When a review turns up work the ticket did not plan for, the flow triages it: `absorb` (do it now, in this PR — the default), `file` (its own ticket, only for genuinely separate work meeting the documented filing criteria), or `drop` (recorded with a rationale, never built). Absorbed work is gated: `/notion-dev:ticket` will not merge while an `absorb` item is outstanding. Only `file` items become real tickets, and they land under the same Epic.
- **A ticket closes against what it said it would do.** The `## Acceptance Criteria` you wrote are checked at merge, not assumed: each needs independent evidence, resolved against current source/test artifacts. Unmet mandatory criteria block merge; `file` or `drop` never waive them. Verified met criteria get their Notion to-do boxes ticked; unknown/unmet ones remain unticked. Reducing criteria requires an explicit authorized scope change. The same completeness gate reports any claim in the change that names something absent, and any stated caveat carrying no triage label.
- **`/notion-dev:ticket` refuses to implement an Epic** and lists its children instead — a container is not implementable work.
- **`/notion-dev:ticket` reads its Epic's brief before planning.** A starting ticket reads the brief at `<knowledge.dir>/epic/<KEY>-<n>-<slug>.md` — the epic's root concept in the knowledge bundle — via the `notion-dev:knowledge` skill's `retrieve`, once per run: why the epic exists, where it stands, what is waiting on whom, what is next, and any linked concepts iwe expands in. This is context: background for its reasoning, never requirements; the ticket body stays the single source of truth for what to build. The Notion epic page is written on every resolution but no longer read. See "Knowledge bundle" below.

**`## Next` is kept true by the plugin, not by hand.** Its three lists partition the epic's
unresolved children: the numbered list (item 1 is the next ticket a session can start), an
`In progress:` line (claimed tickets, with the date each was claimed), and `Blocked:` (held by an
open thread). A ticket run marks the brief when it starts (`docs(epic): … start`), when it stops
with a worktree left behind (`… stop`, which also adds an open-thread bullet naming the worktree
and how to resume), and when it resolves (`… after`); `/notion-dev:create-task` marks a new child
(`… create`); and any read that finds the brief apart from Notion repairs it on the next write
(`… refresh`). Nothing polls Notion.

**One writer at a time on the primary checkout.** Every section that commits from the primary
checkout takes a directory lock at `.claude/notion-dev/locks/primary/` (self-ignored). A stuck
lock older than 60 minutes is broken and reported. Run reports list any wait.

**Running two sessions on one epic.** Open a second terminal in the same checkout and run
`/notion-dev:next-task <epic> --depth N` in each. Each session claims its ticket by creating
the worktree, records a run marker under `.claude/notion-dev/runs/`, and moves the ticket to
the brief's `In progress:` line; the other session's next read excludes it. A ticket already
`In Progress` with no worktree here is reported as held elsewhere; a worktree whose marker says
`running` with a heartbeat under two hours is held by a live session; `stopped` or stale
markers resume. Two sessions merging into the same base: the second is rebased once at the
merge gate when it fell behind, its version is re-checked against the base and re-bumped when
equal (two minor bumps land as consecutive minors), and a manifest-version conflict resolves
itself. A worktree carried over from 0.25.0 has no marker and resumes as before. A ticket left
`In Progress` with no worktree here now aborts in non-interactive mode (`held elsewhere`)
instead of proceeding. Same machine only.

An Epic page carries four sections:

| Section | Content |
|---|---|
| `## Overview` | What the initiative or incident is. Written once, at creation. |
| `## Tasks` | Each child with its status: `- [x] [STO-67] Fix stale index — Implemented`. **Refreshed only when a child resolves**, so between resolutions it lags — the live view is Notion's `Parent task` relation column. |
| `## Resolution Log` | Append-only history. Every time a child resolves, a divider and a dated entry are added with what was done, follow-ups filed and dropped, how many tasks remain, and what's next. |
| `## Notes` | Append-only, written by `/notion-dev:new-info`: one dated entry per fact routed to this epic — the fact, the brief it changed, what it cleared and what it unblocked. |

When the last unresolved child resolves and no filing has failed, the Epic's own status moves to `Implemented`. A follow-up you decline at the filing prompt is recorded as a **drop** — a decision, which closes work rather than blocking the Epic indefinitely.

### Knowledge bundle

Every project keeps one shared knowledge bundle in the repo, rooted at `knowledge.dir` (default `knowledge`), owned by the `notion-dev:knowledge` skill and validated by `scripts/knowledge.py` and `iwe`. It holds OKF v0.2 concepts — one fact per markdown file, frontmatter validated against a shipped schema (`type`, `title`, `description`, `status`, `sources`, and more) — under canonical type directories (`ticket/`, `decision/`, `gotcha/`, `component/`, `spec/`, `domain/`, `release/`, plus any client directories declared in `knowledge.extraTypes`), an `index.md` catalog, and an append-only `log.md`. `scripts/knowledge.py` also carries the `next` subcommand (renders a brief's `## Next` region from live state) and `lock` (takes, releases, and reports on the primary-checkout lock).

**The epic brief is the epic's root concept**, at `<knowledge.dir>/epic/<KEY>-<n>-<slug>.md`. It carries the same six sections as before — `Why`, `Goal`, `Where we stand`, `Open threads`, `Decisions & constraints`, `Next` — and a soft budget of 120 lines, plus OKF frontmatter; bullets under `Decisions & constraints` and `Open threads` link to other concepts instead of restating them.

- **Two writers, one commit path.** Every resolution — `/notion-dev:ticket` and `/notion-dev:finalize` alike — writes the bundle twice, under the same git assertions and straight to the base branch. Phase 10's `notion-dev:epic-doc` `record` rewrites the **brief** and its catalog bullet (`docs(epic): <KEY>-<n> after <ticket key>`); the post-merge hook's `notion-dev:knowledge` `capture` writes the **concepts** a merge evidenced, plus the index and log entries for them (`docs(knowledge): capture <KEY>-<n>`). `/notion-dev:knowledge capture <ticket-id> <merge-sha>` re-runs the second by hand when the hook was skipped or failed.
- **Valid until superseded.** No `stale_after`, no reconciled clock, no scheduled sweep. A concept stays `stable` until a later fact deprecates it (`status: deprecated`, `superseded_by: <new path>`); knowledge changes only when new information arrives — a merge (`capture`) or a fact (`/notion-dev:knowledge capture --fact`, driven by `/notion-dev:new-info`).
- **One retrieve per run.** `/notion-dev:ticket` reads the bundle exactly once, via the `notion-dev:knowledge` skill's `retrieve(<epic-id>, <ticket-title>?, <ticket-id>?)`: it assembles the epic's root concept plus everything `iwe retrieve --expand-references` pulls in, budgeted by `knowledge.retrieveBudget`, and returns `KNOWLEDGE_CONTEXT` for the run — background for the run's reasoning, never requirements. `iwe` missing or a failed retrieve degrades to the brief alone (`partial:knowledge-retrieve`); the run still proceeds.
- **The hook.** `git.postMergeHooks: ["notion-dev:knowledge"]` (set by `/notion-dev:init`) is what runs `capture` after every merge. `check` gates every write — a failing check means nothing is committed.
- **New information.** `/notion-dev:new-info "<fact>"` routes a fact learned between resolutions — a deployment, an approval, a customer decision — to every brief it affects: it clears the open thread the fact satisfies, adds or replaces the constraint, recomputes `Next`, and shows you the diff per epic before committing it to the epic branch (`--non-interactive` applies; `--pr` lands through one reviewed pull request). The Notion epic gets a dated `Notes` entry; each ticket the fact unblocked gets a comment. Tickets are never edited — a requirement the fact contradicts is flagged for you. The same fact reaches the knowledge bundle through `capture --fact`.
- **Existing clients migrate.** `/notion-dev:knowledge migrate [--apply]` moves a client's own bundle implementation onto this schema: without `--apply` it prints the complete diff and writes nothing; with `--apply` it rewrites the bundle, updates the config, and prints a removal checklist for the client's now-redundant code. See `docs/superpowers/specs/2026-09-14-knowledge-bundle-design.md` §13 for the full per-client removal inventory.

> **Upgrading to `0.13.0`: skim epics that close soon after the upgrade.**
> Before this version, declining a follow-up at the filing prompt recorded a `SKIPPED` entry that blocked the Epic's closure **permanently** — one decline and the Epic could never reach `Implemented`. That is the bug this release fixes: a decline is now a recorded **drop**, and a drop does not block.
>
> The consequence on existing data: an Epic that was stuck behind such a decline will close on its next resolution — including one where the declined item was *genuine outstanding work* someone meant to come back to. Nothing is lost, but nothing is tracked either: that work exists only as a line in the Epic's `## Resolution Log`, never as a ticket.
>
> Both the new `**Follow-ups dropped**` wording and the pre-`0.13.0` `**Follow-ups skipped**` wording are parsed, so older Epics recover normally. To catch anything worth reviving, read the follow-up lines in any Epic that closes shortly after you upgrade, and file what still matters.

**A note on Notion Sub-items.** `/notion-dev:init` can create the `Parent task` relation for you, but the Notion API cannot enable Notion's native *Sub-items* feature — so an API-created relation renders as an ordinary relation column rather than nested sub-rows. Grouping and every plugin behavior work identically either way. For the native nested rendering, enable Sub-items in the Notion UI **before** running `/notion-dev:init`, and init will bind to it instead of creating its own.

## Input sources

| Source | Ref format | Notes |
|---|---|---|
| `prompt` | free text | Default; used when no source prefix is given. |
| `existing-ticket` | ticket id or `PREFIX-n` | Fetches the configured ticket system; useful for elaborating thin tickets. |
| `notion-page` | Notion URL or page id | Read any Notion page as seed input. Requires Notion MCP. |

Add a new source by creating `skills/input-source/<name>.md` matching the output shape in `skills/input-source/SKILL.md`.

## Phase-2 seams

`git.postMergeHooks` already carries one hook (`notion-dev:knowledge`, the knowledge-bundle capture). Phase 2 will ship additional skills and commands that append to it:

- `git.postMergeHooks` — skills invoked after merging, run by `/notion-dev:ticket` and `/notion-dev:finalize` as the last step of their cleanup phase, with the primary checkout asserted to be on a freshly pulled base branch. The ticket worktree is already removed by then, so a hook reads the merge from git history, not from a working tree.
- Additional commands planned: `prepare-release`, `hotfix`, `hotfix-sync`, `release-fix`, `resume-merges`, `prod-deploy`.

No v1 refactor required to adopt phase 2.

## Layout

```
.
├── .claude-plugin/
│   ├── plugin.json           # plugin manifest
│   └── marketplace.json      # self-contained single-plugin marketplace
├── commands/                 # slash commands (init, create-task, ticket, finalize, next-task, new-info, knowledge)
├── references/               # command reference files — deliberately NOT under commands/, where every .md registers as a slash command
│   └── record.md             # shared inline journaled recording for ticket/finalize
├── skills/
│   ├── ticket-system/        # Notion ticket operations: SKILL.md dispatcher + references/ (config, read-ops, write-ops, styling, create-ops)
│   ├── input-source/         # input adapters (SKILL.md + prompt.md + existing-ticket.md + notion-page.md)
│   ├── ticket-interviewer/   # depth-calibrated requirements interview (used by create-task)
│   ├── task-breakdown/       # single-vs-mission split analysis (used by create-task)
│   ├── flow-triage/          # legacy build-flow chooser, scorecard and ledger
│   ├── review-and-merge/     # PR review loop: Codex rounds, local fallback, merge gates
│   ├── local-code-review/    # legacy fallback reviewer contract
│   ├── plan-review/          # pre-implementation plan review: fresh agent vs. the codebase (used by ticket)
│   ├── epic-update/          # records a resolved ticket against its epic (used by ticket, finalize)
│   ├── epic-doc/             # per-epic markdown brief: rewritten at resolution, noted by new-info (used by ticket, finalize, next-task, new-info)
│   ├── knowledge/            # the OKF knowledge bundle: retrieve, capture, curate, migrate (used by ticket, finalize, next-task, new-info, knowledge)
│   ├── session-closeout/     # zero-tails gate before any final report (used by ticket, finalize)
│   └── issue-log/            # durable, redacted runtime deviation log (used by all four commands, ticket-system)
├── scripts/
│   └── knowledge.py          # bundle shape validator, migrator, and touched-concept finder (used by the knowledge skill)
├── schema/
│   └── notion-dev.config.schema.json
├── LICENSE
└── README.md
```

## Credits

`skills/flow-triage/`, `skills/review-and-merge/`, `skills/local-code-review/`, `skills/plan-review/`, and `skills/session-closeout/` are vendored and adapted from the `quick-dev` plugin. `local-code-review` was itself originally adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills/blob/main/skills/code-review-and-quality/SKILL.md) `code-review-and-quality` (MIT License, © 2025 Addy Osmani).

## License

MIT
