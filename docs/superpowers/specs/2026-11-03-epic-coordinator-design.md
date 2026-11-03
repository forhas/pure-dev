# Epic coordinator — fresh-context ticket sessions, judged between tickets

Status: approved 2026-11-03; facts 12–13 added from the Task 1 probe. Part A (serial) is planned and built first; Part B (parallel)
is planned only after Part A has been field-tested on the client projects.

## Intent

Today the user drives an epic by hand: run `/notion-dev:next-task` in a session, read the
ticket's outcome, close or record every open item, then start the next ticket — in a fresh
session, because `--depth N` in one session exhausts the context window. The coordinator
replaces that person "more or less". It is a Claude Code session that launches every ticket in
its **own fresh background session** and, between tickets, applies the user's standard:
**every ticket ships functional, bug-free, well-tested and well-written, with zero tails** — every
open item is either closed before the next ticket or recorded (knowledge bundle, follow-up
ticket), never left in a report.

## Goals, non-goals, anti-goals

Goals
- One command drives an epic to completion, one fresh context window per ticket.
- The user can watch any ticket session live (`claude attach <id>`) and step in.
- Between tickets, an AI judgment — not a script — decides: next ticket, close an item first,
  or ask the user.
- Works unchanged from WSL 2 Ubuntu and from Windows-native Claude Code (Git Bash).
- Part B later: several compatible tickets at once, merged one at a time.

Non-goals
- A second code review by the coordinator. The ticket's existing Codex + completeness review
  is the review (user decision).
- Running a ticket inside a subagent of the coordinator (see Verified facts 1).
- Cross-machine coordination.

Anti-goals — a failure even if it "works"
- The coordinator writing code, resolving conflicts or editing the primary checkout itself.
- Counting a ticket done on a launch acknowledgement, a merged PR alone, or a report that
  merely *says* resolved without the evidence checks in §A5.
- Silently escalating permissions (never passes `--dangerously-skip-permissions` or
  `bypassPermissions` to a ticket session).
- Billing ticket sessions to an API key when the user expected their subscription.
- A coordinator that ends its turn while a ticket session is still working, with nobody to
  resume it.

## Verified facts this design rests on

Measured 2026-11-03 on Claude Code 2.1.317, WSL 2 Ubuntu, unless marked.

1. **A ticket run cannot be a subagent.** `capture-ticket` and user-approval capture read the
   session's main transcript and reject `isSidechain` rows (`scripts/host_capture.py`); run
   ownership and the Stop guard key on the host session ID, which subagents share with their
   parent; `EnterWorktree` moves the whole session.
2. **The model cannot run `/compact`**, and no hook can trigger it
   ([slash-commands](https://code.claude.com/docs/en/slash-commands.md): "Other built-in
   commands such as `/compact` are not" available through the Skill tool;
   [hooks](https://code.claude.com/docs/en/hooks.md): PreCompact can only block, PostCompact
   "can't affect the compaction result"). A fresh context per ticket therefore needs a new
   session.
3. **`claude --bg "<prompt>"` starts a full background session** that runs a plugin command
   marked `disable-model-invocation: true` (probe: a gated command replied `GATED-RAN-t3`).
   `claude -p` does too, but is not used (fact 7).
4. **`claude agents --json --all` is the documented machine-readable state**
   ([agent-view](https://code.claude.com/docs/en/agent-view.md)). Observed entry:
   `{"id": "9bf0bf6f", "sessionId": "9bf0bf6f-1043-…", "kind": "background", "status": "busy|idle",
   "state": "working|done"}`. The short id is the UUID's prefix. Documented states: `working`,
   `blocked` (waiting on the user: permission prompt, dialog), `done` (turn finished, idle),
   `failed`, `stopped`. A `done` session stays alive ~1 hour unattached, then its process stops;
   the transcript remains and `claude --bg --resume <id>` continues it.
5. **Hooks run in background sessions.** SessionStart fired with `CLAUDE_ENV_FILE` present
   (so `NOTION_DEV_SESSION_ID`/`NOTION_DEV_TRANSCRIPT` are published); Stop fired with
   `session_id` equal to the agents-list `sessionId` and a `transcript_path`. The
   `--non-interactive` stop guard therefore protects ticket sessions.
6. **A background session starts like `claude` in that directory**: project settings, plugins,
   permission mode. A permission prompt puts it in `blocked`; only attaching answers it.
   `--bg` refuses an untrusted folder (client repos are already trusted).
7. **Auth.** `ANTHROPIC_API_KEY` is set in the user's WSL shell. `claude -p` warned the key
   "takes precedence over your claude.ai login" (docs: in `-p` "the key is always used when
   present"); the `--bg` session's status line showed `Claude Max`. Background sessions use the
   supervisor's stored credentials.
8. **Native Windows: verified (G1, 2026-11-03).** The probe passed 8 of 8 from Git Bash on the
   user's machine (Claude Code 2.1.306, npm install whose `claude.cmd` forwards to a bundled
   `bin/claude.exe`, which the coordinator runs directly). Two Windows traps it surfaced: Windows
   Python finds a bare `claude` only as a real `.exe`, and Git Bash rewrites a native program's
   arguments that begin with `/` into paths, so a `/plugin:command` prompt must be launched from
   Python, as the coordinator does, never from bash.
9. **Finding — merge-gate drift.** quick-dev's review-and-merge rebases a PR at the merge gate
   when the base moved (with version re-bump); notion-dev 0.26.0 (#47) had the same. The lean
   rewrite (0.36.0, #72) reduced it to "Base movement triggers safe stabilization", while
   `plugins/notion-dev/README.md` (the parallel-sessions paragraph) still promises the rebase.
   Part B depends on the explicit procedure; see §B4.
10. **Resuming a background session keeps its identity only once it is off the list.**
    `claude --bg --resume <sessionId> "<prompt>"` on a session still listed by `claude agents`
    (even `done` and stopped) starts a **copy with a new session ID** (SessionStart
    `source: fork`). After `claude stop <id>` and `claude rm <id>`, the same command continues
    the session **under the same ID** (`source: resume`; the turn ran). Run ownership is keyed on
    that ID, so only stop → rm → resume hands a run back to its owner.
11. **A deliberate yield shows as `working`, and wakes by itself.** A background session that
    launched a background worker and ended its turn stayed `working`/`busy` for the worker's
    whole run, woke on its completion notification, replied, and only then read `done`.
    So `done` with a `running` marker is a genuine hand-back, not a yield.
12. **`state` does not settle for a session started with a slash command; `status` does.**
    (Measured by `scripts/analysis/probe-background-sessions.sh`, Task 1 of the Part A plan.)
    A `claude --bg "/plugin:command …"` session whose turn has ended reads `state: working`,
    `status: idle` indefinitely; a plain-prompt session reads `done`/`idle`. `status` is `busy`
    for the whole turn **including a yield on a background worker** (fact 11 re-measured on a
    slash-command session: busy for the worker's 60 s, then idle after the wake). So the settle
    signal is `status: idle` (or a terminal `state`), never `state: done` alone. Entries can
    also lack `status`/`pid` for the first seconds after launch, and the host's own interactive
    session is listed without an `id`. A session at a permission prompt reads `state: blocked`,
    `status: waiting`, `waitingFor: "permission prompt"` (measured on a slash-command session).
13. **`claude stop` returns before the session's process exits** (the supervisor logs it
    `settled (killed)` up to ~1 s later). A `--resume` inside that window forks (fact 10)
    even after `claude rm` succeeded — reproduced four times out of four on slash-command
    sessions. Resuming under the same ID therefore needs: stop → wait until the entry's `pid`
    has exited → rm → resume, and a check that the printed id is the original.

## Decisions

| # | decision | by |
|---|---|---|
| 1 | New command; `ticket` behaviour unchanged except the small additions in §A2 | user |
| 2 | Two modes: `--serial` (default) and `--parallel` | user |
| 3 | Serial launches `/notion-dev:next-task <epic>` in a fresh background session per ticket | user |
| 4 | No coordinator code review; Codex + completeness is enough | user |
| 5 | `next-task` loses `--depth`; it always resolves one ticket | user |
| 6 | Parallel merges via a merge queue (policy §B4), not a sprint branch | user |
| 7 | Two plans: Part A now; Part B after field-testing A | user |
| 8 | Launch vehicle `claude --bg`, never `claude -p` | my call (facts 3, 7) |
| 9 | Command name `/notion-dev:run-epic` | my call |
| 10 | Every launched command persists its final report to a file keyed by session ID | my call (§A2) |
| 11 | Closing an item = a session running an existing command, never coordinator edits | my call |
| 12 | An item about a ticket's own run is fixed by resuming **that ticket's session** (fact 10), which owns the run and holds its context; a fresh session only for a different ticket | my call |
| 13 | Coordinator exclusivity uses its own marker file, never `knowledge.py lock` (that is one shared primary lock, stale after an hour) | my call |
| 14 | `close` / `rescope` from epic-goal end the run with the recommendation and the exact command | my call |
| 15 | Windows-independent work proceeds before G1; G1 gates the merge | my call |
| 16 | Approvals: the coordinator asks the user in its own session and relays the answer into the ticket's session (§A6a) | user |
| 17 | Facts handed off for confirmation: the coordinator asks the user as each appears and, on a yes, launches `new-info` (§A6b) — a change to the 0.50.0 rule that `new-info` is only user-started | user |

## Part A — serial coordinator

### A1. Command surface

```
/notion-dev:run-epic <epic-id> [--serial] [--non-interactive] [| guidance]
```

- `--serial` is the default. In Part A `--parallel` is rejected with "not available yet";
  unknown flags are rejected before any launch.
- Runs in the **primary checkout**, never enters a worktree, never edits tracked files.
- Interactive by default: escalations ask the user in this session. `--non-interactive`: an
  escalation stops the epic run with the cause and the exact resume command.
- `| guidance` is passed through to each `next-task` launch.
- Preflight reuses `references/lean-intake.md`'s probes (config, interpreter, `gh auth`, `jq`)
  plus: `claude` on PATH, `claude agents --json` parses, and the epic is an epic (same check as
  `next-task`).
- One coordinator per epic per machine: its own marker in the coordinator state directory
  (decision 13; never the shared `knowledge.py lock`, which every ticket session needs and
  which goes stale after an hour); a second invocation reports the live one and stops.

### A2. Changes to existing commands

- **`next-task`**: remove `--depth` and the "Delegate and repeat" loop; it selects and resolves
  exactly one ticket. `--depth` given → reject with a pointer to `run-epic`. `argument-hint`,
  README and harnesses follow.
- **`next-task`, `ticket`, `finalize`**: as the last step of every outcome — resolved, stopped,
  nothing selected, epic complete, goal met — also write the finished report verbatim to
  `.claude/notion-dev/reports/<NOTION_DEV_SESSION_ID>.md` in the primary (overwritten by a later
  turn of the same session). One sentence each; nothing else changes. The coordinator reads this
  file instead of parsing transcripts (decision 10), including launches that never reach a
  ticket's preflight.
- **Authorization lines**: `ticket.md` ("Invoke only at the user's request or through an
  authorized next-task run") and `finalize.md` gain "or a `run-epic` run".

### A3. One ticket iteration

1. **Launch** from the primary checkout:
   `claude --bg "/notion-dev:next-task <epic> --non-interactive [| guidance]"`.
   Parse the printed short id; resolve `sessionId` from `claude agents --json --all`. Record the
   launch in coordinator state (§A7) **before** waiting.
2. **Wait** until the session settles: `status: idle` or a terminal `state` (fact 12). Through a helper (e.g.
   `workflow.py session-wait --id <short> --seconds <n>`) that polls `claude agents --json --all`
   and returns the entry. The coordinator must not end its turn while a session is `working`
   (anti-goal); how it stays alive across hours is left to the builder (bounded foreground
   waits, or the host's background-task notification), but it must follow the existing
   one-waiter rule in `workflow.py guide --stage dispatch`.
3. **Locate the outcome**: `.claude/notion-dev/reports/<sessionId>.md`, plus the run marker in
   `.claude/notion-dev/runs/` whose `claude_session` equals the `sessionId` (absent when
   `next-task` selected nothing). A missing report on a `done` session is a hand-back (§A4).
4. **Judge** (§A5) and **act** (§A6).
5. **Retire** the session after the judgment: `claude stop <id>`. Keep it listed (no `rm`) until
   the epic run ends, so the user can still `claude --resume` it; `rm` at the end.

### A4. Session states

| state | meaning | coordinator action |
|---|---|---|
| `busy` | running, including a yield (facts 11–12) | keep waiting |
| settled + marker `complete` | ticket finished | judge §A5 |
| settled + marker `running`, or no report | the session handed back mid-run (fact 11) | resume the **same** session (stop → process exit → rm → `claude --bg --resume <sessionId> "<instruction>"`, facts 10, 13); counts toward the §A6 bound |
| settled + marker `stopped` | ticket stopped with a cause | §A6 failure handling |
| `blocked` | permission prompt / dialog | tell the user `claude attach <id>`; keep waiting (interactive) or stop (non-interactive) |
| `failed` / `stopped` | process ended | resume the same session, as for a hand-back |

### A5. The coordinator's standard — acceptance evidence per ticket

Each item is checked from a source, not from the report's own claims:

1. Marker `complete`; `final-report.md` carries `OUTCOME: resolved` and a CLOSEOUT block.
2. PR `MERGED` (`gh pr view`); the merge commit's checks on the base are green (or none
   configured), waited for with a bound.
3. Notion ticket status is the configured done status (ticket-system read).
4. Every `tracked:` line resolves to an existing, open item at its **computed** destination
   (`workflow.py followup-body` routes meta/non-goal follow-ups to the backlog; the coordinator
   checks existence, never the destination choice); every `blocked:` line names an **external**
   cause and an unblocker (session-closeout's definition). An internal-cause `blocked:` is an
   open item.
5. Recording outcomes: knowledge-delta, epic-brief, NEW-INFO handoffs — any failed or
   `unknown` outcome is an open item.
6. Workspace: the ticket's worktree and local branch are gone; the primary is on its base branch
   and as clean as its preflight snapshot.

All pass → next iteration. Otherwise each open item goes through §A6.

### A6. Acting on open items and failures

The coordinator decides per item and never does the work itself (decision 11). An item about a
ticket's own run goes back to **that ticket's session** — resumed under its own ID (fact 10), so
it still owns the marker and runtime and needs no takeover — with a specific instruction
(decision 12). Only a different ticket gets a fresh session.

| open item | default action |
|---|---|
| recording failed or unknown (Notion, knowledge, brief) | resume the ticket's session: "run `/notion-dev:finalize <pr>` recording recovery" |
| a tail with no record, or an internal-cause `blocked:` | resume the ticket's session: "resolve or record <item> per session-closeout" — it files through its own follow-up path |
| ticket stopped: transient (provider outage, flake, timeout) | resume the ticket's session to continue from its runtime |
| a tracked follow-up that is a defect in the just-shipped work, or blocks the next tickets | fresh session `/notion-dev:ticket <followup-key> --non-interactive` before the next `next-task` |
| any other tracked follow-up | leave it to its normal order; it is recorded |
| main CI red on the merge commit | stop and escalate; never launch the next ticket on a red base |
| ticket stopped: needs an approval phrase | ask the user; relay per §A6a |
| ticket stopped: missing credential or decision | escalate to the user; relay a decision as an instruction on the resumed session |
| a fact handed off "awaiting the user's confirmation" | ask the user; on a yes, §A6b; it does not hold up the next ticket while unanswered |
| epic-goal `close` or `rescope` | end the run; report the recommendation and the exact next command (decision 14) |

### A6a. Relaying an approval (decision 16)

- Interactive coordinator only. `--non-interactive` never relays: it stops with the cause and
  the session to attach to.
- The coordinator shows the user the exact request (what is being approved, the phrase, the
  ticket and session) and asks. It relays **only the user's explicit yes**, as the exact phrase,
  by resuming the ticket's own session (fact 10) with the phrase as the prompt — so it lands as a
  user message in the owning session, which is what approval capture requires. It never
  composes or sends an approval the user did not give in this turn.
- It relays immediately: the approval's time window is bound to the request. An expired window
  goes back to the ticket for a new request; never a reworded phrase.
- The coordinator state records the user's message (transcript row id) behind every relay, so
  the provenance "the user approved via the coordinator" stays auditable.
- Docs: `runtime.md`/review-accounting text that says approval must come from the user gains the
  relay as a sanctioned path; the capture code is unchanged.

### A6b. Confirming handed-off facts (decision 17)

- Interactive coordinator only; `--non-interactive` lists them in the final report with the
  command to run.
- As a report names a fact "awaiting the user's confirmation", the coordinator shows it with its
  source and asks. On a yes it launches a fresh background session running that fact's `run:`
  line with `--non-interactive`: the user's yes, given to the coordinator with the source shown,
  is the confirmation. (Amended during Part A: `new-info`'s own Apply/Skip gate is an
  AskUserQuestion, and a background session's question can only be answered by attaching to it,
  so it cannot be relayed.) Its report shows what was applied and skipped. On a no, the fact is
  dropped and recorded as declined in the coordinator state.
- `new-info`'s "user-invoked" statement (`commands/new-info.md` intro, 0.47.0), the two README
  sentences that say it "stays user-invoked", and `fact-routing.md`'s policy gain "or a
  `run-epic` launch on the user's explicit yes"; the user's yes relayed at the gate is the
  confirmation that paragraph already names. Checked, reproducible facts keep routing inside
  the ticket as today.

Bounds: at most **2** remediation launches per ticket; a third need escalates. A remediation
session is judged by the same §A5 standard. The coordinator never edits code or Notion itself.

### A7. Coordinator state and resume

- File `.claude/notion-dev/coordinator/<epic>-<invocation>.json` in the primary (ignored
  directory): mode, per-iteration session id, ticket key, launch time, outcome, judgment,
  remediation launches, escalations.
- Re-invoking `/notion-dev:run-epic <epic>` with an unfinished state resumes it: a session still
  `working` is waited on, not relaunched; a finished one is judged.
- The coordinator's context holds only per-ticket judgments; auto-compaction of the coordinator
  loses nothing that matters because the state file is authoritative.

### A8. Ending

The run ends when `next-task` reports the epic complete, when every remaining child is blocked,
on an unresolved escalation, or on a bound. Final report: resolved tickets and PRs, open items
and what was done with each, sessions (ids) for review, then the coordinator's own closeout.

### A9. Gates and testing

- **G1 — Windows-native probe.** On the user's Windows machine, in Git Bash: `claude --bg` with
  a gated probe command, `claude agents --json --all` states, SessionStart/Stop hooks fire, and
  facts 10–11 (resume identity, yield wake). The plan ships the probe as a script the user runs.
  Windows-independent work proceeds meanwhile; G1 gates the merge (decision 15). Fail → bring
  the alternative to the user (e.g. Windows Terminal tabs `wt.exe new-tab`), never a silent
  fallback.
- Helpers (session-wait, marker-by-session lookup, state file) get unit tests driven by recorded
  `claude agents --json` fixtures, running on both CI legs. Command contracts get a
  `scripts/verify-*.sh` harness per `CLAUDE.md` (mechanism-level assertions, each proven to
  fail).
- Field test: a client epic in serial mode from WSL (smart-contracts-foundry) and from Windows
  (BTC-Gateway).

### A10. Release

Removing `--depth` breaks existing users of `next-task`, so the version policy
(`plugins/quick-dev/skills/develop/SKILL.md`) makes this a **major** bump (0.51.0 → 1.0.0), in one PR.

## Part B — parallel mode (outline; its plan follows Part A's field test)

### B1. Selection (user's algorithm)

Start from the ticket `next-task` would pick. Walk the following tickets in epic order; add a
ticket only if it is compatible with **every** ticket already selected; stop at the first
incompatible one or at `max`. Never skips ahead, so a lower-priority ticket never runs before a
higher one that had to wait.

### B2. Compatibility (to be designed in Part B's plan)

Incompatible when any holds: an explicit `## Blocked by` link (either direction or
transitively); a predicted overlap in files/modules, shared interfaces, schemas/migrations or
configuration; or a scope too uncertain to predict. Unsure → incompatible. "Hot files"
(version manifests, changelogs, lockfiles, migration numbers) do not count as overlap; they are
re-derived at the merge turn.

### B3. Launch

Each selected ticket: `claude --bg "/notion-dev:ticket <key> --non-interactive"`. Each finished
ticket is judged by §A5/§A6. Maximum concurrency from config (default to be decided), bounded
in practice by the shared Codex quota and machine resources.

### B4. Merge queue (agreed policy)

1. Prevent conflicts at selection (B2).
2. Sync with the base at two points only: before the PR opens, and at the merge turn.
3. Merge turn under a dedicated merge-turn marker (not `knowledge.py lock`, decision 13), granted in readiness order: update
   the branch from the base, re-run full verification, merge only if green.
4. The ticket's own session resolves its conflicts; real resolution edits get a delta review; a
   clean update with green verification needs no re-review.
5. The next merge turn waits for the base's CI on the previous merge to be green.
6. Hot files are mechanical: re-bump/re-derive from the new base.
7. An invalidated assumption surfaces as a red verification at the merge turn; the ticket's
   session fixes it and re-queues.

Prerequisite: restore notion-dev's explicit rebase-at-gate procedure (fact 9) and make the merge
turn a gate in notion-dev's review-and-merge.

### B5. Open for Part B

Fixed batch vs. refilling as tickets finish; default `max`; how the compatibility prediction
reads code (cost bound); where hot-file rules are declared per project.

## Left to the builder

- Helper names and exact CLI shape; poll interval and wait bounds.
- How the coordinator stays alive while waiting (within the one-waiter rule and the anti-goal).
- The state file's schema.
- Harness layout and test fixtures.
- Wording of the reports.
