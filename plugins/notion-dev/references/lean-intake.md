# Lean intake — shared by ticket and finalize

Read only at intake/resume. Commands use the primary checkout's config; `python3` below
stands for its `knowledge.python` executable (`python` / `py -3` on Windows). Use Git Bash,
UTF-8 and LF on Windows and Ubuntu/WSL2. Never rewrite provider/host settings to make a run pass.

## Preflight

Resolve the primary checkout from the first `git worktree list --porcelain` entry. Read its
config to obtain the interpreter, then run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" preflight --project "$REPO_ROOT" --non-interactive
```

Omit the flag for interactive runs. Save the returned `marker`, `runtime`, `invocation` and
`root`; the helper creates the ignored local directory and session-owned preflight marker
before checking config/cleanliness. It preserves pre-existing changes. Missing session ID
means no Stop-hook protection; say so. Missing config means run init, not invent defaults.
Do not leave a running preflight marker on an abort: use `workflow.py marker --path <marker>
--phase <phase> --status stopped --cause <actual-cause>` before ending the turn.

Probe `gh auth status`, `jq --version`, Git origin and the configured interpreter. The lean
flow has no Superpowers/feature-dev dependency. Verify external skills only for an explicit
legacy override, using `references/dependencies.md`. Missing tools stop with install/auth
guidance; do not install or modify credentials automatically. `iwe >=0.19` is needed for
knowledge operations: missing/unavailable knowledge is reported, never silently replaced by
an invented brief. Installation alternatives include `cargo install iwe --root ~/.local`
(Ubuntu 22.04/older GLIBC), `brew install iwe`, or `npm i -g @iwe-org/iwe` where supported.

## Fetch authoritative intent

Use ticket-system `fetchTicket` with the numeric key, page ID or URL. Missing argument means
infer the ticket from an owned ticket branch; otherwise ask. Derive numeric ID from the
configured id property, not the title. Missing ID is a stop. An empty parent relation AND
true epic-marker checkbox means this is an epic: direct the user to next-task, do not implement
the container. Load the skill's operation reference before using it.

Save the full ticket source and metadata under the invocation directory. A next-task source
may be reused only after identity and revision/freshness checks; live status and ownership
are still checked before a write. Requirements come from this ticket, not from a knowledge
bundle or epic recommendation. Check `## Blocked by` references against live resolved statuses.
An in-progress ticket without our worktree is held elsewhere; do not claim it.
Already resolved tickets are not reopened implicitly. If a ticket already has an OPEN or
MERGED PR, use finalize for that PR instead of opening another implementation branch.

On schema 5, after `init`, run `capture-ticket --page <notion-page-uuid>
--config <primary-config>` using runtime.py. SessionStart supplies `NOTION_DEV_TRANSCRIPT` and
`NOTION_DEV_SESSION_ID`; an explicit actual --transcript/--session is supported when needed.
The helper selects the actual call ID, extracts the complete host response and generates ticket.md. Never transcribe the
response, invent a call ID, or patch/copy an old capture. If the completed exchange has not yet
been flushed to the host log, wait for that existing delivery and retry capture, not the fetch.
Unsupported/missing host evidence stops explicitly. Load only the intake protocol with
`workflow.py guide --stage intake` (the Requirements and evidence / Actual host captures
sections of runtime.md and boundaries.md), not their later review/record sections.
Existing schema-4 runs keep `ticket-source --response <capture.json> --config <primary-config>`.

Use already-retrieved ticket-scoped context if available, otherwise knowledge
`retrieve(<epic-id>, <ticket-title>, <ticket-key>)` once AFTER selecting the ticket. A scheduling
brief is not a knowledge retrieval. Load only retrieve's operation reference, not capture/migrate. Save
paths for relevant architectural constraints/history. Only fetch deeper documents to answer
a named question. Do not eagerly read every sibling ticket or the whole epic body.

Resolve ambiguity before implementation. Interactive: batch genuinely blocking questions.
Non-interactive: make evidence-backed implementation choices, but never invent a prerequisite,
approval or credential. Preserve external blockers and stop if mandatory readiness is unknown.
Extract every mandatory requirement, constraint, prerequisite and AC into the runtime inventory
as that intake guide specifies; record release-only obligations without treating an
explicitly optional sign-off branch as a new merge prerequisite. Run `requirements` and `ready`.

**Declared folds.** For a ticket under an epic, run `references/scope.md`'s intake fold scan
(one search for this key, fetch only its hits, `workflow.py fold-scan`) before planning; absorb
every declared sibling or record why not.

**Premises first.** When the ticket has a `## Premises to verify` section (follow-ups carry one),
`ready` stays false until each premise is checked against the code, before planning: write
`[{"text": "<premise verbatim>", "verdict": "holds|false|moot", "evidence": "<file:line or
command output>", "correction": "<what is actually true>"}]` and run `runtime.py premises
--checks <file>`. A `false` premise is corrected as a ticket comment (the frozen text stays
untouched) and stated in the PR. A `moot` verdict — a false premise that makes the ticket
pointless — stops the run with a `drop` recommendation instead of building. The `## Hypothesis
— verify before implementing` section is a lead, never a requirement.

## Resume or claim

Start a resume with `workflow.py resume-view --state <existing-state> [--worktree <path>]`.
This read-only index references full evidence and identifies outstanding work; it is not an
authorization or a replacement requirement inventory. Preserve the runtime, not the whole chat.
After a long interruption in a large conversation, recommend a fresh conversation running
`/notion-dev:finalize <pr>` with this runtime path. Do not automatically spawn a replacement,
abandon live workers, or replay an old approval. If this host cannot safely switch sessions,
continue with scoped retrieval or explain the handoff; no user-created test project is needed.
Read the retained compact context and full current ticket; retrieve specific evidence as needed.

Inspect `.claude/notion-dev/runs/<key>.json` before initializing a new ticket runtime. Reuse its
runtime on a lean resume, including attempt budgets, receipts and journal. Refresh the source/
inventory there only after resolving its old workers. A pre-0.36 run reads the legacy ticket
reference and keeps its own state. Never adopt a running marker merely because a heartbeat is
old: confirm its workers stopped and obtain takeover authority first. Do not auto-stash edits.
For a schema-5 takeover, the authorized claim/resume-pr transfers host-session ownership using
the retained readiness state first; then capture the new full source and re-establish readiness
before any implementation/review or Notion write. Do not capture under the old session identity.
Regenerate resume-view after adoption. Approval is host-session/head/input bound, so a new session
must obtain its own challenge/approval when required; it never receives a fresh default budget.

Fresh runs initialize the returned runtime with `init --run <invocation> --ticket <key>`.
After readiness, claim with:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" claim --project "$REPO_ROOT" --preflight "$RUN_MARKER" --ticket <key> --title <title> --state "$RUNTIME_STATE"
```

On an explicitly resolved lean resume add `--resume`. The helper serializes the claim with a
kernel lock, checks ownership again, creates the worktree on a fresh branch, writes
the ticket marker and retires the preflight marker. Save its returned paths, especially the
possibly resumed runtime. A failed claim creates no Notion status change. Report
`OUTCOME: claimed-elsewhere` only when evidence actually establishes competing ownership.
If Git succeeded but marker publication failed, preserve the worktree and inspect the partial
claim; do not overwrite it or assume the multi-step operation was transactional.

Work only in the returned worktree. Compare the primary checkout with its preflight status
after implementation boundaries; a new edit there is a wrong-root error, not permission to
discard or sweep it into a commit. Initialize dependencies and local config from committed
examples as needed; missing ignored config/services are environment gaps, not code regressions.
Do not copy secrets into logs or commit runtime artifacts.

Through ticket-system set `inProgress` and the started/branch record; use configured mappings.
For an epic, refresh its start brief under the existing `knowledge.py lock` start section,
passing `LOCK_HELD: true`; release afterwards. Resolve interactive choices before taking locks.
Use the lifecycle retrieval planner inline; do not dispatch another epic/dependency agent.
If that advances the base, fetch and fast-forward a clean fresh ticket branch before coding.
Never reset a resumed branch. A brief refresh failure is reported without claiming it succeeded.

## Boundaries and stop

At each stage run `runtime.py stage <name>` and `workflow.py marker --path "$RUN_MARKER"
--phase <name>`. The raw `NOTION_DEV_SESSION_ID` identifies ownership; do not sanitize its value
or use an unrelated ambient Claude variable. For worker waits use runtime's one-shot yield.

On a stop, preserve existing work and owned artifacts, update the marker with cause, and give
the actual resume command plus runtime path. For a long/large-context run, explicitly tell the
user to run that command in a fresh conversation after workers/ownership are settled; give this
handoff BEFORE a long user wait, not only after the old history has already been re-cached.
Do not change Notion to a failure status. A held primary lock must
not be released while any record writer could still run; never create a replacement writer
to recover a missing report. `finalize` on a MERGED PR uses recording recovery only.
