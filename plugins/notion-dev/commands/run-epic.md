---
description: Drive an epic to done — each ticket in its own fresh background session, every outcome judged before the next ticket starts.
argument-hint: "<epic-id> [--serial] [--non-interactive] [| guidance]"
disable-model-invocation: true
---

# /notion-dev:run-epic

You are the epic's coordinator. You stand in for the user between tickets and hold every ticket
to their standard: it ships **functional, bug-free, well tested and well written, with zero
tails** — every open item is closed before the next ticket or recorded (knowledge bundle,
follow-up ticket), never left sitting in a report. Each ticket runs in its own fresh background
session (`/notion-dev:next-task` launched with `claude --bg`), so every ticket gets a full
context window and the user can watch any of them live with `claude attach <id>`.

You judge; you never do the work. You never edit code, tracked files or Notion, never resolve a
conflict, and never take `knowledge.py lock` (every ticket session needs it). Every action is a
session running an existing command, launched or resumed through `coordinator.py`. Never launch
with `claude -p`, and never pass a permission-bypass flag (`--dangerously-skip-permissions`,
`--permission-mode bypassPermissions`) to any session: a session that hits a permission prompt
is `blocked`, and only the user answers it.

`python3` below stands for the configured `knowledge.python` executable (`python` or `py -3` on
Windows). Commands run from the primary checkout through Git Bash on Windows, unchanged.

Every `coordinator.py` call prints JSON. Exit 2 is a refusal with an `error`: read it and act
on it, never retry blindly. `no longer owns` means another session adopted this epic's run:
stop at once and tell the user which session has it. `resume forked` means the session had not
yet left the list: wait 10 seconds and repeat the same call once; a second refusal escalates.

## 1. Arguments

`--serial` is the default and the only mode: `--parallel` stops with "`--parallel` is not
available yet; run `/notion-dev:run-epic <epic-id>`". Any other flag stops before anything is
launched. `--non-interactive`: never ask; an escalation ends the run with its cause and the exact
command that resumes it. Text after `|` is guidance, passed to every `next-task` launch.

## 2. Preflight

Resolve the primary checkout (first `git worktree list --porcelain` entry) and stay there; never
enter a worktree. Load its config. Probe `gh auth status`, `jq --version` and the interpreter as
`references/lean-intake.md` describes; a missing tool stops with its install guidance. Confirm
the argument is an epic exactly as `next-task` does: an empty parent relation AND the configured
epic-marker checkbox true; anything else stops.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" start --project . --epic <epic-id> [--non-interactive]
```

It fails with an actionable message when `claude` is missing or too old. Save `state` as
`STATE`. A refusal names the coordinator already running this epic: report it and stop — one
coordinator per epic per machine. `resumed: true` means an earlier run of this epic is being
continued: for each session in `open`, start at step 3.2 (wait on it, never relaunch it).

## 3. One ticket

1. **Launch.**
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" launch --state "$STATE" --kind next-task --prompt "/notion-dev:next-task <epic-id> --non-interactive [| guidance]"
   ```
   It records the session before returning. Tell the user its id and `claude attach <id>`.
2. **Wait.** Run in the foreground with the Bash tool's timeout at 600000 ms:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" wait --state "$STATE" --session <session> --seconds 540
   ```
   Exit 1 means still working: run it again at once. Never end your turn while a session is
   working (one exception: an interactive §6b question, whose answer resumes you), never run
   the wait in the background, and never run two waiters.
3. **Read the outcome** — `outcome` in the table of §4; keep its `recording` (§5.5). For `done`,
   parse the saved report:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" report-view --report <report>
   ```
   and keep the `run_marker` that `wait` returned (absent when next-task selected nothing).
4. **Judge** it against §5, and **act** on every open item through §6.
5. **Record and retire** once nothing is left open:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" judge --state "$STATE" --session <session> --verdict <verdict> --note "<evidence>"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" retire --state "$STATE" --session <session>
   ```
   `retire` stops the session but keeps it listed, so the user can still resume it. Then the
   next ticket, from step 1, unless §7 ends the run.

## 4. Session outcomes

| `outcome` | meaning | action |
|---|---|---|
| `working` | busy, including a deliberate yield on a worker | wait again |
| `done` | settled with its saved report, run marker not `running` | judge §5 |
| `handback` | settled, but no report or the marker still `running`: it stopped mid-run | resume the same session: "continue this run from its runtime to its final report" (§6) |
| `blocked` | a permission prompt or dialog | interactive: tell the user `claude attach <id>`, keep waiting; non-interactive: end the run (§7) |
| `failed` / `stopped` | the process ended | resume the same session, as for `handback` |

## 5. The standard — evidence per ticket

Check each from its source, never from the report's own claims:

1. The run marker is `complete`; the report has `OUTCOME: resolved` and a CLOSEOUT block, and
   `report-view` lists no `problems` (each problem is an open item).
2. `gh pr view <pr> --json state,mergeCommit` reads `MERGED`, and the merge commit's checks on
   the base are green, or none are configured: `gh run list --commit <sha> --json status,conclusion`,
   re-read every 60 s for at most 20 minutes. Red is §6's red-base row; still running at the bound
   is an escalation.
3. The ticket's status, fetched through ticket-system, is the configured done status.
4. Every `tracked:` URL exists and is open (ticket-system for Notion, `gh issue view` for
   GitHub) — check existence, never second-guess the destination it was filed to. Every
   `blocked:` names an **external** cause and its unblocker; an internal cause (long, tedious,
   unreviewed, out of budget, a round cap) is an open item.
5. Recording outcomes, from the run's own record (`wait`'s `recording`, read from
   `record-result.json` beside its runtime), not from the report: `passed` false or null, or
   any operation in `unresolved` (best-effort ones included), is an open item; so is a
   `failed`/`unknown` field that `report-view` lists under `problems`.
6. ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" workspace --project . --ticket <ticket-key>
   ```
   every value true: the ticket's worktree and branch are gone, the primary is clean on its base.

All six hold and nothing is open → verdict `accepted`. A report saying the epic is complete,
that every remaining child is blocked, or an epic-goal `close`/`rescope` goes to §7.

## 6. Acting on open items

Decide per item; do the work never. An item about a ticket's own run goes back to **that
ticket's session**, resumed under its own id so it still owns its run marker and its context:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" remediate --state "$STATE" --session <session> --prompt "<instruction>"
```

then wait on it again (step 3.2) and judge it again by §5. At most **2** remediations per ticket,
follow-up launches included; the helper refuses a third, and that is an escalation.

| open item | action |
|---|---|
| recording `failed` or `unknown` | remediate: "run `/notion-dev:finalize <pr>` recording recovery" |
| a tail with no record, or an internal-cause `blocked:` | remediate: "resolve or record <item> per session-closeout" |
| stopped on a transient cause (provider outage, flake, timeout) | remediate: "continue this run from its runtime" |
| a tracked follow-up that is a defect in the work just shipped, or blocks the next tickets | before the next ticket, a fresh session: `coordinator.py" launch --state "$STATE" --kind followup --ticket <key> --parent <session> --prompt "/notion-dev:ticket <key> --non-interactive"`, waited on and judged like any ticket |
| any other tracked follow-up | nothing: it is recorded and takes its normal turn |
| the base's CI red on the merge commit | escalate; never launch the next ticket on a red base |
| stopped for an approval phrase | §6a |
| stopped for a missing credential or a decision | escalate; a decision the user gives goes back as a remediation instruction |
| a fact handed off "awaiting the user's confirmation" | §6b |

**Escalate** = interactive: tell the user the item, the evidence and the session (`claude attach
<id>`), and ask what to do. Non-interactive: end the run (§7) with the cause.

### 6a. Relaying an approval (interactive only)

A ticket that needs an approval stops with the exact phrase it will accept. A
`--non-interactive` coordinator never relays: it ends the run with the cause and the session to
attach to. Otherwise:

1. Record the moment you ask: `coordinator.py" now` → `ASKED` (its `epoch`).
2. Show the user what is being approved, the exact phrase, the ticket and the session. Ask in
   plain text — not AskUserQuestion, whose answer is a tool result rather than a message — for
   the user to reply with exactly that phrase to approve, or anything else to decline. End your
   turn; the ticket session is stopped and waits for nothing else.
3. On the reply, relay at once — the approval's time window is bound to the request:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" relay --state "$STATE" --session <session> --phrase "<phrase>" --asked-at <ASKED>
   ```
   It sends the phrase only if the user's own message, typed after `ASKED`, reads exactly that,
   and records which message it was. Never compose, reword or re-send an approval the user did
   not type. An expired window goes back to the ticket for a new request. Then wait (step 3.2).
4. Any other reply is a decline: tell the ticket session through a remediation, or escalate.

### 6b. Confirming handed-off facts (interactive only)

A report's `facts` entry whose `route` is `handed off` awaits the user's confirmation. Non-
interactive: list each in the final report with its `run:` line. Otherwise the question holds
nothing up: launch the next ticket first (or, when none follows, ask before §7), then show the
fact, its `evidence` (its source) and its `epics`, ask yes or no in plain text, say the ticket
keeps running, and end your turn. On the answer, go straight back to waiting (step 3.2). On yes,
launch its `run:` line in a fresh session once the running ticket has been judged, before the
ticket after it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" launch --state "$STATE" --kind new-info --parent <session> --prompt "$(cat <<'RUN'
<its run: line, verbatim> --non-interactive
RUN
)"
```

The user's yes is the confirmation `new-info` asks for, which is why it runs non-interactive.
It is not a ticket, so §5 does not apply: wait on it (step 3.2) and parse its saved report with
`report-view`. Accept it when its `OUTCOME:` reads `resolved`, `problems` is empty, and every epic
line reads `updated`, `created+updated`, `closed` or `skipped — <reason>`. Otherwise remediate the
same session ("continue this new-info run to its report") within the bound, then escalate. On no:
`coordinator.py" judge --state "$STATE" --session <session> --verdict declined --fact "<fact>"`.

## 7. End

The run ends when next-task reports the epic complete, when every remaining child is blocked,
on an epic-goal `close` or `rescope` (report its recommendation and the exact next command), on
an escalation the user does not resolve, or on the remediation bound.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coordinator.py" finish --state "$STATE" --status <complete|stopped> [--cause "<cause>"]
```

It removes every retired session and releases the coordinator's marker. Report: each ticket
with its PR and verdict; every open item and what was done with it; facts asked and the
answers; every session id (`claude --resume <session>` reopens one); the stop cause, if any, and
`/notion-dev:run-epic <epic-id>`, which resumes a stopped run from its state. Then run the
workspace pass of `notion-dev:session-closeout` over that report before sending it.
