# run-epic (serial) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `/notion-dev:run-epic <epic> [--serial]`, a coordinator session that runs each ticket of an epic in its own fresh Claude Code background session and judges every outcome before starting the next; `next-task` loses `--depth`.

**Architecture:** A new standard-library helper `plugins/notion-dev/scripts/coordinator.py` owns everything mechanical — launching/resuming/stopping background sessions through the `claude` CLI, the coordinator's state file and exclusivity marker, waiting, locating outcomes, parsing reports, recording judgments and relaying approvals. A new command `plugins/notion-dev/commands/run-epic.md` owns the judgment and calls only that helper. `next-task`, `ticket` and `finalize` each gain one line that saves their final report through a new `workflow.py save-report`.

**Tech Stack:** Python 3 standard library (the plugin's `knowledge.python`), Markdown commands, bash harnesses using `scripts/lib/assert.sh`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-03-epic-coordinator-design.md` (Part A only). Read it first; facts and decision numbers below refer to it.

## Global Constraints

- Works unchanged on WSL 2 Ubuntu and Windows-native Claude Code through Git Bash; no GNU-only flags, no `python3` literal outside examples that say it stands for `knowledge.python`, LF + UTF-8 output, child output decoded `encoding="utf-8"`.
- Sessions are launched only with `claude --bg`; never `claude -p`, never `--dangerously-skip-permissions`, `--permission-mode bypassPermissions` or `--allow-dangerously-skip-permissions`.
- Resume keeps identity only as stop → rm → `claude --bg --resume <sessionId> "<prompt>"` (fact 10); a resume that yields a different session ID is an error, never accepted.
- Paths (all under the primary checkout's ignored `.claude/notion-dev/`): state `coordinator/<epic>-<invocation>.json`; exclusivity marker `runs/coordinator-<epic>.json`; reports `reports/<session>.md`.
- Constants: wait slice default 540 s, poll interval 15 s, remediation bound 2 per ticket, marker staleness 120 min (= `hooks/stop-guard.sh` `STALE_MINUTES`).
- The coordinator never edits tracked files, Notion or code, and never uses `knowledge.py lock` (decision 13).
- `ticket.md` + `next-task.md` + `finalize.md` + `skills/review-and-merge/SKILL.md` stay under 30000 bytes together (`test_default_entrypoints_are_small_and_route_to_shared_owners`).
- Every harness assertion comes from `scripts/lib/assert.sh` and is proven to fail by mutation in an isolated checkout after committing (`CLAUDE.md`).
- `references/legacy/*` is not edited (its harness lines pin the legacy `--depth`).
- One PR; notion-dev `plugin.json` 0.51.0 → 1.0.0 (removing `--depth` is breaking).

## Review Focus

1. `claude --bg` output carrying extra lines (the auth warning, ANSI) before the id → the id is still parsed (`test_launch_parses_id_after_warning_lines`, Task 2).
2. `claude` missing from PATH, or `claude agents --json` printing non-JSON (older CLI) → a one-line actionable error, not a traceback (`test_missing_claude_and_bad_json_are_actionable`, Task 2).
3. The coordinator session itself restarts or compacts mid-epic → re-invoking resumes the same state and waits on the still-working session instead of launching another (`test_start_resumes_unfinished_state`, Task 3).
4. A session reads `done` but wrote no report (report write failed, or it handed back) → outcome `handback`, never `accepted` (`test_done_without_report_is_handback`, Task 4).
5. Two coordinators for two different epics on one machine → both start; the same epic twice from two sessions → the second is refused (`test_exclusivity_is_per_epic`, Task 3).

---

### Task 1: Live probe script, and its Linux run

**Files:**
- Create: `scripts/analysis/probe-background-sessions.sh`

**Interfaces:**
- Produces: a script run as `bash scripts/analysis/probe-background-sessions.sh <trusted-dir>` printing one `PASS|FAIL <check>` line per check and exiting non-zero on any FAIL. Not part of `run-verifications.sh` (it spends tokens and needs a logged-in CLI). Task 9 hands it to the user for Windows (gate G1).

- [ ] **Step 1: Write the script.** It builds a throwaway plugin in a temp dir under `<trusted-dir>/.claude/notion-dev/probe-<random>/` (ignored path; removed on exit, trap) with one `disable-model-invocation: true` command that replies a token, a `--settings` file with SessionStart and Stop hooks that append the hook input's `session_id`/`source` to a log, then checks, in order:
  1. `claude --bg "/probe:gated <tok>" --plugin-dir … --settings …` from `<trusted-dir>` prints an id;
  2. `claude agents --json --all` shows that id `working` then `done` within 180 s, `sessionId` starting with the id;
  3. SessionStart and Stop logs hold that `sessionId`;
  4. `claude logs <id>` contains the reply token (strip ANSI with `sed 's/\x1b\[[0-9;]*[A-Za-z]//g'`);
  5. `claude stop`, `claude rm`, then `claude --bg --resume <sessionId> "<tok2>"` → SessionStart `source` is `resume` with the same `sessionId`;
  6. the session transcript (path from the Stop hook input's `transcript_path`) has a row with `type: "user"`, that `sessionId`, no `isSidechain`, whose text is exactly `<tok2>` (python one-liner via `${PYBIN:-python3}`);
  7. a background session told to launch one background subagent (`sleep 60`) and end its turn reads `working` until it replies the wake token, then `done`.
  8. (added during execution) a session at a permission prompt reads `blocked`; with 2 the settle signal became `status: idle` (spec facts 12–13).
  It stops and removes every session it created, also on failure.
- [ ] **Step 2: Run on Linux.** `bash scripts/analysis/probe-background-sessions.sh "$PWD"` from the repo root. Expected: 8 PASS (7 as first planned), exit 0. A FAIL on 5–8 stops the plan and goes back to the user (facts 10–11 or the relay premise changed).
- [ ] **Step 3: Commit.** `git add scripts/analysis/probe-background-sessions.sh && git commit -m "test(notion-dev): live probe for background-session behaviour run-epic relies on"`

### Task 2: Session layer in `coordinator.py`

**Files:**
- Create: `plugins/notion-dev/scripts/coordinator.py`
- Create: `scripts/tests/fake_claude.py` (not a test module; the discovery pattern is `test_*.py`)
- Test: `scripts/tests/test_coordinator.py`

**Interfaces:**
- Produces (module `coordinator`):
  - `claude_command() -> list[str]` — `[sys.executable, $NOTION_DEV_CLAUDE_FAKE]` when that env var is set, else `[shutil.which("claude")]`; `Invalid("claude is not on PATH; …")` when missing.
  - `agents() -> list[dict]` — parsed `claude agents --json --all`; `Invalid` naming the CLI version requirement on non-JSON.
  - `entry(session: str) -> dict | None` — the agents entry whose `sessionId` equals `session`.
  - `launch(cwd: Path, prompt: str) -> dict` — runs `claude --bg <prompt>` in `cwd`, parses the short id from `backgrounded · <id>` or `claude logs <id>`, resolves `sessionId` via `agents()`; returns `{"id": str, "session": str}`.
  - `resume(cwd: Path, session: str, prompt: str) -> dict` — `claude stop <id>`, `claude rm <id>`, `claude --bg --resume <session> <prompt>`; requires the printed id to be `session[:8]` and `entry(session)` to exist; otherwise stops+removes the fork and raises `Invalid("resume forked …")`.
  - `stop(short_id: str) -> None`, `remove(short_id: str) -> None`.
- `fake_claude.py`: a script emulating those CLI calls against a JSON world file at `$NOTION_DEV_FAKE_WORLD` (`{"sessions": [...], "calls": [...], "prefix_lines": [...], "settle_after": n}`): appends each argv to `calls`; `--bg <p>` adds a `working` session that becomes `done` after `settle_after` `agents` calls; `--bg --resume <uuid> <p>` reuses the id if the uuid is not listed, else creates a fork with a new id; prints `prefix_lines` before its output.

- [ ] **Step 1: Write the failing tests** in `test_coordinator.py` (set `NOTION_DEV_CLAUDE_FAKE`/`NOTION_DEV_FAKE_WORLD` in `setUp`, temp dirs per test):
  - `test_launch_returns_short_id_and_full_session` — `launch(tmp, "/notion-dev:next-task STO-1 --non-interactive")` returns an id of 8 hex chars and a session starting with it; world `calls[0]` is `["--bg", "/notion-dev:next-task STO-1 --non-interactive"]`.
  - `test_launch_parses_id_after_warning_lines` — with `prefix_lines` holding the `ANTHROPIC_API_KEY … takes precedence` warning and an ANSI-coloured line, the id still parses.
  - `test_resume_keeps_identity_after_stop_and_rm` — calls are `stop`, `rm`, `--bg --resume <uuid> <prompt>` in that order; returned session equals the original.
  - `test_resume_that_forks_is_refused` — fake configured to fork (session still listed after rm) → `Invalid` containing `forked`, and the fork was stopped and removed.
  - `test_missing_claude_and_bad_json_are_actionable` — `NOTION_DEV_CLAUDE_FAKE` unset and `PATH` without `claude` → `Invalid` containing `not on PATH`; fake printing `oops` for `agents` → `Invalid` containing `claude agents --json`.
  - `test_no_permission_bypass_flags_are_ever_passed` — after launch and resume, no recorded argv contains `-p`, `--print`, `--dangerously-skip-permissions`, `bypassPermissions`, `--allow-dangerously-skip-permissions`.
- [ ] **Step 2: Run.** `python3 -m unittest discover -s scripts/tests -p 'test_coordinator.py'` → FAIL (`No module named 'coordinator'`).
- [ ] **Step 3: Implement** the Interfaces above. Import `Invalid`, `require`, `read_json`, `atomic_json`, `state_lock` from `runtime` (same `sys.path` handling as `workflow.py`). `subprocess.run(..., encoding="utf-8", capture_output=True)`; id regex `(?:backgrounded · |claude logs )([0-9a-f]{8})`.
- [ ] **Step 4: Run** the same command → PASS.
- [ ] **Step 5: Commit.** `git add plugins/notion-dev/scripts/coordinator.py scripts/tests/fake_claude.py scripts/tests/test_coordinator.py && git commit -m "feat(notion-dev): coordinator session layer over claude --bg"`

### Task 3: State file, exclusivity marker, judgments

**Files:**
- Modify: `plugins/notion-dev/scripts/coordinator.py`
- Test: `scripts/tests/test_coordinator.py`

**Interfaces:**
- Consumes: Task 2's `launch`, `resume`, `stop`, `remove`; `workflow.primary`, `workflow.local_dir`, `workflow.now`.
- Produces:
  - `start(project, epic: str, session: str, non_interactive: bool) -> dict` → `{"state": path, "marker": path, "resumed": bool, "open": [session ids still unjudged]}`. Marker `runs/coordinator-<epic>.json` carries the stop-guard's five keys — `run` (`"coordinator-<epic>"`), `phase`, `state` (`running`), `non_interactive`, `claude_session` — plus `heartbeat` and `state_path`. Refuses when the marker is `running`, its `claude_session` differs and its `heartbeat` is under 120 min old; adopts it (records `adopted_from`) otherwise. An unfinished state for the epic is resumed, not replaced.
  - State JSON: `{"epic", "root": <primary path, the cwd for every launch/resume>, "mode": "serial", "non_interactive", "invocation", "launches": [{"id", "session", "kind", "prompt", "ticket", "parent", "launched", "verdict", "notes": [], "relays": []}], "remediations": {ticket: n}, "status": "running|complete|stopped", "cause"}`.
  - `record_launch(state_path, kind: str, prompt: str, ticket: str | None, parent: str | None) -> dict` — launches through `launch()` and appends **before** returning (spec §A3.1 order: the launch is recorded before any wait).
  - `remediate(state_path, session: str, prompt: str) -> dict` — `resume()` on that session, increments `remediations[ticket]`; when it is already 2, raises `Invalid("remediation bound reached …; escalate")` without resuming.
  - `judge(state_path, session, verdict: "accepted|remediate|escalate|declined", note: str) -> None`.
  - `retire(state_path, session) -> None` — `stop()`; keeps it listed.
  - `finish(state_path, status: "complete|stopped", cause: str | None) -> dict` — `remove()` every retired launch, writes terminal status to state and marker (marker `state` becomes `complete`/`stopped`).
  - Every write also refreshes the marker `heartbeat` (atomic rewrite → mtime, which the stop guard reads).

- [ ] **Step 1: Failing tests:**
  - `test_start_creates_state_and_guardable_marker` — in a temp `git init` repo (the guard resolves the primary through git); marker JSON has exactly the five stop-guard keys plus `heartbeat`, `state_path`; running `bash plugins/notion-dev/hooks/stop-guard.sh` with a Stop input for that `claude_session` and `cwd` = project, `non_interactive=True`, outputs a block decision; with `non_interactive=False` it allows.
  - `test_exclusivity_is_per_epic` — `start(p, "STO-1", "a")` then `start(p, "STO-1", "b")` → `Invalid` containing `coordinator-STO-1`; `start(p, "STO-2", "b")` succeeds.
  - `test_stale_marker_is_adopted` — marker heartbeat set 121 min old → `start(…, "b")` succeeds with `adopted_from == "a"`.
  - `test_start_resumes_unfinished_state` — after one `record_launch`, a new `start` returns `resumed: True` and `open == [that session]`; no new `--bg` call recorded.
  - `test_remediation_bound_is_two_per_ticket` — third `remediate` for one ticket raises `Invalid` containing `escalate`; world records exactly two `--resume` calls.
  - `test_finish_removes_retired_sessions_and_terminates_marker` — `rm` called for each retired id; marker `state == "complete"`; stop-guard now allows.
- [ ] **Step 2: Run** `python3 -m unittest discover -s scripts/tests -p 'test_coordinator.py'` → the new tests FAIL.
- [ ] **Step 3: Implement** the Interfaces; marker writes under `state_lock(marker.with_suffix(".claim.lock"), 5)` like `workflow.marker_update`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat(notion-dev): coordinator state, per-epic exclusivity marker and bounded remediation"` (add the test file explicitly if untracked).

### Task 4: Waiting and locating outcomes

**Files:**
- Modify: `plugins/notion-dev/scripts/coordinator.py`
- Test: `scripts/tests/test_coordinator.py`

**Interfaces:**
- Consumes: `entry()`, the state/marker from Task 3; `workflow.save_report`'s path rule from Task 6 (`reports/<sanitized session>.md`, sanitized as `re.sub(r"[^A-Za-z0-9._-]", "_", s)`) — define the shared `report_path(root, session) -> Path` here and have Task 6 import it.
- Produces:
  - `wait(state_path, session, seconds=540, interval=15) -> dict` → `{"settled": bool, "agent_state": str | None, "report": str | None, "run_marker": dict | None, "outcome": "working|done|handback|blocked|failed|stopped"}`. Polls `entry()` every `interval` until `state` ≠ `working` or `seconds` elapse; refreshes the coordinator marker heartbeat each poll. `outcome` is: `done` when settled `done` and the report exists; `handback` when settled `done` and either the report is missing or the run marker is `running`; otherwise the agent state. CLI exit 0 settled, 1 pending (same convention as `workflow.py await-worker`).
  - `run_marker(root, session) -> dict | None` — the `runs/<KEY>-<n>.json` (not `preflight-*`, not `coordinator-*`) whose `claude_session` equals `session`, with its path.
  - `workspace(project, ticket: str) -> dict` → `{"worktree_gone": bool, "branch_gone": bool, "primary_on_base": bool, "primary_clean": bool}` from `git worktree list --porcelain`, `git for-each-ref refs/heads`, the config's `prTargetBranch|baseBranch`, and `git status --porcelain --untracked-files=all` (ignoring the same exempt files as `workflow.preflight`).

- [ ] **Step 1: Failing tests:**
  - `test_wait_returns_pending_then_settles` — `settle_after=3`, `seconds=0` → `settled False`, `outcome "working"`; then with time → `settled True`.
  - `test_done_without_report_is_handback` — settled `done`, no report file → `outcome "handback"`; with report but run marker `running` → `handback`; report + marker `complete` → `done`.
  - `test_blocked_is_reported_not_waited_through` — fake session in `blocked` → returns immediately, `outcome "blocked"`.
  - `test_run_marker_ignores_preflight_and_coordinator_markers` — three markers with the same `claude_session`; only `STO-7.json` is returned.
  - `test_workspace_flags_leftovers` — temp git repo with a leftover branch `ticket/STO-7-x` → `branch_gone False`; after deleting it → all four true.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Use `time.monotonic()`; `time.sleep(interval)` between polls (tests pass `interval=0`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat(notion-dev): coordinator waits on a session and locates its outcome"`

### Task 5: Report parser

**Files:**
- Modify: `plugins/notion-dev/scripts/coordinator.py`
- Test: `scripts/tests/test_coordinator.py`

**Interfaces:**
- Produces `report_view(text: str) -> dict` →
  `{"outcome": str | None, "closeout": {"TAILS-FOUND": int, "RESOLVED": int, "TRACKED": int, "BLOCKED": int, "PASSES": int} | None, "tracked": [{"item": str, "url": str}], "blocked": [{"item": str, "cause": str, "unblock": str}], "facts": [{"fact": str, "evidence": str, "epics": str, "route": str, "run": str | None}], "problems": [str]}`.
  Formats parsed are exactly those the plugin writes: `OUTCOME: <value>`; the session-closeout block and its `- tracked: <item> — <url>` / `- blocked: <item> — <cause>; unblocked by <what>` lines; record.md's `NEW-INFO:` block (`- fact:` / `evidence:` / `epics:` / `route:` / `run:`). `problems` lists every inconsistency the coordinator must treat as an open item: a CLOSEOUT count that differs from its listed lines, a missing CLOSEOUT block, a `tracked:` without a URL, a `blocked:` without `unblocked by`.
- CLI: `coordinator.py report-view --report <path>` prints the JSON.

- [ ] **Step 1: Failing tests** with inline report fixtures:
  - `test_report_view_parses_resolved_report` — OUTCOME `resolved`, closeout counts, one tracked (URL kept verbatim), one blocked split into cause/unblock.
  - `test_report_view_extracts_handed_off_facts` — a `NEW-INFO:` block with one `route: handed off — human-sourced` fact and its `run:` line → `facts[0]["run"]` is that line; a `NEW-INFO: none` report → `facts == []`.
  - `test_report_view_flags_inconsistencies` — `TRACKED: 2` with one tracked line, a tracked line without URL, a missing closeout → three `problems`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (line-based regexes; tolerate `—` and `-` separators). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat(notion-dev): parse ticket reports into the coordinator's open items"`

### Task 6: `workflow.py save-report`

**Files:**
- Modify: `plugins/notion-dev/scripts/workflow.py` (new function + subparser next to `complete`)
- Test: `scripts/tests/test_lean_workflow.py`

**Interfaces:**
- Consumes: `coordinator.report_path(root, session)` (Task 4).
- Produces `save_report(project, session: str, text: str) -> Path` and CLI `workflow.py save-report --project <root> [--session <id>] --from <path|->` (session default `$NOTION_DEV_SESSION_ID`). Resolves the primary via `primary(project)` (works from a worktree), writes UTF-8 + LF atomically, overwrites; empty session → `Invalid("NOTION_DEV_SESSION_ID missing …")`; prints `{"report": path}`.

- [ ] **Step 1: Failing tests:** `test_save_report_lands_in_primary_from_a_worktree` (call with a worktree path; file is under the primary's `.claude/notion-dev/reports/`), `test_save_report_is_lf_and_overwrites` (CRLF input → LF bytes; second save replaces), `test_save_report_needs_a_session`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s scripts/tests -p 'test_lean_workflow.py'` → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat(notion-dev): save-report persists a session's final report for run-epic"`

### Task 7: Approval relay

**Files:**
- Modify: `plugins/notion-dev/scripts/coordinator.py`
- Test: `scripts/tests/test_coordinator.py`

**Interfaces:**
- Consumes: `remediate()` is **not** used (a relay is not a remediation and does not spend the bound); uses `resume()` directly.
- Produces `relay(state_path, session, phrase: str, expect: str, transcript: Path, coordinator_session: str, asked_at: float) -> dict` and CLI `coordinator.py relay --state --session --phrase --expect --asked-at <epoch> [--transcript $NOTION_DEV_TRANSCRIPT] [--coordinator-session $NOTION_DEV_SESSION_ID]`:
  - refuses when the state is `non_interactive` (`Invalid` containing `never relays`);
  - finds, in the coordinator's own transcript, the **latest** row with `type: "user"`, `sessionId == coordinator_session`, no `isSidechain`/`isMeta`/`isCompactSummary`/`toolUseResult`, timestamp ≥ `asked_at`, whose text (string or text blocks joined) stripped equals `expect` stripped — the same row rules as `host_capture.user_approval`; none → `Invalid("no matching user answer …")`;
  - then `resume(cwd, session, phrase)` and appends `{"phrase", "user_message": <uuid>, "user_text", "at"}` to that launch's `relays`.

- [ ] **Step 1: Failing tests:** `test_relay_requires_a_real_user_turn` (an assistant row and a sidechain user row with the text do not count; a parent user row does), `test_relay_ignores_answers_before_the_question` (row before `asked_at` → refused), `test_relay_records_provenance_and_sends_exact_phrase` (fake records `--resume <uuid> <phrase>` with the phrase byte-identical; state `relays[0]["user_message"]` is the row's uuid), `test_non_interactive_never_relays`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat(notion-dev): relay a user-given approval into the owning ticket session"`

### Task 8: Command contracts — run-epic, next-task, ticket, finalize

**Files:**
- Create: `plugins/notion-dev/commands/run-epic.md`
- Modify: `plugins/notion-dev/commands/next-task.md`, `commands/ticket.md`, `commands/finalize.md`
- Create: `scripts/verify-coordinator.sh`
- Modify: `scripts/verify-windows.sh` (one assertion that `verify-coordinator.sh` runs `-p 'test_coordinator.py'`, as it already does for the lean suite)

**Interfaces:**
- Consumes: every `coordinator.py` CLI from Tasks 2–7 (`start`, `launch`, `wait`, `report-view`, `workspace`, `remediate`, `relay`, `judge`, `retire`, `finish`) and `workflow.py save-report`. Add any missing argparse subcommands to `coordinator.py` in this task; each prints JSON and exits 0/1/2 (2 = `Invalid`).

- [ ] **Step 1: Write `run-epic.md`.** Frontmatter: `description`, `argument-hint: "<epic-id> [--serial] [--non-interactive] [| guidance]"`, `disable-model-invocation: true`. Body, in this order, each section citing the spec section it implements:
  1. Parse: `--serial` default; `--parallel` → stop with "not available yet"; unknown flags rejected before any launch.
  2. Preflight: lean-intake probes (config, interpreter, `gh auth status`, `jq --version`), epic check as `next-task`, then `coordinator.py start`.
  3. Iterate (§A3): `launch` with `/notion-dev:next-task <epic> --non-interactive [| guidance]` → `wait` in foreground slices until settled (never end the turn while `working`; one waiter) → `report-view` + run marker → §A5 checks (`gh pr view`, `gh pr checks` on the merge commit with a bound, ticket-system status read, tracked/blocked existence, `workspace`) → `judge` → `retire`.
  4. States table (§A4) verbatim in meaning.
  5. Acting (§A6 table), with remediation through `coordinator.py remediate` only, approvals through `relay` (§A6a: show request, ask, relay only an explicit yes, immediately; `--non-interactive` never relays), handed-off facts (§A6b as amended: ask with source; yes → `launch` a fresh session with that fact's `run:` line plus `--non-interactive`; no → `judge … declined`).
  6. End (§A8): `finish`, final report, then `notion-dev:session-closeout` workspace pass.
  7. Never: `claude -p`, permission-bypass flags, editing code/Notion/tracked files, `knowledge.py lock`.
- [ ] **Step 2: `next-task.md`.** Remove `--depth` parsing and the repeat loop: one selection, one `ticket` delegation, one report. `--depth` given → stop: "`--depth` was removed in 1.0.0; use `/notion-dev:run-epic <epic>`". `argument-hint` drops `[--depth=N|all]`. Last step: save the finished report with `workflow.py save-report --project "$REPO_ROOT" --from -`.
- [ ] **Step 3: `ticket.md` and `finalize.md`.** After the closeout and before `complete`, also on the stop path: save the finished report with `workflow.py save-report`. Authorization lines become "…at the user's request or through an authorized next-task or run-epic run" (ticket) and "…within an authorized ticket/next-task/run-epic run" (finalize).
- [ ] **Step 4: Run** `python3 -m unittest discover -s scripts/tests -p 'test_lean_workflow.py'` → the 30000-byte entrypoint test PASSES (trim wording in next-task if not).
- [ ] **Step 5: Write `scripts/verify-coordinator.sh`** (copy `verify-lean-workflow.sh`'s header/`ok`/`bad`/`PYBIN` pattern): runs `test_coordinator.py`; then assertions on `RE=plugins/notion-dev/commands/run-epic.md`:
  - `assert_present` frontmatter `^disable-model-invocation: true` in lines 1–5;
  - `assert_order` of `coordinator.py" start` < `coordinator.py" launch` < `coordinator.py" wait` < `coordinator.py" report-view` < `coordinator.py" judge` < `coordinator.py" retire` < `coordinator.py" finish`;
  - `assert_has` `--parallel` rejection, `coordinator.py" remediate`, `coordinator.py" relay`, the non-interactive never-relays line, `session-closeout`;
  - `assert_lacks` `claude -p`, `--dangerously-skip-permissions`, `bypassPermissions`, `knowledge.py" lock`;
  - on next-task: `assert_lacks` `--depth=N`, `assert_has` the removal pointer to `run-epic` and `workflow.py" save-report`;
  - on ticket and finalize: `assert_has` `workflow.py" save-report` and `run-epic` in the authorization line.
  Shortest distinctive fragments; one place per anchor (`CLAUDE.md` harness rules).
- [ ] **Step 6: Run** `bash scripts/verify-coordinator.sh` → all PASS. **Commit**, then in an isolated clone (`git clone -q . "$TMP/m"`) break each guarded line once and confirm the matching FAIL; record the mutation list in the commit message of the next task.
- [ ] **Step 7: Commit.** `git add … && git commit -m "feat(notion-dev): run-epic command; next-task resolves one ticket; reports saved for the coordinator"`

### Task 9: Policy text, README, version, spec amendment, full suite, G1 hand-off

**Files:**
- Modify: `plugins/notion-dev/references/review-accounting.md` (approval paragraph: a `run-epic` relay of the user's explicit yes into the owning session is the sanctioned path; nothing else changes)
- Modify: `plugins/notion-dev/commands/new-info.md` (intro "user-invoked" sentence), `plugins/notion-dev/references/fact-routing.md`, `plugins/notion-dev/README.md` (the two "stays user-invoked" sentences): add "or a `run-epic` launch on the user's explicit yes"
- Modify: `plugins/notion-dev/README.md` — commands table row for `run-epic`; `next-task` row and the parallel-sessions paragraph without `--depth`; a `1.0.0` release section stating the breaking removal, `run-epic`, `save-report`, the relay, and the Windows probe status
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json` → `"version": "1.0.0"`
- Modify: `docs/superpowers/specs/2026-11-03-epic-coordinator-design.md` §A6b: the fact session runs `new-info … --non-interactive` after the user's yes (a background session's own question can only be answered by attaching), the yes being the confirmation; its report shows what was applied
- Modify: `scripts/verify-coordinator.sh` — `assert_has` `run-epic` in review-accounting, new-info, fact-routing; `assert_version_above` is already enforced repo-wide (no new check)

- [ ] **Step 1: Make the edits above.** README stale claim from fact 9 (rebase at the merge gate) is Part B's prerequisite: state in the 1.0.0 section that the paragraph describes behaviour Part B restores, without changing the paragraph's other content.
- [ ] **Step 2: Run** `bash scripts/verify-coordinator.sh` → PASS; mutation-prove the new assertions as in Task 8 step 6.
- [ ] **Step 3: Run the full suite** `bash scripts/run-verifications.sh` → overall success line.
- [ ] **Step 4: Commit.** `git commit -am "docs(notion-dev): run-epic policy paths, README and 1.0.0"`
- [ ] **Step 5: G1 hand-off.** Give the user the Windows command, to run in Git Bash from the BTC-Gateway checkout: `bash <pure-dev>/scripts/analysis/probe-background-sessions.sh "$PWD"` (the script lives in this repo; they pass its path). The PR may open and go through review meanwhile; **merge waits for 8 PASS on Windows** (decision 15). Any FAIL comes back to the user with the spec's alternative (`wt.exe new-tab`), never a silent fallback.
