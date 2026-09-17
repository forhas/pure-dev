---
description: Implement a single ticket end-to-end. Creates a worktree, triages the build flow, implements (feature-dev or superpowers), verifies, ships a PR, runs the review-and-merge loop, merges, and cleans up. Updates the ticket status at each checkpoint.
argument-hint: "<ticket-id> [--non-interactive] [--flow=feature-dev|superpowers] [| <optional guidance>]"
---

# /notion-dev:ticket

Full implementation cycle for one ticket, end to end: fetch → clarify → isolate → triage → build → verify → ship → review & merge → record → clean up.

Args: `<ticket-id> [--non-interactive] [--flow=feature-dev|superpowers] [| <optional user guidance>]`

`<ticket-id>` is either the Notion page id from the page URL (the 32-hex id, e.g. `383fdf83c4178177beebd41a69bf47bc` in `https://app.notion.com/p/.../...-383fdf83c4178177beebd41a69bf47bc`; a dashed UUID or the full page URL works too), or the logical key (`STO-42`).

If called with no argument, attempt to extract the **numeric** ticket id from the current branch name (pattern `<project.key>-<n>` or `ticket/<project.key>-<n>-*`); otherwise fail with guidance. This is the **resume** path — a fresh run passes the page id/URL or logical key, while resuming from inside a worktree relies on the numeric id already encoded in the branch.

**Invocation guard.** Run this command only when the user typed it, or when `/notion-dev:next-task` delegated to it. Never start it on your own initiative because a prompt mentions a ticket — it creates a worktree, moves the ticket to In Progress, and opens a PR. The frontmatter flag that used to enforce this was removed so `/notion-dev:next-task` can chain into it; this sentence is what replaces it.

Flag parsing (modeled on quick-dev's `develop` skill):
- If the arguments contain `--non-interactive`, remove it and set **non-interactive mode**: never pause for user input; whenever any step (including the build flow's own checkpoints) calls for asking the user, self-answer with the most reasonable option and log the decision for the final report (Phase 10).
- If the arguments contain `--flow=<value>`, remove it and record the value as `FLOW_OVERRIDE`. Valid values: `feature-dev`, `superpowers`. Any other value: stop immediately — before creating anything — and name the two valid values.
- Everything after a `|` is optional guidance and remains available context throughout the run.
- Whatever remains is the `<ticket-id>` (or empty, for the no-arg resume path above).

**Continuous execution — non-interactive mode is *never hand back*, not only *never ask*.** Do not end your turn between phases, between steps inside a phase, or after a delegated skill or subagent returns. A message that ends with `Next: <the thing you were about to do>` and then stops is the exact failure this rule names, and the self-answer rule above does not reach it: no question was asked, so nothing was left unanswered — the run simply handed back, and in a non-interactive run nobody is watching to type "continue". Announcing what comes next is fine; announcing it *instead of doing it* is the defect. The only things that end a non-interactive run are the stop conditions this command names explicitly — the preconditions gate, 1.3's under-spec and blocked-on-external stops, `PLAN-REVIEW: blocked` (4.2b), `retry-exhausted:verify` (5.1), and "Failure and stop conditions" — and Phase 10's report. Measured in two clients on the same day: two runs stopped mid-`Phase 4`, one after 4.2(a) and one after 4.2(b), each with a `Next:` line and no question asked.

**Standing rule — runtime issues.** Anything unexpected at runtime — for example an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, or a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens, not batched to the end of the run. That skill is **authoritative** for the full trigger list, the entry format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must **not** be logged; the examples here are illustrative, not exhaustive. The rule applies to conditions nobody enumerated in advance. A failure to write the log never fails the run.

## Preconditions

- **Superpowers and feature-dev (required).** `dependencies.superpowers` **and** `dependencies.featureDev` in the config must both be `true` — if either is missing or false, abort and tell the user to re-run `/notion-dev:init` (which verifies and records both). Confirm `superpowers:writing-plans`, `superpowers:subagent-driven-development`, `superpowers:receiving-code-review`, and `feature-dev:feature-dev` are all available; this command delegates planning, execution, and review to them.
- **GitHub access**: authenticated `gh` CLI is **required** — the Phase 7 review loop (`notion-dev:review-and-merge`) depends on `gh` for paginated comment reads and GraphQL review-thread resolution, which the GitHub MCP cannot perform. Probe `gh auth status` at the top of the command; abort with "Install and authenticate `gh` (`gh auth login`), then re-run" if unavailable. The GitHub MCP (`mcp__github__create_pull_request` etc.) is optional: when present, prefer it for the operations it supports (PR create, metadata reads, merge) and fall back to `gh` when it fails or is absent.
- **`jq` on `PATH` is required** — the same Phase 7 review loop parses `gh api` JSON responses with it throughout; `gh api`'s own `--jq` flag does not substitute for the standalone binary. Probe `jq --version` alongside the `gh` check; abort with install instructions if missing — not preinstalled on Windows (`winget install jqlang.jq`, or `choco install jq` / `scoop install jq`); usually already present on macOS/Linux (`brew install jq` / `apt install jq` otherwise).
- Record `REPO_ROOT` **first**, before loading config or invoking any skill: the first path listed by `git worktree list`, i.e. the **primary checkout** root, never a worktree path. (This recipe is correct from anywhere, including the no-arg resume path invoked from inside the ticket worktree, where `git rev-parse --show-toplevel` would wrongly return the worktree root.)
- `.claude/notion-dev.config.json` exists; load it. If missing, abort and tell the user to run `/notion-dev:init`. All config reads — here and in every later phase or invoked skill — resolve against the **primary checkout** (`$REPO_ROOT/.claude/notion-dev.config.json`), never the worktree: the worktree is cut from `origin/<git.baseBranch>`, which lacks the config whenever it is uncommitted, unpushed, or gitignored.
- The repo has an `origin` remote.
- The working tree is clean, OR the only dirt is exempt, OR the user is resuming inside an existing worktree for this ticket. Any other dirt: stop and ask the user to commit or stash first (non-interactive: stop and report) — and **when the dirt is untracked, say so and name `git stash -u`**, because plain `git stash` does not touch untracked files and a user who follows the bare advice hits this same abort on the next run. Measured twice in one client, on an untracked file belonging to an unrelated maintenance workflow. Report the offending paths from `git status --porcelain` either way: the remedy differs by dirt kind — commit or stash a modified tracked file, `-u` or remove or ignore an untracked one — and a gate that names neither the paths nor the right command makes the user guess at the one step that unblocks the run. **Exactly two kinds of dirt are exempt, and the list is exhaustive:** the init-generated setup files (`.claude/notion-dev.config.json`, `.mcp.json` — init's commit step is optional, and this command must stay usable when it was declined), and a **harness-managed local settings file** (`.claude/settings.local.json`), which the coding harness rewrites on its own — adding an MCP-enablement key, for instance — with no user edit involved. Both are exempt for the same reason: all implementation happens in a worktree cut from `origin/<git.baseBranch>` and config is read from `$REPO_ROOT`, so neither can contaminate the ticket branch. The second is not a courtesy — the file is tracked in some repos, so a literal reading of this precondition halts most non-interactive runs on a modification nobody made. Measured once in a client: the run proceeded, merged correctly, and the modification never reached the branch.
- `python3` in every `knowledge.py` line below stands for `knowledge.python` from `.claude/notion-dev.config.json` (default `python3`; `python` or `py -3` on Windows, as `/notion-dev:init` recorded).

---

## Phase 1 — Fetch and clarify

### 1.1 Fetch the ticket

Invoke the `notion-dev:ticket-system` skill, operation `fetchTicket(id)`, passing whatever was supplied — the page id/URL or logical key on a fresh run, or the numeric id on resume. The adapter accepts both. You get `{ title, key, body, status, url, metadata, type }`.

Derive the **numeric `<id>`** used for all naming below from `metadata.idProperty value` in the returned ticket. If the resolved page has no `idProperty` value, stop and tell the user the ticket DB needs an ID property — branch and worktree naming depend on it.

Record `TICKET_TYPE` from the returned `type` (the logical key, when the DB has a mapped type property) — it may be absent.

**Epic guard.** The fetched page is an epic container when the returned `metadata.parentTaskProperty` is `""` (empty) **and** `metadata.epicMarkerProperty` is `true` — the same predicate `findEpics()`, `getEpicContext` step 2, and `epic-update` step 1 apply (see "Epic containers" in `skills/ticket-system/references/create-ops.md`), so all four agree on what an epic is. In that case abort — an epic is a container, not implementable work:

```
[<KEY>-<n>] <name> is an epic container, not an implementable ticket.
Pick one of its children:
  [<KEY>-67] Fix stale index — Implemented
  [<KEY>-68] Add cache metrics — In Progress
```

Hard abort in both interactive and non-interactive mode. It runs before Phase 2, so no worktree, branch, status change, or ledger line is created.

A page carrying only the `Epic` select tag, with no `epicMarkerProperty` set, is **not** guarded here — even with an empty parent, and even if it happens to have picked up an ordinary Sub-items child. The marker, not the tag or the shape, is what makes a page an epic (see "Epic containers" in `skills/ticket-system/references/create-ops.md`); blocking on shape alone is the exact failure this guard used to have, since a legacy Epic-tagged ticket on an upgraded database can satisfy every structural signal an epic does. A freshly created epic with **zero** children **is** guarded here now — there is no child-count requirement left to exempt it. `metadata.epicMarkerProperty` reads `false` whenever `epicMarkerProperty` is unusable on the live DB — absent, **or present but not a Checkbox** type, which the "Marker usability rule" in `skills/ticket-system/references/create-ops.md` requires to behave identically — so the guard degrades safely to "not an epic" in either case rather than guessing from structure.

**Ownership check.** When the fetched status equals `statusMap.inProgress` (compare the live option name, never the literal) and no worktree of ours exists at the path 1.2 computes, abort: `[<key>] is In Progress and has no worktree here — held elsewhere`. Another session on this machine, or a person, has the ticket. Interactive mode may proceed on explicit confirmation via `AskUserQuestion` (the user is taking it over on purpose); for `held elsewhere` non-interactive mode never proceeds. In progress **with** our worktree is the resume case 1.2 handles.

**Epic context.** When `metadata.parentTaskProperty` is non-empty, invoke the `notion-dev:knowledge` skill, operation `retrieve(metadata.parentTaskProperty, <title>, <id>)`, and record the result as `KNOWLEDGE_CONTEXT` and `EPIC_CONTEXT` (its root), but **skip the fetch when the caller supplied `KNOWLEDGE_CONTEXT`** — `/notion-dev:next-task` passes it so the bundle is read once per run. It reads the epic's root concept and its linked concepts from `origin/<epicBranch>` under `knowledge.retrieveBudget` — **never the Notion epic page** — and `KNOWLEDGE_CONTEXT: unavailable` when `iwe` is missing. `<title>` and `<id>` are this ticket's own title and numeric id, both already derived above; when no brief exists yet, `retrieve` bootstraps one **in memory** (`BOOTSTRAP: true`), and this run's Phase 10 `record` step is what then creates the file. When `metadata.parentTaskProperty` is empty, or the call returns `null`, `KNOWLEDGE_CONTEXT` and `EPIC_CONTEXT` are both absent — every use of either below is skipped silently. Most tickets simply have no epic; on the rarer causes — `epicMarkerProperty` unusable on the live DB, meaning absent **or** present but not a Checkbox — the `fetchTicket` call this phase already made above recorded `missing-property:epicMarkerProperty` or `wrong-type:epicMarkerProperty` per `notion-dev:issue-log`, so nothing further is logged here (see the "Marker usability rule" in `skills/ticket-system/references/create-ops.md`).

`KNOWLEDGE_CONTEXT` and `EPIC_CONTEXT` are **background, not requirements**: the ticket body remains the single source of truth for what to build. Where either appears to conflict — an open thread or a recorded decision in the brief, or a stable concept the bundle carries, that the ticket now contradicts — the ticket wins, and the conflict is surfaced to the user at the 1.3 clarification gate rather than silently resolved.

Record `RUN_START` (`date -u +%FT%TZ`). `REPO_ROOT` was already recorded at the preconditions gate — before the first config read and ticket-system call, both of which depend on it; the ledger, per `skills/flow-triage/references/ledger.md`, likewise lives in the primary checkout it points to.

Announce to the user: "Working on `<key>`: <title>" (`<key>` is the `key` field returned by `fetchTicket`, e.g. `"STO-67"` — display it as-is, don't rebuild it from `project.key`). Show the ticket URL.

**Write the criteria file.** Write the ticket body's `## Acceptance Criteria` list — one criterion per line, verbatim, with the leading list marker stripped: `- [ ]`, `- [x]`, **or a bare `- ` bullet**. All three are reachable and stripping only the first corrupts the ticket. `refreshAcceptanceCriteria` (Phase 8) renders `- [x]` for every `met` criterion, so any ticket a completeness gate has already run against carries ticked boxes; and this command accepts any ticket, including a hand-authored one whose criteria are plain bullets. A criterion line that keeps its old marker still counts as one line, so the `CRITERIA-TOTAL` guard in Phase 8 does not fire, and the next `refreshAcceptanceCriteria` writes back `- [ ] - [x] <criterion>` — accumulating a marker per run and silently rewriting the ticket's own definition of done, the exact failure this whole path is built to prevent. Write it to `$REPO_ROOT/.claude/notion-dev/criteria-<KEY>-<id>.md`, in the self-ignored directory the ledger, the rescued `PLAN.md`, and the persisted review report already share (`mkdir -p` plus its `.gitignore`, commands in `skills/flow-triage/references/ledger.md`). Record the path as `CRITERIA_FILE`.

**Nothing is authored here.** The criteria come from Notion, which no part of this run can weaken — that is what makes them worth gating on.

When the body has no `## Acceptance Criteria` section, or it is empty, write no file and leave `CRITERIA_FILE` unset. `/notion-dev:create-task` guards against that state, but this command accepts any ticket and must not invent a definition of done for one that has none.

### 1.2 Check for existing worktree (resumability)

Compute the worktree path as `$(dirname "$REPO_ROOT")/<repo-name>-worktrees/<prefix>`, where
`<repo-name>` is `basename "$REPO_ROOT"` and `<prefix>` comes from the config template
`worktree.prefix` (tokens: `{name}`, `{key}`, `{id}` — `{id}` is the numeric `idProperty value`
from the fetched ticket). `REPO_ROOT` is the primary checkout recorded in 1.1 — not the current
directory, which on the no-arg resume path is the worktree itself.

**The `<repo-name>-worktrees` container is load-bearing, not decoration**, and it is what
`quick-dev:develop` has always used. Phase 9 step 5 removes "the worktrees parent directory" with
`rmdir "$(dirname <worktree-path>)"`. Without the container that `dirname` is the directory
holding the primary checkout itself — a path this flow neither created nor owns, and one that
can never be empty while `REPO_ROOT` sits in it, so the step is a guaranteed no-op that names the
wrong directory. `rmdir`'s refusal on a non-empty directory is the only thing that made that
safe. With the container, the step removes exactly what this flow created.

Before any resume decision that involves triage: read `$REPO_ROOT/.claude/notion-dev/ledger.jsonl` for the most recent decision line with `run_id == <KEY>-<id>` that lacks a terminal outcome. If found, reuse its `flow_chosen` as `FLOW` and skip Phase 3 entirely when resuming into the build phase. If no unresolved decision line yields a `FLOW` (e.g. an interleaved run's orphan sweep already closed it), do not guess — run Phase 3 normally on resume.

If the worktree already exists, read the run marker `$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json` (2.1 defines it) before anything else:
- marker `"state": "running"` and `heartbeat` younger than 2 hours (compared against `date -u` now — the marker stores UTC) → abort with `held by a live session — <phase> since <heartbeat>`. Interactive mode offers take-over via `AskUserQuestion` (claim it exactly as the resume branch below does — the same `mkdir` claim, the same fresh `session`, the same re-read — rewriting `session`, `phase` and `heartbeat`; `state` stays `running`, `worktree` and `branch` are unchanged by construction; a lost claim aborts there, writing nothing else, and nothing below runs); non-interactive never takes over.
- marker `stopped`, a heartbeat older than 2 hours, or no marker at all (a worktree from before markers existed) → resume, and claim the resume atomically before writing anything: `mkdir "$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.claim"` — the same atomic primitive §4's primary lock is built on. Create the parent `$REPO_ROOT/.claude/notion-dev/runs/` with `mkdir -p` first: it does not exist on a fresh install, nothing else creates it until the marker is written, and the claim would otherwise fail with `ENOENT` rather than because someone holds it. Never `mkdir -p` the claim directory itself — failing when it already exists is its entire value. A plain rewrite-and-read cannot stand in for it: two sessions that each write and then read their own write both see themselves and both proceed into one worktree.
  - `mkdir` fails → another session is inside this window: abort with `held by a live session — <phase> since <heartbeat>` exactly as above, writing nothing else, and **run none of the resume rules below**. Unless the directory is older than the same 2-hour threshold — a session that died mid-claim — in which case retire it **by rename**, exactly as `knowledge.py`'s stale break does and for the same reason: `rename` it to a unique name (atomic, so only one session can win the break), confirm the moved directory is still older than the threshold (rename it back and keep waiting when it is not), remove it, then `mkdir` the claim. Removing the pathname and retrying is the race this avoids — two sessions can both pass the age test, and the second's remove deletes the claim the first has just taken.
  - `mkdir` succeeds → **re-read the marker before rewriting it**, because the decision to resume was made from a read taken before the claim: another session may have held the claim in between, published a fresh marker and released it, and overwriting that now would put two sessions in one worktree while its own post-write re-read still succeeded. When the re-read marker is `running` with a heartbeat younger than 2 hours, or names a different `session` than the one this decision was made from, abort with `held by a live session — <phase> since <heartbeat>`, `rmdir` the claim, and run none of the resume rules below. Otherwise rewrite the marker as `running` with a fresh `session` for this invocation, re-read it, then `rmdir` the claim directory. Only when the re-read marker still names this `session` do the resume rules below run; when it no longer names this run (`session` differs), abort exactly as above, writing nothing else.

**A marker still reading `running` at this point is a mid-phase end, and is recorded.** Every stop path this command has writes `"state": "stopped"` with a `cause` (see "Failure and stop conditions"), so a resume that finds `"state": "running"` with a stale heartbeat means the previous invocation reached no stop path at all — it ended its turn mid-phase, or its session died. Record `unexpected:run-ended-mid-phase` per `notion-dev:issue-log` **before rewriting the marker**, carrying the marker's own `phase` as `Where` — that field is the whole diagnostic value, because it names where the run let go. A **missing** marker is not this condition (a worktree from before markers existed), and neither is `stopped`; only `running` is. This resume is the **only** place the condition is observable at all: a run cannot notice its own turn ending, so without this entry a non-interactive run that hands back mid-phase leaves nothing in the log and is visible only to whoever happens to look at the screen.

If the worktree already exists and the marker allows a resume:
- Announce: "Found existing worktree at `<path>`; resuming."
- **Worktree + `PLAN.md` with unchecked boxes**: this is the `FLOW=superpowers` path. Confirm via `AskUserQuestion` that the user wants to continue with the existing plan, then pick the resume point from the checkbox evidence — **never assume the plan was reviewed**:
  - **Some boxes already checked** — implementation began, so resume at step (d), `superpowers:subagent-driven-development`, from the first unchecked task, and do **not** run the plan review. For a run started on this version, reaching step (d) means the review and gate already cleared. For a worktree predating the review gate they did not — but the plan is already part-built, and `plan-review` has no way to review only the unchecked remainder: it judges the whole plan, so it could revise a task whose code has already shipped. That is worse than not reviewing. State plainly in the final report that this resumed plan was not reviewed by this version; Phase 7's review loop still examines the actual diff.
  - **No boxes checked at all** — there is no evidence the plan ever cleared review. The prior run may have stopped *because* the review returned `PLAN-REVIEW: blocked`, or been interrupted before step (b) ran at all. Resume at step **(b)** and run the review, gate, and build normally. Re-reviewing an already-approved plan costs one review; skipping review on a plan known to be Critically flawed is the failure this gate exists to prevent.
- **Worktree + `PLAN.md` with all boxes checked**: the build finished but the run was interrupted before ship (Phase 6.6 removes `PLAN.md` on a completed run). This is the `FLOW=superpowers` path. Confirm via `AskUserQuestion`, then resume at Phase 5 (verify) and continue the pipeline from there.
- **Worktree, no `PLAN.md`**: inspect state.
  - Commits ahead of base **and** an open PR exists for the branch → offer to jump straight to Phase 7 (or suggest running `/notion-dev:finalize <pr>` instead).
  - Commits ahead of base but no PR → ask (via `AskUserQuestion`) with three options: continue implementing (re-invoke the build flow with the existing diff as context), treat the implementation as complete (the build finished before the interrupt — resume at Phase 5 verify and ship; the feature-dev twin of the all-boxes-checked `PLAN.md` state), or start over.
  - Neither commits nor a PR → treat as fresh, but **reuse the existing worktree and branch**: skip 2.1's `git worktree add` (path and branch both exist — re-running it fails), `cd` into the existing worktree, run 2.1's status update (idempotent), and continue from there.

Otherwise, continue with a fresh setup.

Non-interactive mode: self-answer every resume question above with the most reasonable choice (continue existing plan / continue implementing) and log the decision.

### 1.3 Hard gate — requirement clarification

Read the ticket body together with `CLAUDE.md` at the repo root, any files the ticket references, and `KNOWLEDGE_CONTEXT` when present. The brief's open threads may already answer an open question on this ticket, and one of them may *be* the reason this ticket exists. `KNOWLEDGE_CONTEXT` is background, not requirements (see 1.1) — if a thread or decision in the brief appears to conflict with the ticket body, surface the conflict to the user at this gate rather than silently favoring the brief.

Ask yourself: do I understand the goal, scope, and acceptance criteria well enough to implement without guessing?

- **If yes**: proceed.
- **If no**: use `AskUserQuestion` for targeted clarifications. One question at a time; multiple choice preferred when the options are clear.
- **If severely under-spec** (missing goal or acceptance criteria, or the ticket is a one-liner): suggest re-running `/notion-dev:create-task <id>` to elaborate first; stop the current command.
- **If the requirement is clear but not satisfiable *now*** — every acceptance criterion gates on an event outside this run that has not happened yet (a customer-operated deploy, a human sign-off, an observation window still elapsing): **stop, and report it as blocked on a named external precondition — not as under-spec.** A watch ticket can be perfectly well-formed and still unbuildable, and the question this gate asks (*do I understand it well enough to implement without guessing?*) answers **yes** for one, so nothing above catches it. The distinction decides what the user does next: elaboration is the remedy for the bullet above and is useless here, so sending a well-specified ticket to `/notion-dev:create-task` costs a round trip and improves nothing. Name the precondition and what would clear it, exactly as a `blocked` disposition does everywhere else in this plugin — `blocked` is for a **named external cause**, and this is one. Measured twice in one client, on a ticket and its direct successor.

This gate is **blocking**. Do not proceed to planning until the requirement is unambiguous.

Non-interactive mode: if severely under-spec, stop and report — never guess requirements. Otherwise self-answer clarifying questions with the most reasonable interpretation and log the decision.

---

## Phase 2 — Isolate

### 2.1 Create the worktree

Compute the branch slug: kebab-case the ticket title (lowercase, non-alphanumerics → `-`, collapse repeats, trim leading/trailing `-`), truncate to 40 characters, trim a trailing `-` if truncation left one. The branch name is `ticket/<project.key>-<id>-<slug>` — e.g. `ticket/STO-11-identify-interfaces`.

```
git fetch origin
git worktree add <worktree-path> origin/<git.baseBranch> -b ticket/<project.key>-<id>-<slug>
```

Read values from config: `git.baseBranch`. The branch-name parser in the preamble already accepts this form, so `/notion-dev:ticket` called from inside the worktree (with no args) resolves the ID correctly.

**The claim is the worktree.** `git worktree add … -b ticket/<project.key>-<id>-<slug>` is atomic on one machine: when it fails because the branch already exists and 1.2 found no worktree of ours, another session claimed the ticket in the window between 1.2 and here. End the run with the outcome `claimed-elsewhere`: print one line, `OUTCOME: claimed-elsewhere — [<key>] branch ticket/<project.key>-<id>-<slug> already exists; another session holds it`, and stop **before** any status change, ledger line, or brief write. Nothing to clean but the `.claim` directory this path took, nothing to report beyond that line; `/notion-dev:next-task` reads this outcome and picks another ticket; it is a run outcome, recorded nowhere but this line and the caller's decision log — never an issue-log entry. A `git worktree add` failure for any other reason (path exists, fetch failed) is the ordinary stop.

**Run marker.** The fresh path takes the same claim 1.2's resume path takes, and takes it **before** `git worktree add`: `mkdir "$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.claim"` (the same protocol as there, parent-directory creation and the rename-based stale break included, with one difference in the outcome: on this path a lost claim is another session claiming the *same ticket*, so it ends as `OUTCOME: claimed-elsewhere` exactly like a lost `git worktree add`, never as 1.2's `held by a live session` abort — `/notion-dev:next-task` reads `claimed-elsewhere` as a tie and picks another ticket, while a generic failure stops its loop), released by `rmdir` after the marker below is written — and equally on **any** exit before that, the `claimed-elsewhere` stop included. A `git worktree add` that fails writes no marker, so a claim released only on the success path is orphaned there and blocks every later attempt until the 2-hour stale break. Without it the worktree is visible to another session before its marker exists, and a markerless worktree is exactly what 1.2 reads as a legacy resume: that session claims it, writes and verifies its own marker, and proceeds while this one — which took no claim and never re-reads — proceeds too, putting both in one worktree. Holding the claim across both steps closes that window: a second session either finds no worktree and loses `git worktree add`, or finds one and loses the `mkdir`. Right after the worktree exists, write `$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json` (create the directory; it lives under the self-ignored `.claude/notion-dev/`):

```json
{ "run": "<KEY>-<id>", "session": "<KEY>-<id>-<YYYYMMDDTHHMMSSZ>-<4 hex>", "worktree": "<worktree-path>", "branch": "ticket/<project.key>-<id>-<slug>",
  "phase": "Phase 2", "heartbeat": "<date -u +%FT%TZ>", "state": "running", "cause": null }
```

`run` names the ticket and is identical for every session of it, so it can never tell two of them apart; `session` is generated once per invocation — #44's token form, `$(date -u +%Y%m%dT%H%M%SZ)` plus 4 hex — and is the field 1.2's claim compares. Marker discipline for the rest of the run: rewrite `phase` and `heartbeat` at every phase boundary and every review round (Phase 7 says where), and after every build task and verify iteration; set `"state": "stopped"` with `cause` on the failure path, and delete the file in Phase 9 step 1 right after the worktree is removed. A JSON file this flow writes directly; no script. The marker is what tells a second session — and `/notion-dev:next-task` — whether this claim is live (1.2's rules). A heartbeat says *this run reached that boundary*, never *this run is alive right now*: it is written between units of work and never inside one, because a flow blocked in a dispatched build task, a running verify `cmd`, or a reviewer round cannot write anything until that unit returns. Those boundaries are the resolution of the signal, so 1.2's 2-hour threshold bounds the longest single unit rather than the run — it has to stay longer than any one build task, verify `cmd`, or reviewer round, which is what makes a stale heartbeat mean abandoned instead of busy.

`cd` into the worktree for all subsequent work.

**Gitignored local files are not carried into the worktree — recreate any a verify step needs.** A fresh worktree contains only tracked content, so a gitignored `.env.local` (or any similar local-only file) exists in the primary checkout and nowhere else, and a build or deploy target that reads one fails in the worktree while passing in the primary. **Recreate it from its committed example before treating the failure as a finding** — recorded twice in one client, where `make deploy-local` failed until `.env.local` was copied from `.env.example`. This matters for what the failure *looks* like, not just for the fix: it presents as a deploy regression in the branch under test, right before a merge gate, which is exactly the wrong conclusion to draw. A long-running local service the target expects (a node, a daemon) is the same class of gap and is likewise not a regression in the branch.

Mark the ticket as started — invoke `notion-dev:ticket-system`:

- `updateStatus(id, "inProgress")` — the ticket now stays in "In Progress" through triage, planning, implementation, and PR review. The plugin does not flip it to a further state until Phase 8. Idempotent on resume (re-running on an existing worktree is safe).

**Mark the brief — the `start` section.** When the ticket has an epic (`metadata.parentTaskProperty` non-empty) **and Phase 1.1's `read` did not report `BOOTSTRAP: true`**, from `$REPO_ROOT`:

`BOOTSTRAP: true` means no brief exists on `origin/<epicBranch>` yet, and `refresh` loads the current brief and has no missing-brief path of its own — so invoking it here would turn the first direct ticket run for a new epic into `EPIC-DOC: failed` and a `partial:epic-doc` record for a brief that was never supposed to exist yet. Skip the section, say so in the report, and leave it to Phase 10's `record`, which creates the brief with this ticket already resolved. Bootstrapping from here instead was considered and rejected: it would put a second brief-creation path in the flow, racing the one `record` already owns.

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section start --wait 600` — `<run id>` is `<KEY>-<id>`. Exit 1 → record `lock-timeout:primary` per `notion-dev:issue-log`, skip this section, and say so in the report; a `stale:` line → record `lock-stale:primary`.
2. Invoke the `notion-dev:epic-doc` skill, operation `refresh(<epic-id>, start <key>)`, passing `REPO_ROOT`, `<epicBranch>` and `LOCK_HELD`. It moves the ticket to the brief's `In progress:` line, repairs any drift 1.1's `read` reported, removes a stop bullet left by an earlier stopped run of this ticket, and commits `docs(epic): <KEY>-<n> start <key>` to `<epicBranch>` through the write path. Record its block as `EPIC_DOC_START`; `failed` → `partial:epic-doc`, never a stop.
3. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`.

The worktree exists before this section (2.1) and the status is set before it, so the claim precedes every mirror of it. The primary is clean by precondition on a fresh start; on a resume inside an existing worktree it may not be, and the write path then falls back to its branch assertion.

All subsequent file work happens in the worktree. Ledger writes go to `$REPO_ROOT/.claude/notion-dev/` — a sanctioned exception to the worktree-only rule, and a self-ignored directory that never appears in `git status`.

**Assert the primary checkout is unchanged after each build task.** Every clean-tree gate in this
flow inspects the **worktree**; none inspects `$REPO_ROOT`, so an implementer that writes to a
relative path resolved against the wrong root produces a modification no gate can see. After each
task, `git -C "$REPO_ROOT" status --porcelain` must still show exactly what preflight recorded —
nothing new. A new entry means the task wrote outside the worktree: report it with the path, and
do not treat the task as complete until the stray write is understood. Catching it here is the
difference between a one-line correction and an unattributable edit discovered after the worktree
that explains it has been deleted.

---

## Phase 3 — Triage

Touch the run marker: `phase` = "Phase 3", `heartbeat` = now.

Invoke the `notion-dev:flow-triage` skill via the Skill tool from inside the worktree with:
- always: `--ledger-root="$REPO_ROOT" --run-id="<KEY>-<id>"`
- non-interactive: add `--auto`
- `FLOW_OVERRIDE` set: add `--forced-flow=$FLOW_OVERRIDE`
- `TICKET_TYPE` known: add `--ticket-type=<TICKET_TYPE>`
- description argument: the ticket title, a blank line, then the ticket body — followed, when `KNOWLEDGE_CONTEXT` is present, by a blank line, a `--- EPIC CONTEXT (background, not requirements) ---` delimiter, and `KNOWLEDGE_CONTEXT`, so triage can tell requirements from background.

From its output block record `FLOW`, `MICRO_PLAN`, `SCOUT_FINDINGS` (sourced from that
block's `FLOW:`, `MICRO-PLAN:`, and `SCOUT-FINDINGS:` lines respectively). Triage owns its
own confirmation prompt, bug hard rule, ledger decision line, and degradation — do not
re-ask here.

If Phase 1.2 already resolved `FLOW` from an unresolved ledger decision on resume, skip this phase entirely.

---

## Phase 4 — Build

Touch the run marker: `phase` = "Phase 4", `heartbeat` = now.

From inside the worktree, follow the branch matching `FLOW`:

### 4.1 `FLOW=feature-dev`

Invoke `feature-dev:feature-dev` with the ticket body plus `MICRO_PLAN`/`SCOUT_FINDINGS` as seed context for its exploration/architecture steps, when available (they are absent when Phase 3 was skipped on resume). When `KNOWLEDGE_CONTEXT` is present, include it too as further seed context, labeled background, not requirements. Follow its full flow (explore → clarify → architect → implement → review).

### 4.2 `FLOW=superpowers`

(a) Invoke `superpowers:writing-plans`, passing the ticket body (the `Requirements` / `Acceptance Criteria` / `Context` / `Open Questions` sections — already a well-formed spec from `/notion-dev:create-task`) as the input, with these overrides (writing-plans honors a caller-supplied plan location):

- **Save location**: write the plan to `<worktree>/PLAN.md`. Do **not** use writing-plans' default `docs/superpowers/plans/...` path.
- **Feature name** for the plan header: `<KEY>-<id>: <title>`.
- **No execution handoff.** `superpowers:writing-plans` ends with an `## Execution Handoff` section that presents the user two execution options and asks "Which approach?". Suppress it — do not present it, and do not ask. This command already chose: step (d) below runs `superpowers:subagent-driven-development`, and step (b) runs first regardless. Writing the plan file **completes** this step; go straight to (b). The handoff is written for a standalone `writing-plans` invocation that has no caller waiting, and left unsuppressed it is a scripted turn-ending hand-back sitting in the middle of a flow that continues here — a question the non-interactive self-answer rule can answer without the run ever resuming, because what ends the turn is the offer, not the absence of an answer. Measured in a client: a `--non-interactive` run stopped at exactly this boundary.

When `KNOWLEDGE_CONTEXT` is present, also pass it — labeled explicitly as **background context, not spec**: writing-plans must not turn an open thread, a recorded decision, or a stable concept the bundle carries into a task. Only the ticket body is the spec.

Writing-plans produces a TDD-structured plan with bite-sized (2-5 minute) tasks, explicit file-by-file create/modify paths, and checkbox (`- [ ]`) tracking.

For tickets that are genuinely not TDD-shaped (docs-only edit, config bump, pure refactor with existing coverage), say so in the spec you hand to writing-plans — it will still structure tasks appropriately, just without red-then-green gating.

(b) Invoke `notion-dev:plan-review` — independent review of the plan before any of it is built.

**Reaching this step is itself the request for that agent — invoke the skill.** A standing rule of the shape *do not dispatch subagents unless the user asks for one* is already satisfied by reaching here, and is **not** grounds to skip the invocation. This clause exists because the skill's own equivalent (`plan-review/SKILL.md` Step 2) can only be read by a run that actually invokes it: a run that decides not to, right here, never sees it. Deciding the authorization question at this line, before the invocation, is the only place it can be decided correctly.

**Never review the plan yourself instead.** Whoever runs this command wrote the plan or ordered it written, so a self-review verifies nothing while producing something that reads like a verdict — the absence of the check, reported as the check. Only an instruction forbidding *this* dispatch counts as a prohibition (the user saying not to use subagents at all, or not for this review), or a harness that refuses the call outright; a general default is not one. When the dispatch is genuinely forbidden, `plan-review` emits `PLAN-REVIEW: degraded`, and the final report must say plainly that the plan went unreviewed.

Pass `--plan="<worktree>/PLAN.md"` (add `--auto` in non-interactive mode) and a context packet whose `INTENT:` block is the ticket body (the `Requirements` / `Acceptance Criteria` / `Context` / `Open Questions` sections), `SCOUT-FINDINGS:` and `MICRO-PLAN:` are the blocks recorded in Phase 3 — or `NONE — not available` when Phase 3 was skipped on resume — `VERIFY:` lists the `verify.steps` commands from config, and `EPIC-CONTEXT:` is `KNOWLEDGE_CONTEXT` when present or `NONE — not available` when absent, following the same convention as the other optional blocks — labeled as background, not requirements, so the reviewer never treats a resolution-log entry as spec. No `--spec-file`: the ticket body is the spec and travels inline.

It dispatches a fresh reviewer against the plan **and the codebase**, triages the findings, revises `PLAN.md`, and returns a `PLAN-REVIEW:` output block. Record the whole output block as `PLAN_REVIEW_REPORT` — `PLAN-REVIEW`, `FINDINGS`, `ACCEPTED`, `DECLINED`, `UNRESOLVED-CRITICAL`, `UNRESOLVED-REQUIRED`, `TRIAGE`, `DECLINED-WITH-REASONING`, and `UNRESOLVED` — for the ledger outcome and the ticket's `## Implementation` section (6.5). When the block reads `PLAN-REVIEW: degraded` — the reviewer never ran — record `retry-exhausted:plan-review` per `notion-dev:issue-log`. The revision preserves every `- [ ]` checkbox, so Phase 1.2's resume detection is unaffected.

**Non-interactive mode and `PLAN-REVIEW: blocked`** (≥1 unresolved Critical): stop the run per the command's failure handling, leaving the worktree, branch, and `PLAN.md` intact, and report the blockers. Do not implement a plan already known to be Critically flawed. `proceed-with-warnings`, `clean`, and `degraded` all continue — with any blockers logged for the final report.

(c) Hard gate — plan approval (**interactive only; skipped entirely in non-interactive mode**, where step (b)'s rule already decided — see 4.3). Present a short summary (not the whole file): what the review changed, what it declined and why (`DECLINED-WITH-REASONING`), and anything still unresolved. Ask `AskUserQuestion`: "Approve this plan, or revise?" Options:
- **Approve** — proceed.
- **Revise** — capture the user's feedback, edit PLAN.md, re-ask **this gate**. Do not re-invoke `notion-dev:plan-review`: it has already run, and human iteration is deliberately outside it. After each Revise iteration, refresh the recorded plan-review report before continuing: for every `UNRESOLVED` item record whether the revision addressed it, and recompute the status from what remains. Never carry pre-revision values into the ledger or the final report — a run whose blockers the user fixed at the gate must not be recorded as having proceeded past them, and one where the revision resolved nothing must not be recorded as clean. Write a status that only became clean through human revision as `clean (resolved at gate)`, so calibration keeps it distinguishable from a review that passed on its own.

Blocking when it runs. Do not implement without approval. When `PLAN-REVIEW: blocked`, say so plainly and make **Revise** the recommended option.

(d) Invoke `superpowers:subagent-driven-development` on `<worktree>/PLAN.md`. Touch the run marker (`heartbeat` = now) after every task it completes. It walks the checkbox-tracked task list writing-plans produced, running a fresh subagent per task with per-task review. Two scoping instructions for this delegation, kept from the prior single-flow command:

- **Tick the file checkboxes**: as each task completes, mark its `- [ ]` as `- [x]` in `PLAN.md`. This keeps execution resumable across sessions — if interrupted, the next run resumes from the first unchecked task (paired with the resume detection in Phase 1.2).
- **Stop before `superpowers:finishing-a-development-branch`**: do not let the delegation proceed into it. Ship, review, merge, and cleanup are owned by Phases 6–9 below, not by this delegation.

**If the user has explicitly disallowed subagents**, this delegation may substitute — as may Phase 8's record-unit dispatch, the same class for the same reason: its subagents buy context hygiene and throughput, not independence, unlike a review seat, which exists *for* independence and degrades instead. So execute the plan's tasks yourself in the plan's order, ticking each checkbox as it lands, and say so in the final report.

**"Explicitly disallowed" means an instruction aimed at this dispatch — not a general default.** A host-level or session-level rule of the shape *do not dispatch subagents unless the user asks* is satisfied by the user invoking this command, and does not reach this clause at all. Read narrowly, or the exemption swallows the rule.

**The review seats never substitute this way**, and the asymmetry is the point: this delegation's agents buy throughput, while the seats buy *independence*, which cannot be self-supplied. So on a genuine prohibition, plan review emits `degraded` (4.2b) and Phase 7's review loop **stops** rather than being replaced by your own reading. Skipping a seat is a reportable outcome; filling one yourself is not an outcome at all.

State the explicit deviations from stock superpowers when invoking, so the flows do not fight: skip `superpowers:using-git-worktrees` (Phase 2 already made the worktree); the end-of-branch review that `subagent-driven-development`/`finishing-a-development-branch` would normally run is not a substitute for Phase 7's review loop, which runs identically for both build flows.

### 4.3 Non-interactive mode and shared context

Non-interactive mode: every build-flow user gate (clarifying questions, plan approval, per-task review pauses) is self-answered with the most reasonable choice and logged for the final report.

Throughout execution, project context matters: `CLAUDE.md` at the repo root, existing sibling files, and any skill files under `.claude/skills/` describe conventions the implementation must follow. Ensure these surfaces are available to whichever build flow is running.

---

## Phase 5 — Verify

Touch the run marker: `phase` = "Phase 5", `heartbeat` = now.

### 5.1 Run verify

Iterate over `verify.steps` from config in order. For each step:
1. Run the `cmd`.
2. If it fails, attempt to fix and re-run.
3. Cap at `retries` attempts per step (default 3). If still failing, record `retry-exhausted:verify` per `notion-dev:issue-log`, then report to the user and stop.
4. Touch the run marker after every verify iteration.

### 5.2 Optional simplify

If the `simplify` skill or command is available in this environment, invoke it as a **non-blocking** pass: it may refactor for clarity, but if the verify suite breaks afterward, revert the simplify changes and continue. Correctness beats elegance.

---

## Phase 6 — Ship

Touch the run marker: `phase` = "Phase 6", `heartbeat` = now.

### 6.1 Plugin version bump

If `.claude-plugin/plugin.json` exists at the worktree root, the manifest `version` must change exactly once per `/notion-dev:ticket` run before the commit. All base comparisons in this step use `<PR_BASE>` = `git.prTargetBranch`, falling back to `git.baseBranch` — the branch the PR will actually merge into (6.4's target), which is where the version must be greater:

1. Skip only if the ticket's work already **increased** it: parse `version` from `git show origin/<PR_BASE>:.claude-plugin/plugin.json` and from the worktree manifest, and compare as semver. Strictly greater → the bump already exists; never double-bump. Equal, lower, or merely a reformatted line → not a bump; continue to step 2. (Compare the working tree, not committed history — at this point the ticket's edits may still be uncommitted.) If the manifest does not exist at the base — this run created the plugin — the manifest's initial version **is** the release version: skip the bump and record it as `new plugin @ <version>`.
2. Otherwise classify this run's change and bump semver accordingly: breaking behavior for existing users → **major**; new capability (command, skill, option, mode) → **minor**; fix, docs, refactor, internal-only → **patch**.
3. Record `old → new` and the classification; state it in the PR body (6.4) and the final report (Phase 10).

Non-plugin repos skip this entirely.

### 6.2 Commit

**Re-validate the branch before committing.** The branch/worktree decision was made back in Phase 1.2/2.1 and is never re-checked across the build — if another actor merges (and deletes) this ticket's branch while Phase 4 is still running, the working directory can end up back on `<PR_BASE>` by the time this step runs, and a commit here would land ticket work directly on the base branch:

```
git rev-parse --abbrev-ref HEAD
```

Must equal **the branch name recorded in 2.1** — never re-spell the `ticket/<project.key>-<id>-<slug>` template here: on a resume (1.2), 2.1 reused the branch already created by an earlier run, and its `<slug>` was kebab-cased from the ticket's title *at that earlier time*. If the title has since changed in Notion, re-deriving the slug from the current title produces a different string than the branch actually in use, and this check would misread a perfectly correct branch as a mismatch (recorded-name comparison and the `-D` in Phase 9 step 2 already follow the same rule for the same reason).

If the recorded branch name doesn't match, **do not commit yet** — but only apply the recovery below when the mismatch is **exactly** `<PR_BASE>` (the branch was merged/deleted externally mid-run, the case this check exists for). Any other value — a detached HEAD, or some unrelated branch — is a different failure mode this recovery does not cover: stop and report the actual branch/state rather than guessing, since the repoint below assumes specifically that `<PR_BASE>` is what was abandoned, and forcing it against an unrelated branch's stale position could discard commits that have nothing to do with this run.

When it is `<PR_BASE>`, **inspect what the checkout below would carry over before running it** — `git log --oneline origin/<PR_BASE>..HEAD`. Nothing in this command validates local `<PR_BASE>` at any earlier point (the clean-tree precondition checks whatever directory the command starts in, never this ref), so a commit sitting there could in principle predate and be unrelated to this run entirely. Every commit listed should be explainable as this run's own work (Phase 4/5's build, or an earlier pass of this same recovery) — if anything looks unrelated, stop and report the list rather than folding it into the ticket branch, since Phase 6.3 would then push it as part of this PR. When the list is clean, recover with:

```
git checkout -b <the branch name recorded in 2.1>
git branch -f <PR_BASE> origin/<PR_BASE>
```

The first line is a checkout, not a reset, so it changes nothing: this run's uncommitted work and any commits already sitting on `<PR_BASE>` from an earlier iteration of this same bug both carry over onto the new branch intact — `checkout -b` only adds a ref pointing at the current commit; it never touches the working tree or history. **Do not fold this into a `git reset --hard origin/<PR_BASE>` instead** — with the ticket branch just cut and now checked out, a hard reset runs against *that* branch (reset acts on whatever is currently checked out, not on the ref named in the command), silently discarding the very commits and working-tree changes this recovery exists to save. The second line is what actually repoints `<PR_BASE>` at `origin/<PR_BASE>` — safe specifically because `<PR_BASE>` was just abandoned by the checkout above and is therefore not checked out anywhere, and `git branch -f` touches only that ref, never the working tree, so it cannot disturb the branch just recovered. Without it, `<PR_BASE>` stays pinned at the same commit as the ticket branch, and once the PR is squash-merged that ref diverges from `origin/<PR_BASE>` in a way a later `git pull` there cannot cleanly resolve. If it fails (non-zero exit) — meaning `<PR_BASE>` turned out to be checked out in some other worktree after all — do not force it further: continue on the recovered branch and flag the discrepancy plainly in the final report (Phase 10) so it can be fixed by hand.

Exclude `PLAN.md` from the commit:

```
git add . ':!PLAN.md'
git commit -m "<type>(<scope>): <short summary> (<KEY>-<id>)"
```

Commit type follows Conventional Commits: `feat`, `fix`, `refactor`, `chore`, `test`, `docs`. Skip cleanly when the tree is already clean — `superpowers:subagent-driven-development` commits as it goes, so there may be nothing left to commit here.

### 6.3 Push

Push the branch created in 2.1:

```
git push -u origin ticket/<project.key>-<id>-<slug>
```

### 6.4 Open PR

**One pull request per ticket, and prefer one per session.** Every additional PR pays a whole `review-and-merge` cycle — its own reviewer trigger, its own multi-minute latency, its own merge and its own cleanup — and that cycle, not the coding, is the dominant cost of finishing. Before opening this one, check whether the session already has an open PR covering related work (`gh pr list --state open`); if it does and the work belongs together, push these commits to that branch and skip the create. A second PR is justified by a **technical** reason — a dependency that must merge first, a release boundary, or work the user asked to keep separate — never by a preference for small diffs, and never to carry an item this run itself filed. `review-and-merge`'s final sweep has already taken back everything cheap enough to keep, so a filed item that now looks worth doing is a signal the sweep mis-triaged it; say that in the report rather than opening a second PR for it. A direct user instruction overrides this, as user instructions always do.

Target: `git.prTargetBranch` (falls back to `git.baseBranch`).

Prefer the GitHub MCP tool `mcp__github__create_pull_request` when available; fall back to `gh pr create`.

**Pass a long PR body with `--body-file`, never `--body`, and never `@-`.** `gh pr create` does **not** support `@-` for `--body`: passed literally it becomes the *entire body* — two characters, **exit code 0, no warning** — and the prepared description is silently gone. `--body` with an inline string is barely better for anything multi-line, since backticks and newlines are mishandled.

**`--body-file -` is the correct spelling of what `@-` was reaching for**: `gh pr create --help` documents `-F, --body-file file` as *Read body text from file (use "-" to read from standard input)*, so a heredoc piped into `--body-file -` gives the same ergonomics `@-` promised and actually works. **Prefer it to a temp file.** A body file written inside the worktree is never committed and never cleaned up, so it sits as an untracked file — and `quick-dev:review-and-merge` requires `git status --porcelain` to be empty before it will start, which would stop every run before review. If you do use a file, put it outside the worktree and delete it after the read-back.

Then **read the body back and confirm a realistic length** (`gh pr view <pr> --json body`): the check is cheap, and it is the only thing standing between a silent truncation and a review window spent against a body nobody can see.

Measured in a client: a PR was created with a body of exactly `@-` and sat through **all three review rounds** with no description. Nothing false was published — the literal `@-` claims nothing — but the run's explicit "acceptance criterion 1 is unmet" disclosure, the one thing it most wanted a human to read, was absent for the entire review window and was caught only at the merge gate.

The MCP tool takes the body as a parameter and is not exposed to this failure; the rule binds the `gh` fallback path.

PR body structure:
- **Summary** — 1-3 bullets.
- **Ticket** — link to the ticket URL returned from fetchTicket.
- **Changes** — grouped list of files touched.
- **Test plan** — how to verify the change.

For plugin repos, add the version-bump line (`old → new`, classification) from 6.1.

### 6.5 Update ticket

Write a persistent `## Implementation` section onto the ticket so the ticket itself becomes a memory reference for what was built. Invoke `notion-dev:ticket-system`:

- **Do not change status here** — the ticket stays in "In Progress" through PR review. Phase 8 flips it to "Implemented" after the merge lands.
- `setPullRequest(id, <PR URL>)` — persists the PR URL into the dedicated `prProperty` column so the Notion DB stays filterable by PR. No-op when the DB has no such property.
- `upsertSection(id, "Implementation", { ... })` with this content:
  - **Plan** — a 2-4 sentence summary of the resolution approach, distilled from PLAN.md's Goal / Architecture / top-level Tasks. Not a copy of PLAN.md; a scan-readable overview. For the feature-dev path (no PLAN.md), distill this instead from the architecture summary feature-dev produced.
  - **Implementation** — what was actually done. Include: the ordered list of task headings completed, any notable decisions made during execution (e.g. a library chosen, a pattern introduced, an approach that replaced the planned one), and any deliberate deviations from the plan with the reason.
  - **Files Changed** — the list from `git diff --name-only origin/<PR_BASE>...HEAD` (6.1's `<PR_BASE>` — the branch the PR actually targets; `git.baseBranch` would misstate the PR's contents when `prTargetBranch` differs), grouped by directory — excluding `PLAN.md` if present: 6.6 removes it before review, so it never survives into the final PR diff even when an interim commit swept it in.
  - **PR** — the PR URL.
  - **Branch** — the branch name.
  - **Plan review** — `superpowers` path only, from `PLAN_REVIEW_REPORT`: the `PLAN-REVIEW` status, plus — when non-empty — the `UNRESOLVED` blockers the run proceeded past and the `DECLINED-WITH-REASONING` entries. Omit this bullet entirely on the `feature-dev` path, on a `degraded` review, and on a resume that skipped the review. This is the only durable home for that detail: `PLAN.md` is deleted in 6.6 and the ledger keeps only aggregate counts.
  - **Notes** — optional. Any caveats for the reviewer, plus the plan review's `TRIAGE:` **`file`** items with their criterion numbers, which otherwise die with `PLAN.md` in 6.6. The plan review's `absorb` items are **not** listed here: they were appended to `PLAN.md` as tasks and are already built, so they belong in the **Implementation** bullet above like any other completed work. Its `drop` items are listed with their rationale, so a reader can see what was considered and decided against.

This section is the single source of truth for "what did this ticket do?" — it survives even if the PR is later squashed or comments are lost. Phase 8 will append a separate `## Merged` section later; the two coexist.

Also call `postComment(id, <one-line PR URL + "ready for review">)` so watchers get a notification.

### 6.6 Remove PLAN.md

`FLOW=superpowers` path: `rm -f PLAN.md` at the worktree root (`-f` keeps the step idempotent when the file is already gone, e.g. on re-entry). Its durable summary now lives in the ticket's `## Implementation` section (6.5), and the worktree must be clean before entering Phase 7 — review-and-merge's clean-tree gate (`git status --porcelain` empty) would otherwise deadlock on the untracked file, and its `git add -A` fix-commits would sweep PLAN.md into the PR. After the `rm`, check `git status --porcelain -- PLAN.md`: a ` D` entry means an earlier commit swept the file in (`superpowers:subagent-driven-development` commits as it goes and doesn't know 6.2's exclusion rule) — commit the removal (`git commit -m "chore(<KEY>-<id>): remove PLAN.md" -- PLAN.md`) and push, or the same clean-tree gate deadlocks on the tracked deletion. This is why Phase 1.2's resume logic treats "worktree with no `PLAN.md` + open PR" as the jump-to-Phase-7 state.

`FLOW=feature-dev` path: no-op — there is no PLAN.md.

---

## Phase 7 — Review and merge

Touch the run marker: `phase` = "Phase 7", `heartbeat` = now.

**Closeout — completion pass, before the merge.** The review-and-merge skill performs the merge
itself, so its `--pre-merge-check` is the last moment a fix can still enter this pull request.
Always pass the **completion pass** of `notion-dev:session-closeout` there — on every repo,
plugin or not — appending the stale-bump clause below when the target repo is a plugin:
`--pre-merge-check "the completion pass of notion-dev:session-closeout must come back with no
unresolved tail: no uncommitted or unpushed work in any worktree this run owns, every FILED item carried in REVIEW_REPORT's FILED list with its criterion number, ready for the
record phase's epic-update to file — not its ticket URL, which cannot exist yet, the project's verification re-run and passing on this HEAD, and no unsupported
claim or unstated caveat left in the PR body — resolve anything it finds on this branch and push
before merging"`.

Invoke the `notion-dev:review-and-merge` skill via the Skill tool with args:
`<pr-number>`, plus `--non-interactive` when set, plus — when `CRITERIA_FILE` is set —
`--criteria-file "<CRITERIA_FILE>"`, plus — when the target repo is a
plugin (6.1 applied or verified a bump) — the stale-bump guard:
`--pre-merge-check "the manifest version in .claude-plugin/plugin.json on this branch
must be strictly greater, as semver, than in
git show origin/<the PR's baseRefName>:.claude-plugin/plugin.json (missing at base = new
plugin, check passes) — if equal or lower, the base moved: first update the branch
from the current base, then recompute the semver bump, commit, and push"`.

While it runs, touch the marker after every reviewer round it reports (its round log) — `phase` stays "Phase 7", only `heartbeat` advances — so a two-hour review does not read as an abandoned claim.

Remain in the worktree while it runs so review fixes land on the branch. It owns:
existing-comment processing, rounds with the configured code reviewer (Codex or Copilot,
resolved from `.claude/notion-dev.config.json`), the local fallback
(`notion-dev:local-code-review`), merge gates (including config `git.preMergeChecks`),
the merge itself per `git.mergeStrategy`, and remote branch deletion. Record its final
report (which loop ran, rounds, applied vs. declined) as `REVIEW_REPORT`.

Also record the completion pass's `CLOSEOUT:` block — printed when `notion-dev:review-and-merge` evaluated the `--pre-merge-check` above — as `COMPLETION_CLOSEOUT`, together with its `tracked:` and `blocked:` lines. Phase 10's `epic-doc` `record` step reads it; when the block cannot be found in this run's output, leave `COMPLETION_CLOSEOUT` absent rather than reconstructing one.

`REVIEW_REPORT` carries the skill's four triage lists verbatim — `ABSORBED`, `FILED`, `DROPPED`, `BLOCKED` — and they must survive the persist below intact. **Only the `FILED` list is passed to `notion-dev:epic-update`, invoked from inside the dispatched `${CLAUDE_PLUGIN_ROOT}/references/record.md`.** `ABSORBED` items are already merged, `DROPPED` items are already decided, and `BLOCKED` items cannot be worked by anyone until their named external cause changes; filing any of the three would recreate the non-convergence this split exists to stop. A `BLOCKED` item filed as a ticket is strictly worse than a forgotten one — it is a queue entry no future run can close, and it will be re-read as ordinary backlog once the cause is out of sight. Carry it to Phase 10 instead, where it becomes a `blocked:` line in the closeout.

Record the report's `COMPLETENESS-REPORT` section — `COMPLETENESS`, the four `CRITERIA-*` counts, `VERDICTS`, `CLAIMS`, `CAVEATS`, `TRIAGE` — as `COMPLETENESS_REPORT`, alongside `REVIEW_REPORT`. It is present regardless of whether `CRITERIA_FILE` was set — with no criteria file it reads `COMPLETENESS` as `clean`, `blocked`, or `degraded`, with `CRITERIA-TOTAL: 0`.

When that report
shows the local fallback ran because the configured reviewer was unavailable, record
`fallback:local-code-review` per `notion-dev:issue-log`.

Persist it: write `REVIEW_REPORT` to `$REPO_ROOT/.claude/notion-dev/review-report-<KEY>-<id>.md` (`mkdir -p` + self-ignoring `.gitignore` first — same self-ignored directory the ledger and the rescued `PLAN.md` live in, per `skills/flow-triage/references/ledger.md`, so it never appears in `git status`) **as the skill returned it, unedited — it already carries its own inline `COMPLETENESS-REPORT` section, and that is not a reason to strip it out first** — then **append** `COMPLETENESS_REPORT` a second time, under a `## Completeness` heading, purely so it is separately locatable: `/notion-dev:finalize`'s post-merge recovery path (its Phase 1 step 2) reads everything at or after that heading back out as its own `COMPLETENESS_REPORT`; everything before the heading is read back as `REVIEW_REPORT` regardless of whatever completeness content it already carries inline. This is what lets `/notion-dev:finalize`'s post-merge recovery path recover both deferred follow-ups and completeness verdicts if this run dies before Phase 8 completes. Best-effort, exactly like the existing write — a failure here never fails the run.

**Best-effort is not silent.** After the write, confirm **this run's** write landed — not merely that a file of that name is present. The path is deterministic per ticket and both entry points are re-runnable, so a stale `review-report-<KEY>-<id>.md` from an earlier run of the same ticket satisfies an existence test while this run's write failed: the failure is then neither logged nor reported, and the recovery path later consumes another run's review and completeness dispositions as if they were this one's. Confirm the write's own status, or read the file back and match it against the content just written. If it does not, record `unexpected:review-report-not-persisted` per `notion-dev:issue-log` and say so in Phase 10 — the run still continues. A persist that never happened and one that happened are otherwise indistinguishable afterwards, and the recovery path this file exists for will simply find nothing when it is needed most. Measured on `notion-dev` 0.20.2: BTC-Gateway STO-77 wrote no `review-report-STO-77.md` at all, on a run that filed three tickets, and no artifact anywhere records that it was missing.

---

## Phase 8 — Record

Touch the run marker: `phase` = "Phase 8", `heartbeat` = now.

**Resolve the interactive filing gate before the lock is taken.** In interactive mode, walk `REVIEW_REPORT`'s `FILED` list and put each item to the user with `AskUserQuestion` — File as ticket, or Drop with a rationale — and carry the answers forward as `FILING_DECISIONS`. A person deciding this can outlast the lock's 60-minute stale threshold, after which another run breaks a lock this one still believes it holds and both write at once. A non-interactive run files everything and has nothing to ask. This is the rule `/notion-dev:new-info` and `/notion-dev:knowledge curate` already follow — no interactive gate is ever held under the primary lock, which is what the stale rule assumes.

**The `record` section begins here and ends after Phase 10's `record`.** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section record --wait 3600` — `<run id>` is `<KEY>-<id>`. Exit 1 → stop per "Failure and stop conditions" with `CAUSE: primary lock held by <run> (<section>) since <time>`: cleanup cannot be skipped, so the run does not proceed without the lock. A `stale:` line → record `lock-stale:primary` and name the old owner in the report. Everything from here to the end of Phase 10's epic-doc step — `epic-update`'s rewrite of the Notion epic page, cleanup's checkout and pull of the primary, the post-merge hooks, and `record` — runs with the lock held, now inside the dispatched unit rather than directly here; the caller holds it across the dispatch and releases it after Phase 10's `record`, and tells the dispatched agent `LOCK_HELD: true` so it never takes it again. The section is bounded by the hour the lock's stale rule allows; a post-merge hook that cannot finish inside it must not be configured.

**Leave the worktree: `cd $REPO_ROOT`.** `${CLAUDE_PLUGIN_ROOT}/references/record.md`'s cleanup removes the worktree, and the orchestrator is normally sitting inside it.

**Compose the pre-dispatch draft report.** Phase 10's summary list below, minus every line that reads `RECORD_REPORT` — those describe work the dispatched unit has not done yet. Everything else is already known here: the flow chosen, the PR URL, the review summary, the plan-review outcome, the ticket end state, blocked items, non-interactive decisions, completeness. Carry it as `DRAFT_REPORT`. **This is not the final report** — Phase 10 composes that one in full, from this draft plus the `RECORD_REPORT` lines — but it is what `notion-dev:epic-doc`'s `record` operation reads inside the dispatched unit, and the unit cannot build it: it has no report of its own and no access to Phases 1-7. Without it the epic's brief loses `## Where we stand`'s ticket lines and `## Open threads`'s caveat sentences, silently, on every dispatched run.

**Dispatch one `general-purpose` agent, synchronously**, with a self-contained prompt carrying: the ticket id, the ticket body, PR number and URL, `$REPO_ROOT`, the worktree path, the branch name, `baseRefName`, `<merge-commit>` (the SHA `notion-dev:review-and-merge` returned), the merge strategy it used (`squash` / `merge` / `rebase`), `RUN_START`, `REVIEW_REPORT`, `COMPLETENESS_REPORT`, `PLAN_REVIEW_REPORT`, `COMPLETION_CLOSEOUT`, `KNOWLEDGE_CONTEXT`, `DECISIONS` (this run's non-interactive decisions), `DRAFT_REPORT`, the `CRITERIA_FILE` path, the run id, **the `session` token** — the run marker's `session` field, `<KEY>-<id>-<YYYYMMDDTHHMMSSZ>-<4 hex>`, which the unit keys its replay guards and hook checkpoints by and **cannot recover for itself**, because cleanup deletes the run marker before the hooks run — `FILING_DECISIONS`, `LOCK_HELD: true`, `--non-interactive` when this run has it, and the instruction to read `${CLAUDE_PLUGIN_ROOT}/references/record.md` and follow it exactly. Record its `RECORD:` block as `RECORD_REPORT`.

**That list is the unit's whole input, and every omission from it fails quietly.** A fresh agent can reach none of these on its own, and the unit's own text names each one: `<merge-commit>` hard-gates Phase 9's `git merge-base --is-ancestor` hook assertion and fills 8.3's `Merge commit` field, the merge strategy fills `Merge strategy` beside it, `RUN_START` is the ledger's `duration_minutes`, `KNOWLEDGE_CONTEXT` and the ticket body are the post-merge hook contract, and `DECISIONS` and `DRAFT_REPORT` are `epic-doc` `record` inputs. **`PLAN_REVIEW_REPORT` is the dangerous one**: the ledger reserves `null` in all four `plan_review_*` metrics for *no review signal*, so a unit never given it writes exactly the corruption that rule exists to prevent — indistinguishable afterwards from a `feature-dev` run or a reviewer that never ran. **Pass every name even when its value is absent, and say that it is absent**, rather than omitting the name: an absent value the unit was told about is a fact it can record; a name it was never given is a hole it cannot see.

**Reaching this step is itself the request for that agent.** A standing rule of the shape *do not dispatch subagents unless the user asks for one* is already satisfied by the user invoking this command, and is not grounds to skip the dispatch.

**Bound the wait at ~15 minutes** — the same bound `notion-dev:review-and-merge`'s checks gate, `notion-dev:plan-review` and `notion-dev:flow-triage` already apply, and for the same reason: a dispatch that never returns emits nothing, so no check written against a delivered result can ever fire. The tell is `ListAgents` reporting the same agent as "started <1m ago" on repeated checks. **The bound is on absence of progress, not on elapsed time, and when `git.postMergeHooks` is configured it is the `record` section's own hour rather than ~15 minutes.** That tell is what distinguishes the two: an agent restarting from the beginning is stuck, while one still inside a hook is working. A configured hook is an arbitrary skill that may deploy or publish, and the lock section above already budgets an hour for exactly that — so stopping it at 15 minutes would interrupt a legitimate deploy *and* leave it unfinished, because the `attempted` marker correctly stops the replay from re-running it. Keep ~15 minutes where no hooks are configured, since nothing else in the unit runs that long; where they are, extend to **~45 minutes — deliberately short of the lock's 60-minute stale threshold, not equal to it** — and stop earlier than either only on the stuck tell. **The margin is the point.** A bound *at* the threshold puts this run's cancellation at the same instant another run is entitled to break the lock as stale, leaving no room for the polling interval or for the pre-hook work that already consumed part of the hour; two runs would then mutate the primary checkout, Notion and the ledger together, which is the outcome the lock exists to prevent. A hook that cannot finish inside that margin must not be configured — the lock section above already states that requirement, and this bound is what enforces it rather than discovering it at the boundary.

**Validate the returned block before treating the dispatch as successful.** A fourth failure shape is a response that arrives and is unusable: truncated, or missing keys. Require every key of the `RECORD:` contract — `EPIC-REPORT`, `TICKET-RECORD`, `CLEANUP`, `CLEANUP-STEPS`, `HOOKS`, `EPIC-DOC-RECORD`, `EPIC-DOC-NEXT`, `ISSUES` — to be present before recording `RECORD_REPORT`. **A block missing any of them is a dispatch failure, not a partial success**, and takes the recovery path below exactly as a zero-byte one does. Without this the run walks on: Phase 10 renders absent fields as though the unit reported them, the lock is released, and cleanup or ticket recording can be silently unfinished with nothing saying so. An absent key and a key reporting `failed:` are opposites — the second is the unit telling you something went wrong, which is the contract working.

**On a failed, zero-byte, malformed, or timed-out dispatch: do not retry, and do not stop.** Record `unexpected:record-unit-not-dispatched` per `notion-dev:issue-log`, then **read `${CLAUDE_PLUGIN_ROOT}/references/record.md` and run it inline yourself**, exactly as `/notion-dev:finalize`'s `MERGED` post-merge recovery path does. **On the timed-out shape only, stop the dispatched agent and confirm it is no longer running before starting the inline recovery.** A failed or zero-byte dispatch has ended, which is what makes it safe to fall through; a timed-out one has **not** — the tell above is precisely that it is still going. Both executions carry `LOCK_HELD: true` for the same run, so the primary lock cannot serialize them: they would concurrently rewrite the epic page, update the ticket, remove the worktree, run the post-merge hooks, and append their own ledger lines. Stop it, re-check that it is gone, and only then read the file and run it yourself. If it cannot be confirmed stopped, do **not** start the inline recovery — stop the run per "Failure and stop conditions" with `CAUSE: record unit timed out and could not be confirmed stopped`, and the worktree intact for a person, because a second writer is worse than a late one. **This one stop is an explicit exception to the lock release, and it has to be stated because every other failure releases it**: the `record` section's own end and the stop path both run `lock release --run <run id>` on every failure inside the section. Here the child holds the same `<run id>` and was told `LOCK_HELD: true`, so releasing would let a *second* run take the lock while an unterminated agent is still writing Notion, git and the ledger — the exact interleaving the lock exists to prevent, arrived at by way of the lock. So **hold the lock** on this path: skip both releases, say in the stop report that the lock is deliberately still held and why, and name the run id a person must release by hand once they have confirmed the agent is gone. A lock held too long is visible and recoverable; one released over a live writer is neither. The work is idempotent and the fallback is the path that already exists; only this run's context saving is forfeited. Say so plainly in Phase 10's report.

**An explicit user prohibition on this dispatch takes the same inline path as a failed one.** Read `${CLAUDE_PLUGIN_ROOT}/references/record.md` and run it yourself, in the same order, with the same `FILING_DECISIONS` and the lock already held. Unlike the failure path, this is not a degradation: do **not** record `unexpected:record-unit-not-dispatched` — that signature means a dispatch that should have worked did not, and a user who declined subagents is not a degradation to log, only a preference to honor. Say plainly in Phase 10's report that the record unit ran inline at the user's instruction, so the missing context saving is legible rather than mysterious.

**Only an instruction aimed at this dispatch counts as that prohibition** — the user saying not to use subagents at all, or not for this one. A standing host- or session-level default of the shape *do not dispatch subagents unless the user asks* is already satisfied by the user invoking `/notion-dev:ticket`, and does not reach this clause. Read narrowly, or the exemption swallows the rule.

This is the reverse of Phase 7's reasoning, deliberately: there a lost dispatch costs the merge and has no fallback, so the skill is invoked in this context. Here — whether the dispatch fails or the user forbids it — it costs only the saving.

---

## Phase 10 — Report

**The `record` section ends here:** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>` — on this path and on every failure inside the section, before anything else is reported.

**Closeout — zero tails.** Before printing anything below, invoke the **workspace pass** of the `notion-dev:session-closeout` skill via the Skill tool and follow it exactly — its completion pass already ran before the merge, as that skill's "When to run" section requires. It enumerates loose ends from git, `gh`, Notion, and the draft report itself, and forces every one into `resolved`, `tracked: <url>`, or `blocked: <external cause>`. **Compose the full draft first, then run the pass over it, then send** — source 8 and the phrase check read the finished report, which does not exist any earlier, and nothing re-reads it afterwards. A tail found this way gets fixed rather than written down. Every `FILED` follow-up must come out of it as `tracked:` with its Notion ticket URL — a filed item named only in this summary is a tail, not a record. End the report with its `CLOSEOUT:` block verbatim, followed by any `tracked:` and `blocked:` lines; a report ending `TRACKED: 0` / `BLOCKED: 0` says the run is finished, with no trailing caveat.

Print a summary covering:
- Flow chosen (score/confidence/override, or the bug hard rule) and why.
- PR URL.
- Review summary — which loop ran (the configured code reviewer, Codex or Copilot, or the local fallback), rounds, applied vs. declined findings. When the local fallback ran, state prominently that no cross-model review validated the PR, and why.
- Plan-review outcome (`superpowers` path only) — status, findings, and accepted vs. declined counts from `PLAN_REVIEW_REPORT`. List any unresolved blockers the run proceeded past explicitly; a `proceed-with-warnings` run must not bury them. State `degraded` plainly when the reviewer could not run, and `skipped` when a resume bypassed the review.
- Ticket end state (`implemented`).
- Epic outcome, when the ticket had one: rendered from `RECORD_REPORT`'s `EPIC-REPORT` field — the epic's ID and URL, follow-ups absorbed, filed (with their IDs), and dropped, whether the epic closed, and **packets written vs. items filed** whenever `RECORD_REPORT`'s `ISSUES` field names `unexpected:followup-packet-missing`. Omit the line entirely when the ticket had no epic.
- **Epic doc**, when the ticket had an epic: `RECORD_REPORT`'s `EPIC-DOC-RECORD` field verbatim (`ok` / `skipped: <why>` / `failed: <cause>`), followed by its `EPIC-DOC-NEXT` field verbatim — the brief's `PATH:`, its outcome, and its `NEXT:` line, which is **the one place the run tells the reader what to do next**; on `failed`, the `CAUSE:` and the exact local commit left unpushed, which the closeout above forces into `blocked:` with that cause. Never summarise either field: the dispatched unit already reduced `EPIC_DOC_REPORT` to these two lines, and reducing them again leaves the reader nothing actionable. Omit the line entirely when the ticket had no epic.
- **Ticket record** — `RECORD_REPORT`'s `TICKET-RECORD` field whenever it is not `ok`: which of the Completeness block, the acceptance-criteria refresh, and the `## Merged` section was not written to the ticket, and why. Say nothing when it is `ok`. The ticket is the durable record — the PR is squashable and this summary scrolls away — so a half-written one is exactly the thing a reader must not have to discover from Notion later.
- **Blocked items** — every entry in `REVIEW_REPORT`'s `BLOCKED` list, each as `blocked: <item> — <external cause>; unblocked by <what>`, which is the closeout's own line format so the two records cannot drift. These are **not** tickets and must never be reported as though they were: no ID, no URL, no "filed". State the count alongside `FILED` so the two are legible against each other — a run reporting `FILED: 1  BLOCKED: 2` has pushed one piece of work forward and hit two walls, which is a different thing from filing three. Say nothing when the list is empty.
- Non-interactive decisions taken during the run, if any.
- Clean-workspace evidence, from `RECORD_REPORT`'s `CLEANUP` and `CLEANUP-STEPS` fields (worktree removed, branch gone locally and remotely, base branch up to date, or the `partial:`/`failed:` step and cause it names).
- **Run marker** — deleted (normal) | left `stopped` with the cause (stop path). Omit on `claimed-elsewhere`.
- Post-merge hooks: from `RECORD_REPORT`'s `HOOKS` field — which ran, or — when a Phase 9 hook assertion failed — that they were **skipped**, the branch the primary was actually on, and that they need a manual re-run. Omit the line entirely when `git.postMergeHooks` is empty.
- **Lock waits** — one line per section that waited: `waited <m>m for <run> (<section>)`; a broken stale lock: `broke stale lock held by <run> since <time>`. Omit the line entirely when no section waited.
- **Brief at start** — `EPIC_DOC_START`'s outcome (`refreshed` / `unchanged` / `failed` with `CAUSE:`) and its `DRIFT:` line when it was not `none`. Omit when the ticket had no epic.
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`, `<N>` summing this run's own writes (Phases 1-7) with the signatures named in `RECORD_REPORT`'s `ISSUES` field. Omit the line entirely when the run logged nothing.
- **Completeness** — say nothing when `CRITERIA_FILE` was unset (the ticket had no criteria to check). Otherwise: when `COMPLETENESS_REPORT` was absent or its `CRITERIA-TOTAL` didn't match `CRITERIA_FILE`'s line count, state that explicitly — the completeness gate produced no usable verdict for this record, and the unticked boxes are not a verdict — rather than saying nothing; an unchecked run and a clean `met` result must never render the same. Otherwise, when any criterion is not `met`: "<n> of <m> acceptance criteria were not met at the completeness gate" — `<n>` counts `not-met` criteria only — then each with its verdict, triage label, and rationale. State `CRITERIA-UNVERIFIED` separately whenever it is non-zero, as a third state never folded into `<n>`: `unverified` means the gate could not check, which is not the same as finding the work undone. Say nothing only when every criterion is `met`.

When `triage_reclassified` is greater than zero, state it in the report: "<n> of <m> `absorb` items were reclassified to `file` at the merge gate (criteria <list>)". This is worth surfacing every time it happens — an `absorb` item became a `file` item only because a criterion turned out true that the earlier triage missed, and a run doing that repeatedly is the signal the blast-radius test is miscalibrated. Say nothing when the count is zero.

---

## Failure and stop conditions

- 3+ consecutive verify failures with no progress → stop and report.
- > 15 files touched unplanned → stop and ask whether to continue or re-plan.
- Missing env vars or configuration → stop, never guess credentials.
- Any hard gate not passed → stop, do not proceed.
- **On any unrecoverable failure** (verify can't be made to pass, PR unmergeable, review loop stopped, unresolvable conflicts): STOP without running cleanup. Leave the worktree, branch, and PR (if one exists) intact for inspection. **Confirm each artifact exists at the moment you name it** — `git worktree list` for the worktree, `git branch --list` and `git ls-remote --heads origin` for the branch, a plain file test for `PLAN.md` — and report only what those reads actually return. A stop report is the one record a later resume trusts, and nothing contradicts it: measured in a client, a deliberate work-preserving stop asserted that a worktree, a branch and an 8-task `PLAN.md` were all intact when none of the three existed, and the plan was unrecoverable. A work-preserving stop is precisely when this claim is most load-bearing, which is why it is the one that must be read rather than remembered. **Copy `PLAN.md` out before stopping — copy, never move.** Write it to `$REPO_ROOT/.claude/notion-dev/PLAN-<KEY>-<id>.md` (creating that self-ignored directory first, per `skills/flow-triage/references/ledger.md`) so a plan survives a worktree that does not, **and leave the worktree's own `PLAN.md` exactly where it is**. This path leaves the worktree intact by design, and 1.2's resume detection reads that file and its checkboxes to decide where to resume — moving it would make a stopped superpowers run look like a fresh one, re-authoring a plan that exists or losing a part-built run's task-level resume point, and nothing on the resume path ever restores the rescued copy. `/notion-dev:finalize` moves rather than copies for a reason that does not apply here: its review loop's clean-tree gate requires the worktree clean, so there the file has to leave. The copy is a **snapshot for the case where the worktree is gone**; whenever the worktree still has `PLAN.md`, that one governs and resume must read it, never the rescue. Then report the exact remaining state (worktree path, branch name, PR number if any) and the exact commands to resume or clean up manually — including `/notion-dev:finalize <pr>` when a PR exists. Best-effort, before stopping: append a ledger outcome line with `result` `"failed"` (unrecoverable failure) or `"stopped"` (user abort) and `null` metrics — **except** the `plan_review_*` fields, which carry their real values from the plan-review output block whenever the review ran. A `blocked` exit is the single most valuable case to calibrate on, and the schema reserves `null` for *no review signal*, which is not what happened here — never let ledger bookkeeping mask the real failure report. Also best-effort, before stopping: run the issue-log sweep from Phase 9 — this path skips Phase 9 entirely, and an unrecoverable failure is the single most valuable thing this log can record. A failure to write it never masks the real failure report. Also, always: rewrite the run marker with `"state": "stopped"` and `cause` set to the one-clause cause in the stop report, leaving `worktree` and `branch` in place — 1.2 and `/notion-dev:next-task` read `stopped` as resumable. The Notion ticket stays "In Progress" — no failure status is ever written to Notion.

Also best-effort, before stopping, when the ticket has an epic — the `stop` section: confirm the primary is clean outside the exempt paths (`git -C $REPO_ROOT status --porcelain`), else skip with `brief not marked: primary checkout dirty` in the stop report; `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section stop --wait 600` (exit 1 → skip, `lock-timeout:primary`); invoke the `notion-dev:epic-doc` skill, operation `refresh(<epic-id>, stop <key> <phase> <cause> <worktree-path>)`, with `REPO_ROOT`, `<epicBranch>`, `LOCK_HELD`, `<phase>` the phase that failed, `<cause>` one clause, `<worktree-path>` from 1.2/2.1 — it writes the stop bullet, moves the ticket to `Blocked:`, and commits `docs(epic): <KEY>-<n> stop <key>`.

Then `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`. When the failure happened inside the `record` section, that section's release runs first, and this one takes the lock afresh. Print the `EPIC-DOC:` block in the stop report.
