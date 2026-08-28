---
name: review-and-merge
description: This skill should be used when the user asks to "review and merge" a pull request, "merge PR after review", "run the review loop on PR", "drive PR to merge", or when /notion-dev:ticket reaches its review phase or /notion-dev:finalize runs. Resolves existing review comments, loops the configured code reviewer (Codex or Copilot) — falling back to a local fresh-agent review loop when the reviewer is unavailable (quota, not configured, erroring, or silent) — then merges (per the configured strategy) and deletes the remote branch.
argument-hint: "<pr-number> [--non-interactive] [--pre-merge-check \"<requirement>\"]"
---

# review-and-merge

Drive a pull request to a clean, merged state: resolve existing review feedback, run repeated review rounds until no meaningful issues remain, merge (per the configured strategy), and delete the remote branch. Local branch/worktree cleanup is the caller's responsibility (the calling command handles it in its flow).

## Input

Arguments: `$ARGUMENTS` — the PR number, plus optional `--non-interactive`, plus optional `--pre-merge-check "<requirement>"` — a caller-supplied condition (with its remediation) that must hold immediately before the merge command runs; see step 5 — plus optional `--criteria-file <path>`.

`--criteria-file <path>` names a file holding the run's acceptance criteria, one per line, verbatim in their authoritative wording. It feeds the Completeness gate in `## 5. Merge`. **When it is absent** — a manually opened PR, or a ticket with no `## Acceptance Criteria` section (or `finalize` reached with no recoverable ticket body) — the gate still runs its claim and caveat charges and reports `CRITERIA-TOTAL: 0`. It degrades; it never becomes a hard failure, and it must never report criteria as met when it had none to check.

Interactive mode (default) pauses for user input at exactly two points: (a) before merging while findings remain that were disagreed with or could not be addressed (round cap or oscillation guard), and (b) when a review suggestion conflicts with the PR's stated intent and both readings are defensible. With `--non-interactive`, never pause — resolve those calls autonomously and log them in the final report.

If no PR number is given, stop and ask for one. Do not guess.

All GitHub interaction uses the `gh` CLI against the current repository. Run `gh pr view <pr>` up front to confirm the PR exists, is **open**, and is not a draft. If closed/merged/draft, stop and report.

**Requires the standalone `jq` binary on `PATH`** — this skill pipes `gh api` output through it throughout (thread mapping, author filtering, review-id reconciliation); `gh api`'s own built-in `--jq` flag does not substitute for it. Probe with `jq --version` before step 1. If missing, stop and report install instructions rather than proceeding into a loop that would fail opaquely partway through: macOS `brew install jq`; Debian/Ubuntu `apt install jq`; Windows `winget install jqlang.jq` (or `choco install jq` / `scoop install jq`).

## Reviewer

This skill drives one of two configured reviewers. Resolve which **before step 3**:

1. Read `reviewer` from `.claude/notion-dev.config.json` (primary checkout).
2. If the file has no `reviewer` key (e.g. a project configured before this field existed),
   resolve one **for this run only**: in interactive mode, ask via `AskUserQuestion` —
   "Which code reviewer should the review loop use?" (**Codex** / **Copilot**) — and tell the
   user the choice applies to this run; to persist it, re-run `/notion-dev:init` (which writes
   `reviewer` to the config). In non-interactive mode, default to `codex` and note in the
   report that the choice was resolved but **not** persisted. Carry the value forward in memory.

   **This skill never writes `.claude/notion-dev.config.json`.** Persisting the reviewer key
   is `/notion-dev:init`'s job, not the review loop's. The config lives on the primary
   checkout ($REPO_ROOT, the base branch), where the caller later runs `git pull origin <base>`
   during cleanup; a mid-run config write there would dirty or diverge that checkout, and a
   write on the PR branch would inject an unrelated config commit into the PR. Resolving in
   memory keeps the loop side-effect-free and sidesteps both hazards.
3. Bind the **reviewer profile** below; every trigger / re-trigger / reviewer-response /
   unavailability reference in steps 3–5 means the bound profile's row.

| aspect | **codex** | **copilot** |
|---|---|---|
| trigger | comment `@codex review` | request the bot reviewer: `gh api --method POST "repos/{owner}/{repo}/pulls/<pr>/requested_reviewers" -f 'reviewers[]=copilot-pull-request-reviewer[bot]'` (gh substitutes `{owner}`/`{repo}`) |
| re-trigger each round | re-comment `@codex review` | re-run the same reviewer-request command (the bot is auto-removed once it submits) |
| response author | `chatgpt-codex-connector[bot]` on every surface | **one bot, two logins**: `copilot-pull-request-reviewer[bot]` on the **review** object, `Copilot` on that review's **inline comments** — same `user.node_id`. Accept **either** login; matching one alone silently drops half the review (see step 4) |
| review shape | `COMMENTED` review; actionable findings are inline threads (+ a summary body) | `COMMENTED` review whose findings are **often in the summary body only** — Copilot frequently generates zero inline comments, withholding low-confidence findings into a `<details><summary>Suppressed comments (N)</summary>` block in the body instead, so the body is a first-class finding source; inline threads appear only when it has line-level findings |
| non-actionable boilerplate to ignore | Codex "About" block | **exactly two things**: the "Reviewed changes" per-file summary table and the "Add Copilot custom instructions" footer. A `<details><summary>Suppressed comments (N)</summary>` block is **not** boilerplate — despite also being a `<details>` block it carries real findings, and is triaged like any other finding |
| "no meaningful issues" | review says no major issues / equivalent | the body carries no actionable findings, **no** `Suppressed comments (N)` block with N ≥ 1, and there are no (or only resolved) inline comments. The headline "generated no new comments" is **not** sufficient on its own — it co-occurs with a populated suppressed-comments block |
| not-configured signal | a message from the Codex app that is *exclusively* an inability-to-review notice (no `Reviewed commit` marker, no findings) | a **permanent rejection** of the reviewer-request: a `422`/`403`/`404` whose **message** says Copilot review is not enabled. Status alone is never enough — GitHub documents `422` on this endpoint as "Validation failed, or the endpoint has been spammed". Transient statuses (`500`/`502`/`503`/`429`, rate-limit `403`, spam-protection `422`) and bare transport errors are **not** signals — retry them (step 3) |
| quota signal | body contains the case-insensitive substring `reached your codex usage limit` | n/a — Copilot has no comment-based quota notice; a persistent GitHub *rejection* is treated as `not-configured` |
| silence | no response within ~10 min (20×30s polls) → confirm the request is really gone (definite re-read), then re-trigger once → `reason=silent` | same window, but **never re-trigger while the pending-request check (`references/github-api.md`) still shows the bot outstanding** — it is slow, not silent (latency of ~16 min observed); keep polling to a ~30-min bound. Do **not** use `gh pr view --json reviewRequests` for this — it has been observed empty while the request was genuinely live |

### Round cap

Both review loops in step 4 are capped by `reviewsCap`, read from
`.claude/notion-dev.config.json` in the **primary checkout** (`$REPO_ROOT`, resolved as every
other config read in this skill — never the worktree). Resolve it **once**, here, before the
first trigger:

- The value is an integer ≥ 1 → use it.
- The key is absent, the file is missing, or the value is anything else (`0`, negative,
  non-integer, non-numeric) → use **15**. When the value was present but unusable, say so in
  the final report; never stop the loop over it.

The resolved number caps the reviewer loop and the local fallback loop **independently** —
the fallback restarts its counter at 1, so a run that falls back can perform up to twice the
cap in total. As with `reviewer`, this skill never writes the config: `reviewsCap` is
hand-edited, and `/notion-dev:init` does not write it either.

Copilot round-trip latency has been observed in the 3–20 minute range per round (mostly 15+),
so the default cap of 15 is a many-hour worst case if every round produces a code change. The
judgment-based stop ("no meaningful issues" / theoretical-only findings, step 4) is the loop's
real brake — the cap is only a runaway backstop. For a PR with little or no code (docs-only,
config-only), consider hand-setting a lower `reviewsCap` before starting the run.

## 1. Load the pull request

- `gh pr view <pr> --json number,title,body,state,isDraft,mergeable,mergeStateStatus,headRefName,baseRefName,reviewDecision,statusCheckRollup,url` (`body` is required later: the local fallback reviewer judges the diff against the PR title and body)
- Fetch all existing review comments with `--paginate` (inline comments, review summaries, issue comments) and the review-thread resolution state via GraphQL — exact commands, the thread query, and the pagination rules are in **`references/github-api.md`**. Read it before the first API call; the pagination and thread-mapping rules there are load-bearing (unpaginated reads silently miss comments; REST alone cannot resolve threads).
- Ensure the PR branch is checked out locally so fixes can be applied: if the current directory is already on `headRefName` (the calling command's worktree), stay there; otherwise `gh pr checkout <pr>`.
- Require a clean working tree before proceeding (`git status --porcelain` empty): review fixes are committed with `git add -A`, which would sweep pre-existing uncommitted changes into the automated commit and push them. If dirty, stop and ask the user to commit or stash first (non-interactive: stop and report).
- Push any local commits the remote is missing before processing anything: if `git rev-list --count @{upstream}..HEAD` is non-zero (e.g. a prior run committed fixes but its push failed), `git push` first — otherwise the already-replied skip path could resolve threads and merge while the remote head lacks those fixes.

## 2. Process existing review comments

**Before touching any comment**, run the green-CI gate: `gh pr checks <pr>`. If any check is **failing** (not merely pending), fixing it is the first priority — diagnose, push a fix, wait for green. Never process review feedback while a check is red. In this and **every** green-CI gate in this skill (start of each reviewer round, local-loop step 1): `gh pr checks` exiting non-zero with `no checks reported` means the repo defines no checks — the gate passes; treat only actually failing checks as red (same caveat as the step-5 merge gate).

Handle all review feedback with the `superpowers:receiving-code-review` skill (from the required superpowers plugin) — verify each point against the code with technical rigor; no performative agreement, no blind implementation.

**Apply judgment — do not apply a change you are not confident improves the code.** Every review comment (bot or human) is a suggestion to evaluate, not an order to follow. The bar to apply is affirmative: you must be able to state why it's an improvement for THIS codebase. If unsure — or it's cosmetic churn / speculative / unverifiable / an equivalent-wording swap — do not apply it; reply with your reasoning (ask the user for anything contentious; non-interactive: decide autonomously and log it in the final report) and leave it. Blindly applying suggestions to "clear" the review adds churn, risks regressions, and dilutes the signal. A well-reasoned decline beats a low-confidence edit.

This judgment bar governs **every** piece of review feedback in this flow — existing comments here, reviewer rounds, human comments arriving mid-loop, and local-reviewer findings (step 4) — and it also governs **loop stopping** in both review loops: when findings become theoretical or insignificant, stop — do not manufacture work to "address" them.

**Triage is two-axis.** The agree / partially agree / disagree axis decides whether a finding
is *right*. A second axis decides *where the work goes*, and applies to every finding you
agreed with (fully or partly) that is not already fixed in this round:

- **`drop`** — theoretical or insignificant under the judgment bar above. Record the
  rationale; build nothing. A **disagreed** finding is already resolved and is not triaged —
  it is a decline, not a `drop`.
- **`absorb`** — do it in this PR, before merge. **This is the default.**
- **`file`** — becomes its own ticket, and only when **any** of these is true:
  1. It **reaches code this PR was not already changing** — files outside
     `git diff --name-only origin/<PR_BASE>...HEAD`. New files this PR creates count as
     *inside*.
  2. It requires a **new public interface, dependency, config key, or data migration**.
  3. It needs a design decision the ticket's **acceptance criteria do not already settle**.

  Every `file` item must cite the criterion number that made it one.

Absorbing does not skip review: the absorbed change is pushed like any other fix and the next
round reviews it. That is why this cannot run away — absorbed work re-enters the existing
round-capped loop, and the round cap is the backstop.

For **each unresolved** thread (skip threads whose GraphQL `isResolved` is `true` — a prior reply alone does not resolve a thread):

1. Read the comment against the actual code and the PR's intent. Validate every suggestion.
2. If a reply was already posted to this comment (this run or a prior aborted run), do not reply again — skip to resolving the thread. Otherwise take exactly one action and reply on that comment:
   - **Agree** → apply the change, reply `Agreed and applied.`
   - **Partially agree** → apply only the correct part, reply with what was and wasn't applied, and why.
   - **Disagree** → no code change, reply with a concise technical reason.
3. Reply in-thread for inline comments; use `gh pr comment` for PR-level notes (commands in `references/github-api.md`).
4. **Resolve the thread** via the GraphQL `resolveReviewThread` mutation — replying does not resolve; without this the merge gate in step 5 can never pass.

**Non-inline feedback has no thread-resolution state and must not be skipped**: review summary bodies and PR-level issue comments with actionable requests (e.g. "add tests") get the same agree/partially/disagree treatment, with the reply posted via `gh pr comment <pr> --body "..."`. Track them by comment ID — that tracking is their only "resolved" marker. Ignore non-actionable bot boilerplate per the bound reviewer's profile (e.g. the Codex "About" block, or Copilot's per-file summary table and custom-instructions footer).

Never respond twice to the same comment — track handled comment IDs. If code changed, first re-run the project's verification when the repo configures it (`verify.steps` in `.claude/notion-dev.config.json` — read from the primary checkout, not the worktree, honoring per-step `retries`) — a broken fix would surface as red CI next round, but repos without covering CI have only this gate — then commit and push:
`git add -A && git commit -m "review: address PR feedback" && git push`

## 3. Trigger a review

After all current comments are handled, trigger the bound reviewer per its profile:
- **codex** → `gh pr comment <pr> --body "@codex review"`.
- **copilot** → run the reviewer-request command. Treat it as `reason=not-configured` **only**
  when the response **message** says Copilot review is not enabled for this repo/org —
  on a `422`, `403`, or `404` alike. The status code alone never proves it. Then post the unavailability note
  (step 4) and enter the local review loop — do not count a round. Every other failure is
  retryable, not a verdict — see the classification below.

### A failed trigger has an unknown outcome — never blind-retry it

`gh` exiting non-zero does **not** mean the request never reached GitHub. A transport failure
(DNS, TLS, `error connecting to api.github.com`) can lose the *response* after the mutation
was already applied. Retrying blind then double-triggers: two reviews race on one poll
baseline and the round counter is wrong for the rest of the run.

**Capture an attempt baseline immediately before every trigger post — including the first one
of the run.** The recovery read below needs something definite to compare against, and "newer
than the round's previous trigger" is undefined on the first post. A PR can already carry an
older `@codex review` comment (a previous run, or a human), so with no baseline the recovery
read can adopt that stale comment as proof the new post landed — skipping the retry *and*
polling from a stale timestamp, which makes an old review look like this round's response.
Record either the current UTC time or the newest existing `@codex review` comment id before
each post; for copilot the pre-call UTC timestamp step 3 already requires is that baseline.

On any non-zero exit from a trigger command:

1. **Re-read the state the trigger would have changed, and let that decide** — never the exit
   code alone:
   - **codex** → `gh api --paginate repos/{owner}/{repo}/issues/<pr>/comments` and look for an
     `@codex review` comment newer than **this attempt's baseline**. Present → the post
     succeeded; adopt its `created_at` as the trigger timestamp and continue. Absent → nothing
     landed; retry the post.
   - **copilot** → **two** states each mean the request landed, and checking only the first
     yields a false negative that re-requests the review:
     - (a) the bot is listed by the **pending-request check** (`references/github-api.md` —
       the REST `requested_reviewers` endpoint, **never** `gh pr view --json reviewRequests`,
       which has been observed empty for a genuinely live request), **or**
     - (b) a Copilot review has appeared that was **not in `$SEEN`** (the pre-trigger id
       snapshot) — the bot is **auto-removed** from the pending-request list the moment it
       submits, so a review that completes before this recovery read leaves no trace in (a):

       ```bash
       gh api --paginate --slurp "repos/{owner}/{repo}/pulls/<pr>/reviews" \
         | jq "[.[][] | select(.user.login == \"copilot-pull-request-reviewer[bot]\" or .user.login == \"Copilot\")
                | select(.id as \$i | $SEEN | index(\$i) | not)] | length"
       ```

     Either → the request succeeded; continue (if (b), that review *is* the round's response —
     handle it, do not re-request). Neither → nothing landed; retry.
2. **The state re-read must itself succeed before it decides anything.** A read that errors,
   times out, or returns empty is not evidence of either outcome — it tells you nothing about
   whether the mutation landed. Never compare a failed read's empty result against the
   baseline and conclude from the difference that the state did (or did not) change: that
   turns one network fault into a false verdict, and a false "it landed" silently skips the
   round while a false "it didn't" double-triggers. Retry the **read** until it returns a
   definite answer, then decide. This is the same rule one level up — a transport failure is
   never a semantic signal.
3. **Retry at most 3 times** with a short backoff (~10s), re-checking state before each retry.
   Still failing with no state change → stop and report. Do not fall through to the local loop
   on a transport fault.

**Classify a failed reviewer-request in three buckets, not two — only the first is a verdict.**
`gh` exits non-zero "for any reason" (`gh help exit-codes`), so neither the exit code nor the
mere *presence* of an HTTP status distinguishes these. Read the status and message:

- **Permanent rejection** → `reason=not-configured`. A status whose meaning is "Copilot review
  is not available for this repo/org" — a `422`, `403`, or `404` whose **message** says so.
  The status alone is never sufficient: GitHub documents `422` on this endpoint as
  "Validation failed, or the endpoint has been spammed", so a validation error or
  spam-protection throttle returns the same code as a genuine not-enabled rejection. Read
  the message; if it does not name Copilot review as unavailable, this is not a verdict.
- **Transient response** → retry, **never** `not-configured`. `HTTP 500`, `502`, `503`, `429`,
  and any rate-limit `403` carry a status but say nothing about configuration. A rate-limit
  `403` in particular is indistinguishable from a permission `403` by status alone — the
  message decides.
- **Transport failure** → retry, **never** `not-configured`. A bare connection error (DNS, TLS,
  `error connecting to api.github.com`, `i/o timeout`) carries no status at all.

Recording `not-configured` for either retryable bucket permanently switches the run to the
local fallback and makes the final report claim a configuration problem the repo does not have.

**Record the trigger timestamp** — the poll baseline used in step 4. It must be well-defined for both reviewers, since only codex leaves a comment to key off:
- **codex** → the `created_at` of the `@codex review` comment just posted.
- **copilot** → the current UTC time captured **immediately before** the reviewer-request call (the REST request creates no comment). Capture it before the call so a review that lands during the request is not excluded.

**Also snapshot the reviewer's existing response IDs immediately before the trigger — and
prefer them to the timestamp.** GitHub timestamps are **second-precision**, so a reviewer that
submits inside the same second the baseline was captured has `submitted_at` *equal* to `$TS`
and is dropped by a strict `>` comparison: the round then reads as silent, gets re-triggered
or classified `reason=silent`, and its findings go untriaged even though the review exists. An
ID snapshot has no such boundary condition.

```bash
# immediately BEFORE the trigger — ids of reviews the reviewer has already submitted.
# set -o pipefail: without it a failed `gh` still yields exit 0 from `jq`, leaving $SEEN empty.
set -o pipefail
SEEN=$(gh api --paginate --slurp "repos/{owner}/{repo}/pulls/<pr>/reviews" \
  | jq -c "[.[][] | select(.user.login == \"copilot-pull-request-reviewer[bot]\" or .user.login == \"Copilot\") | .id]")
```

**Validate the snapshot before issuing the trigger — it is a read, so retrying it is free and
safe.** The fetch and the parse must *both* succeed: `gh` exits non-zero on failure, but in a
pipeline that status is discarded unless `pipefail` is set, and `jq` given no input exits 0
with empty output. An unvalidated `$SEEN` fails in two directions — empty, so every existing
review looks new and a stale one is triaged as this round's; or unset, so interpolating it
produces invalid jq and the round cannot be read at all. Either way an already-completed review
gets re-triggered or classified `reason=silent`. Require a non-empty, parseable JSON array
(`[]` is valid and means "none yet"; an *unset or non-JSON* value is the failure) and retry the
read until you have one. Only then send the mutating trigger — never trigger on an unvalidated
baseline.

Snapshot **reviews** and, for codex, its **issue comments** (quota / unavailability notices) —
but **never inline comments**. Inline comments are attributed to a round by their
`pull_request_review_id`, never by snapshot membership. A PR that already carries reviewer
inline comments from an earlier round or run would otherwise show every one of them as absent
from `$SEEN`, so the poll would end instantly on already-handled feedback and walk to merge
without ever waiting for the review it just requested. This applies to **both** reviewers, and
codex is the more exposed of the two because it creates inline threads routinely.

So: a **new response** is a review, or a codex issue comment, whose `.id` is absent from the
corresponding snapshot. Its inline comments are then collected via
`pull_request_review_id ∈ $RIDS` — the same path the copilot profile already uses. No
wall-clock comparison anywhere. Keep `$TS` for the report only; never let it decide whether a
response is new.

**A next-round trigger refreshes this baseline; a silence re-trigger must not** — neither
`$TS` nor `$SEEN`. The silence retry is the *same logical round*: its purpose is to recover a
response that never arrived, not to start a new one. Refreshing there opens a hole. If the
original review submits after the last pre-retry read but before the baseline is re-captured,
a refreshed `$SEEN` now *contains* that review's id, so it is no longer "new" and drops out of
`$RIDS` (and with the older timestamp form, its `submitted_at` fell below the new `$TS` the
same way). Either way its findings go untriaged and its threads unresolved, which blocks the
merge gate far from the cause. Keep the round's **original** `$TS` and `$SEEN` across a
silence re-trigger, and refresh both only when beginning a genuinely new round.

Set the round counter to **1** when posting this first trigger (also when the PR had no
reviews at all: run the green-CI gate first, then trigger).

## 4. Review loop

Rounds are counted from the first reviewer trigger. **Hard cap: the resolved `reviewsCap` (default 15).** After the capped round is handled, stop looping and go to merge (step 5) regardless of what the reviewer still finds.

**At the start of every round**: `gh pr checks <pr>` — fix any failing check and re-green before handling any review comment.

Poll for a **new** reviewer response every 30 seconds (`sleep 30` — do not busy-loop), reading reviews, issue comments, and inline comments with `--paginate`, acting only on items newer than the newest already seen. A **reviewer response** is a review or comment authored by the bound profile's reviewer bot whose **id is absent from the round's `$SEEN` snapshot** (step 3). Newness is decided by that snapshot alone — never by a wall-clock comparison, which has a second-precision boundary that silently drops a response submitted in the same second as the baseline. Authorship is an exact match against the profile's **set** of logins — never a substring or prefix test:

- **codex** — `user.login` exactly equals `chatgpt-codex-connector[bot]` on every surface.
- **copilot** — the bot renders under **two** logins, and filtering on either one alone silently drops half its output: `user.login` is `copilot-pull-request-reviewer[bot]` on the **review** object but `Copilot` on that review's **inline comments** (both carry the same `user.node_id`). Accept **either** login. Then attribute inline comments to the round by **review id**, not by login or timestamp — the review carries `submitted_at`, its inline comments do not:

  ```bash
  # EVERY copilot review submitted after the round's trigger timestamp $TS — not just the
  # newest. A silence re-trigger can leave two requests outstanding, and both can submit
  # inside one poll interval; keeping only the latest loses the other review's findings and
  # leaves its threads unresolved, which then blocks the merge gate.
  # --paginate applies --jq PER PAGE, so an aggregating filter (last, length, add) emits one
  # result per page; --slurp wraps all pages in one array but cannot be combined with --jq.
  # Hence: --slurp, then filter with external jq, flattening pages with .[][] — see
  # references/github-api.md.
  RIDS=$(gh api --paginate --slurp "repos/{owner}/{repo}/pulls/<pr>/reviews" \
    | jq -c "[.[][] | select(.user.login == \"copilot-pull-request-reviewer[bot]\" or .user.login == \"Copilot\")
              | select(.id as \$i | $SEEN | index(\$i) | not) | .id]")
  # their inline comments — matched by review id, across every matching review
  gh api --paginate --slurp "repos/{owner}/{repo}/pulls/<pr>/comments" \
    | jq "[.[][] | select(.pull_request_review_id as \$r | $RIDS | index(\$r))]"
  ```

  **Handle every review in `$RIDS`, not only the newest** — each one's body and inline comments
  are a separate finding source, and each one's threads must be resolved for the merge gate to
  clear.

  **Reconcile the counts before treating a round as clean**: each review body states how many comments it generated ("generated N comments" / "generated no new comments"). Compare each review's N against that review's own inline comments. If any disagrees, the filter is wrong — do not proceed on the smaller number.

Any other author (humans, CI bots, the *other* reviewer bot) is handled per step-2 rules but neither ends the poll nor counts as a round.

### Reviewer unavailability detection

While polling, watch for signals that the bound reviewer cannot review. Detection is active at **every** poll in **every** round — mid-loop quota exhaustion routes here too. On any signal below: capture the `reason`; **first handle any reviewer content already received** (a real review can arrive in the same poll as a quota notice — process it per the step-2 rules, reply and resolve its threads); then post a brief PR note (`gh pr comment <pr> --body "..."`) stating the reviewer is unavailable (with the reason) and the local review fallback is engaging, and switch **permanently** to the **local review loop** below — never re-trigger the reviewer again this run.

- **Quota** (codex only) — a new bot message whose body contains the case-insensitive substring `reached your codex usage limit`. `reason=quota`. Not applicable to copilot — copilot has no comment-based quota notice.
- **Not-configured / error / refusal**:
  - **codex** — a message from the Codex app itself (author login exactly `chatgpt-codex-connector[bot]`, matching the response filter above) or explicitly about Codex (e.g. a workflow notice that Codex is disabled or not installed) that is *exclusively* an inability-to-review notice: it carries **no** `Reviewed commit` marker and **no** findings. Two guards matter here: the exclusivity guard — a normal review that merely mentions an error while still carrying findings or a reviewed-commit marker is a normal round, not an unavailability signal — and the author guard — another review/CI app's failure notice is never a codex signal. `reason=not-configured` when the message says Codex is disabled / not set up / no app installed; otherwise `reason=error`.
  - **copilot** — only a **permanent rejection** is a signal: a `422`, `403`, or `404` whose **message** says Copilot review is not enabled for the repo/org. Status alone is never enough — `422` on this endpoint also covers validation failure and spam protection, which are retryable. `reason=not-configured`; a persistent rejection is `not-configured`, not `error`. **Transient responses** (`500`, `502`, `503`, `429`, rate-limit `403`) and **transport failures** are neither — retry them per step 3's three-bucket classification and never record `not-configured` for them.
- **Silence** — no new reviewer response within **~10 minutes (20 polls)** of a trigger.
  **The window elapsing is not proof the request is dead.** Reviewer latency varies widely:
  copilot has been observed responding in under 30 seconds on one round and ~16 minutes on
  another round of the *same* run. Re-triggering a request that is merely slow queues a second
  review and produces a duplicate round. So before re-triggering, confirm the request is
  actually gone:
  - **copilot** → the **pending-request check** (`references/github-api.md` — REST
    `requested_reviewers`; **not** `gh pr view --json reviewRequests`, which has been observed
    empty while the request was genuinely live). Bot **still listed** → the request is live and
    just slow; do **not** re-trigger — keep polling. The request is genuinely gone only when the
    bot is absent **and** no Copilot review has been submitted after the trigger timestamp (the
    bot is auto-removed the moment it submits, so absence alone is ambiguous — check for the
    review too, per step 3).
  - **codex** → no equivalent pending marker exists. Re-read reviews and issue comments with a
    **definite** read before concluding — a failed read is not silence.

  While the reviewer is confirmed live but slow, keep polling in further ~10-minute extensions
  rather than re-triggering, to a bounded total of **~30 minutes** from the trigger.

  Once the request is confirmed gone (or the 30-minute bound is reached): **re-trigger the
  bound reviewer once per its profile** (codex: re-comment `@codex review`; copilot: re-run the
  reviewer-request command), re-poll one more ~10-minute window — this re-trigger does not
  increment the round counter **and does not refresh the trigger timestamp** (step 3): the
  round keeps its original `$TS` so a late-arriving original review is still matched. If a review lands on the retry, continue normally. If the retry
  window is also silent: `reason=silent`.

  If a duplicate round does occur anyway (both the original and the re-triggered request
  submit), the multi-review handling above covers it: collect **every** matching review id and
  triage all of them — do not let the newer review mask the older one's findings.

### When a new reviewer response appears

1. Read all new comments from it — the review body **and** every inline comment attributed to that review by id (per the copilot rule above; a single-login filter misses them). **Copilot only**: because Copilot findings are often body-only (it frequently generates zero inline comments), treat the review's summary body as an actionable finding source, parsed via the existing step-2 "non-inline feedback" path (tracked by comment ID — no thread-resolution state). Two body regions carry findings:
   - **`<details><summary>Suppressed comments (N)</summary>`** — findings Copilot withheld for low confidence, and frequently the most substantive ones in the review. **Findings, not boilerplate.** Each entry is `**<path>:<line>**` followed by `* <description>` and an optional fenced code excerpt. Triage every one under the step-2 judgment bar. A headline of "generated no new comments" above a populated suppressed block is not a clean verdict.
   - The prose overview, for any actionable request not tied to a line.

   Skip only the two boilerplate regions named in the reviewer profile (the "Reviewed changes" per-file summary table and the "Add Copilot custom instructions" footer).
2. Evaluate and handle each per the step-2 rules and judgment bar (agree/partially/disagree, reply once, never twice). Reviewer findings are triaged on the same two axes as step 2 — every agreed-but-unfixed finding gets `absorb`, `file`, or `drop`, and `file` items cite their criterion number.
3. **Re-run the GraphQL thread query** (REST polling does not return thread node ids; new comments create new threads) and resolve every thread handled — this applies only to threads that actually exist (codex always creates inline threads for line-level findings; Copilot only when it has line-level findings).
4. Re-run the step-2 verification (config `verify.steps`, when present), then commit and push applied changes.
5. **Before treating the round as complete — in *either* branch below — confirm it has
   settled.** A silence retry can leave two requests outstanding, so a second review can arrive
   after the one just handled; the `$RIDS` query only saw what existed when it ran. The
   dangerous case is a late **body-only** Copilot review: it creates no inline thread, so the
   all-threads-resolved merge gate cannot catch it, and its findings would be merged past
   silently.

   Track a second set, `$HANDLED` — the ids triaged **during this round** — and add each
   response to it as you handle it. A response is genuinely new only when its id is absent from
   **both** `$SEEN` and `$HANDLED`. Testing against `$SEEN` alone deadlocks the loop: `$SEEN` is
   the immutable pre-trigger snapshot, so the response you just handled is by construction
   absent from it, and every settle poll would rediscover it, declare the round unsettled, and
   spin forever without ever reaching another round or the merge.

   After handling the round's responses, poll once more (~60–90s) and — for copilot — re-run the
   **pending-request check** (`references/github-api.md`; not `gh pr view --json
   reviewRequests`). If any id appears that is absent from both sets, the round has **not**
   settled: handle it, add it to `$HANDLED`, and repeat. If the bot is still listed as pending, a
   request is still outstanding — keep waiting, but bound that wait by the
   same ~30-minute total as the silence rule, then proceed rather than stalling. Only once a
   settle poll adds nothing may the round end.

   Then: if the round counter is below the cap and the round **produced code changes**: increment the counter, re-trigger the bound reviewer per its profile (codex: re-comment `@codex review`; copilot: re-run the reviewer-request command), return to the top of the loop. Do **not** re-trigger when nothing changed: if every finding in the round was rejected with rationale — including rounds whose findings were only theoretical or insignificant, declined under the step-2 judgment bar — the reviewer would repeat the same findings; resolve the threads and treat the loop as ended.

The reviewer loop ends on whichever comes first: **the reviewer reports no meaningful issues** per its profile's "no meaningful issues" row, the **judgment-based stop** in item 5 above, or the **round cap**. Then merge (step 5). If unavailability was detected instead, the local review loop below takes over with its own termination rules.

### Local review loop (reviewer unavailable)

Entered only from unavailability detection — the reviewer loop's structural twin, with "spawn a fresh reviewer agent" replacing "trigger the bound reviewer". Fresh context per round is the point: the reviewer never sees prior rounds' reasoning, so its findings are independent. Round counter starts at 1; **hard cap: the same resolved `reviewsCap`, counted independently of the reviewer loop's rounds** — a runaway backstop only; the judgment-based stops below are expected to end the loop much earlier.

Each round:

1. **Green-CI gate**: `gh pr checks <pr>` — fix any failing check and re-green before reviewing. Also check for new comments since the last round — from humans, other bots, or a late-arriving reviewer response from a pre-switch trigger — and handle them per the step-2 rules; they do not count as local rounds, and a late reviewer arrival never un-does the permanent switch (do not re-trigger).
2. **Spawn a fresh reviewer**: a `general-purpose` agent (synchronous — the loop needs the verdict before continuing), with a self-contained prompt containing:
   - Instruction: apply the `notion-dev:local-code-review` skill (shipped with this plugin) exactly, including its output contract (severity-graded findings and a final `VERDICT: CLEAN` / `VERDICT: NOT-CLEAN` line).
   - Material: the PR diff (`gh pr diff <pr>` or `git diff <base>...HEAD`), the PR title and body (the intent to judge correctness against), and the current HEAD sha to echo as `Reviewed commit: <sha>`.
   - The reviewer is review-only: it must not edit files, commit, or push.
3. **Post the round's findings as a PR comment** (audit trail on the merged PR): header `Local review — round <N> (reviewed commit <sha>)`, then the reviewer's findings and its `VERDICT` line.
4. **Triage** every finding per the step-2 rules and judgment bar (agree / partially agree / disagree). Local findings have no review threads — record each decline's rationale in a follow-up PR comment (or the round comment itself). Local findings are triaged on the same two axes as step 2 — every agreed-but-unfixed finding gets `absorb`, `file`, or `drop`, and `file` items cite their criterion number. Apply justified fixes, re-run tests/verification, commit and push; the new HEAD is what the next round reviews.
5. **Terminate or continue:**
   - Verdict is `VERDICT: CLEAN` (zero Critical/Required — only Optional/Nit/FYI findings, or none) **and no code changed this round** → converged; go to merge (step 5). If fixes were applied (e.g. an Optional finding worth taking), the new HEAD has not been reviewed — continue to another round.
   - Every finding this round was declined with rationale (no code changed) → loop ended; a fresh agent on the same code would repeat the same findings; go to merge.
   - **Oscillation guard**: the same Critical/Required finding (or finding-set) recurs across rounds even though fixes addressing it were applied and pushed → stop early and treat it as a disagreed finding (interactive: pause per pause point (a); non-interactive: resolve autonomously and log).
   - Round counter reaches the cap → stop; go to merge under the cap semantics.
   - **Contract violation**: the reviewer's output has no `VERDICT` line, or its verdict contradicts its own listed severities → derive the verdict from the findings (`CLEAN` iff zero Critical/Required) and proceed with these rules. If the output is unusable (no parseable findings at all), discard it and spawn one replacement reviewer without incrementing the counter; if the replacement also fails, stop and report.
   - Otherwise: increment the counter and spawn a fresh reviewer on the new HEAD.

Local-reviewer output consists of plain PR comments — no GraphQL thread resolution applies to them. The all-threads-resolved merge gate in step 5 still applies to all review threads — pre-existing, human, and any reviewer threads, including late arrivals from pre-switch triggers.

### The completeness verifier

Dispatched by the Completeness gate below. A fresh `general-purpose` agent, synchronous — the gate needs the verdict before it can decide — spawned the same way the local review loop spawns its reviewer, and for the same reason: independence from the party that believes the work is done.

Pass these as **file paths, not inline text**: the criteria file, the diff (`origin/<baseRefName>...HEAD`), the PR body, and the config `verify.steps` output already produced during the loop (`## 2. Process existing review comments`). Pass **nothing** from the implementer — not the plan, not the run's narrative, not prior reasoning. That exclusion is the point of the seat.

Its three charges:

1. **Per-criterion verdict.** `met` or `not-met` for each line of the criteria file, each with a **citation**: a command and its output, a named test and its result, or a quoted span with `file:line`. A `met` verdict carrying no citation is malformed output, not a passing criterion. Restating the criterion, "the implementation handles this", and pointing at a plan that said it would are all non-citations.

2. **Unsupported completeness claims**, over text **this pull request changed** — not the whole repository. The finding is the **missing referent, not the claim**: report only "this text says X exists, is handled, is mitigated, or is durable; I looked for X and it is absent or materially different." A true claim produces no finding, so honest prose costs nothing.

3. **Untriaged caveats.** Any stated gap, caveat, or known limitation — in the PR body or in docs this PR changed — carrying no `absorb` / `file` / `drop` label. A labeled caveat is fine and produces no finding. A limitation may exist; it may not exist unlabeled.

**The anti-circularity rule: the verifier may never cite the deliverable's own claims as evidence.** The PR body, the spec, and the changed docs are what charge 2 is auditing. Admitting them as proof under charge 1 would let a false claim validate itself, and charges 1 and 2 would confirm each other instead of checking anything.

Its output block, ending its response:

```
COMPLETENESS: <clean | blocked | degraded>
CRITERIA-TOTAL: <n>
CRITERIA-MET: <n>
CRITERIA-NOT-MET: <n>
CRITERIA-UNVERIFIED: <n>
VERDICTS:
- [<met|not-met|unverified>] <criterion verbatim> — <command|test|code>: <citation>
CLAIMS:
- <file:line> — claims <X>; <X> is absent or differs because <…>
CAVEATS:
- <where found> — <the caveat verbatim>
TRIAGE:
- [<absorb|file|drop>] <item> — <rationale; `file` cites its blast-radius criterion number>
```

`VERDICTS` / `CLAIMS` / `CAVEATS` / `TRIAGE` each take the literal `NONE` when empty, so an absent block is distinguishable from one that found nothing. Every key appears even on the degraded path.

**The verifier itself only ever writes `met` or `not-met`** (charge 1) — `unverified` is not a token it chooses. The schema still carries it because this same block is re-emitted, with any demoted verdicts, once the gate has resolved citations; see below and `COMPLETENESS-REPORT` in `## 5. Merge`.

**Contract check.** The output is usable only if every key is present, `CRITERIA-TOTAL` equals the criteria file's line count, and `CRITERIA-MET + CRITERIA-NOT-MET + CRITERIA-UNVERIFIED == CRITERIA-TOTAL`. A mismatch is a degradation, never a silent truncation.

**Citation resolution — the gate resolves every citation, not the verifier.** A `met` verdict is a claim until the gate confirms it:

- **Command citation** — the gate runs the command. The criterion is decided by exit status and output; no agent judgment is involved.
- **Test citation** — the named test must appear, passing, in the verification output the gate already holds.
- **Code citation** — the quoted span must appear in that file in the diff. Match **by content, never by line number**: a correct verdict whose line drifted by two must not be punished, and matching the span is stricter about substance while looser about position.

A citation that does not resolve demotes its criterion to `unverified`, a third state that is not `met` and not `not-met`. The verifier may have been right and merely sloppy in citing; the honest statement is that the gate could not confirm it.

**Degradation.** If the agent fails, or its output fails the contract check, retry **once** with the same prompt. If it fails again, emit `COMPLETENESS: degraded` with every key present and every criterion counted in `CRITERIA-UNVERIFIED`. Then:

- **Interactive** — stop and ask. The run has genuinely failed to establish whether the work is done, and that deserves a human rather than a default.
- **Non-interactive** — record each unverified criterion as a `file` item with the reason `unverified — completeness check degraded`. It becomes tracked follow-up work rather than an absence.

Passing the gate on degradation would be a silent bypass, and a silent bypass of a completeness gate is the exact failure this gate exists to remove. Blocking on it would deadlock merges behind a flaky agent. `unverified` is neither.

## 5. Merge

Enter only when the loop has ended. Hard gates — all of these hold even under the round cap:

1. **Checks gate**: every **required** check must pass — `gh pr checks <pr> --required`. Beware: this command exits non-zero **both** on failing required checks **and** when no required checks exist at all (cli/cli#9682) — if it fails with "no checks reported", the repo defines no required checks and the required gate is satisfied; do not treat that as a failure. Additionally, no check of any kind may be **failing** (`gh pr checks <pr>`, same "no checks reported" caveat) — a red optional check still blocks until fixed. Pending **optional** checks do not block the merge; pending **required** checks do — wait for them (`gh pr checks <pr> --required --watch`, or a 30-second sleep loop) with a bounded timeout of ~15 minutes; on timeout, stop and report.
2. **All threads resolved**: re-run the GraphQL thread query, paging through every page, and verify every thread has `isResolved: true`.

3. **Absorb gate**: **No `absorb` item may be outstanding at merge.** Every finding triaged
   `absorb` in step 2 or the local loop must be applied, pushed, and reviewed.

   The only way past this gate is a **reclassification, not a bypass**: re-triage the item to
   `file` and record which blast-radius criterion turned out true. A misjudged item can always
   get out; it can never get out silently. Because the escape always exists, this gate cannot
   deadlock a non-interactive run.

   This gate composes with the loop terminators rather than replacing them — the round cap,
   the oscillation guard, and the judgment-based stop all still end the loop. The gate only
   asserts that when the loop *does* end, nothing labeled `absorb` was left behind.

4. **Completeness gate**: **Nothing incomplete may be unlabeled at merge.**

   Run the completeness verifier (see `## 4. Review loop`), resolve its citations, and
   triage what it returns. Every `not-met` criterion, every `unverified` criterion —
   a single citation failing to resolve on an otherwise-clean run raises exactly one of
   these, and it is held exactly like any other item — every unsupported completeness
   claim, and every untriaged caveat becomes an item on the same two axes as any review
   finding: `absorb` — the default; for `not-met` because the ticket said it would do
   this, for `unverified` because the usual remedy is a citation that actually resolves
   (re-run the command, quote the right span) — `file` citing a blast-radius criterion
   number, or `drop` with a rationale. `absorb` items are then held by the Absorb gate
   above; this gate adds no second enforcement mechanism.

   For an acceptance criterion, `file` and `drop` are **scope reductions**, not deferrals
   of extra work. The caller records them where the work is tracked, not only in the PR.

   `absorb` items are fixed and pushed. **The gate stack then re-runs on the new HEAD,
   unconditionally** — not only when `--pre-merge-check` was supplied and fired; that
   check's own re-run is one instance of this rule, not its source. **The verifier runs
   at most twice.** Pass 2 covers only the criteria that came back `not-met` or
   `unverified` from pass 1, against only the new commits — bounding both cost and
   wall-clock. Anything still `not-met` or `unverified` after pass 2 — whichever state it
   started in — must be reclassified to `file` or `drop` with a rationale. As with the
   Absorb gate, the escape always exists, so this gate cannot deadlock a non-interactive
   run.

5. **Config pre-merge checks**: read `git.preMergeChecks` from
   `.claude/notion-dev.config.json` in the primary checkout (an ordered list of skill names; empty by default).
   Invoke each skill in order via the Skill tool. If any skill signals failure, stop
   and report which check failed and why — never merge past a failing configured check.

6. **Caller's pre-merge check**: if `--pre-merge-check` was provided, evaluate it now — after the other gates pass and immediately before the merge command (`git fetch origin` first if the check references remote state). If it fails, apply the remediation the check describes (then re-satisfy **every gate above** if that pushed new commits — stated ordinal-free deliberately: an enumeration here silently goes stale the next time a gate is inserted, which is exactly how the Absorb gate came to be missing from it); if it cannot be satisfied, stop and report. Never merge with a failing pre-merge check.

Read the merge strategy from .claude/notion-dev.config.json → git.mergeStrategy (default "squash") in the primary checkout. Then merge (per the configured strategy) into the PR's base branch (`baseRefName` — never retarget) and delete the remote branch:

```bash
gh pr merge <pr> --<strategy> --delete-branch   # <strategy> = git.mergeStrategy, default squash
```

If the merge command exits non-zero, do **not** re-run it — check `gh pr view <pr> --json state` first. `--delete-branch` can fail on its local-cleanup step *after* the remote merge succeeded (typical when the branch is checked out in a worktree, as in the ticket and finalize flows — see cli/cli#13380). If state is `MERGED`, the merge succeeded: just finish the remote branch deletion (`git push origin --delete <head-branch>`) and continue. Only if state is still `OPEN` diagnose the merge itself. Leave local branch and worktree removal to the caller.

Confirm `gh pr view <pr> --json state` reports `MERGED` before declaring success. The final report states: which reviewer/loop ran (Codex, Copilot, or the local fallback), rounds run, findings applied vs. declined (with reasons), the merge commit SHA (`gh pr view <pr> --json mergeCommit` after the merge), the number of fix commits pushed during the loop, and any judgment calls resolved autonomously in non-interactive mode — callers consume the merge SHA and counts for their ticket records and ledger metrics. If the round cap was hit, note it and list the findings that were disagreed with or could not be fully addressed. **When the local fallback ran, state prominently that no cross-model review validated this PR**, and why (`quota` / `not-configured` / `error` / `silent`).

The report's triage outcome is **three named lists**, never one undifferentiated set:

- `ABSORBED` — items done in this PR, each with what was changed.
- `FILED` — items that must become their own ticket, each with its criterion number and
  rationale. Reclassified items appear here, marked as reclassified from `absorb`.
- `DROPPED` — items decided against, each with its rationale.

Callers depend on this split: the whole point is that only `FILED` can generate new tickets.

The report also carries a **`COMPLETENESS-REPORT`** section: the verifier's keyed block, with the four `CRITERIA-*` counts restated after citation resolution and each `met` verdict's citation replaced by the gate's resolution of it — the counts a caller consumes are always the gate's, never the verifier's raw ones, because the verifier cannot know which of its own citations resolved. Callers depend on this — `/notion-dev:ticket` and `/notion-dev:finalize` tick the ticket's to-do boxes from `VERDICTS`, and every caller writes its counts to the ledger. When no verifier ran, the section is present and reads `COMPLETENESS: degraded` with its reason, never absent.

## Safety rules

- **Never** merge while any required check is failing or pending.
- **Never** merge while unresolved review threads remain.
- **Never** run more than `reviewsCap` reviewer rounds or `reviewsCap` local review rounds (default 15 each, counted independently).
- **Never** re-trigger the reviewer (codex comment or copilot reviewer-request) again after unavailability was detected — the switch to the local loop is permanent for the run.
- Red CI takes priority over review handling at the start of every round.
- Always merge into the PR's base branch; never retarget.
- Never respond twice to the same comment; never reapply already-applied changes.
- **Never blind-retry a mutating call whose outcome is unknown** — trigger, comment, reply, thread resolve, or merge. A non-zero `gh` exit can mean the mutation applied and only the response was lost, so re-read the state the call would have changed and decide from that (step 3 for triggers; step 5 already applies this to the merge). Never infer a reviewer's configuration state from a transport failure.
- The judgment bar (step 2) applies to every finding from every source — a well-reasoned decline beats a low-confidence edit, and neither loop manufactures work from theoretical findings.
- If the PR becomes unmergeable, is closed, or has conflicts that cannot be resolved safely: **stop and report** — do not force anything.

## Additional Resources

- **`references/github-api.md`** — exact `gh` commands: paginated comment reads, the GraphQL reviewThreads query and its cursor rules, thread-to-comment mapping, reply and resolve mutations.
