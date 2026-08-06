---
name: review-and-merge
description: This skill should be used when the user asks to "review and merge" a pull request, "merge PR after review", "run the review loop on PR", "drive PR to merge", or when the quick-dev develop flow reaches its review phase. Resolves existing review comments, loops the configured code reviewer (Codex or Copilot) — falling back to a local fresh-agent review loop when the reviewer is unavailable (quota, not configured, erroring, or silent) — then squash-merges and deletes the remote branch.
argument-hint: "<pr-number> [--non-interactive]"
---

# review-and-merge

Drive a pull request to a clean, merged state: resolve existing review feedback, run repeated review rounds until no meaningful issues remain, squash-merge, and delete the remote branch. Local branch/worktree cleanup is the caller's responsibility (the develop skill handles it in its flow).

## Input

Arguments: `$ARGUMENTS` — the PR number, plus optional `--non-interactive`, plus optional `--pre-merge-check "<requirement>"` — a caller-supplied condition (with its remediation) that must hold immediately before the merge command runs; see step 5.

Interactive mode (default) pauses for user input at exactly two points: (a) before merging while findings remain that were disagreed with or could not be addressed (round cap or oscillation guard), and (b) when a review suggestion conflicts with the PR's stated intent and both readings are defensible. With `--non-interactive`, never pause — resolve those calls autonomously and log them in the final report.

If no PR number is given, stop and ask for one. Do not guess.

All GitHub interaction uses the `gh` CLI against the current repository. Run `gh pr view <pr>` up front to confirm the PR exists, is **open**, and is not a draft. If closed/merged/draft, stop and report.

## Reviewer

This skill drives one of two configured reviewers — `codex` (default) or `copilot`. Resolve which **before step 3**, then bind its profile:

1. Run the **reviewer resolution procedure** in `references/reviewer-config.md` to obtain the value (`codex` | `copilot`). It reads the gitignored per-clone config from the primary checkout and, when the key is absent, prompts (interactive) or defaults to `codex` (non-interactive) and persists the choice. The skill itself never writes any tracked file.
2. Bind the **reviewer profile** below; every trigger / re-trigger / reviewer-response / unavailability reference in steps 3–5 means the bound profile's row.

| aspect | **codex** (default) | **copilot** |
|---|---|---|
| trigger | comment `@codex review` | request the bot reviewer: `gh api --method POST "repos/{owner}/{repo}/pulls/<pr>/requested_reviewers" -f 'reviewers[]=copilot-pull-request-reviewer[bot]'` (gh substitutes `{owner}`/`{repo}`) |
| re-trigger each round | re-comment `@codex review` | re-run the same reviewer-request command (the bot is auto-removed once it submits) |
| response author | `chatgpt-codex-connector[bot]` on every surface | **one bot, two logins**: `copilot-pull-request-reviewer[bot]` on the **review** object, `Copilot` on that review's **inline comments** — same `user.node_id`. Accept **either** login; matching one alone silently drops half the review (see step 4) |
| review shape | `COMMENTED` review; actionable findings are inline threads (+ a summary body) | `COMMENTED` review whose findings are **often in the summary body only** — Copilot frequently generates zero inline comments, withholding low-confidence findings into a `<details><summary>Suppressed comments (N)</summary>` block in the body instead, so the body is a first-class finding source; inline threads appear only when it has line-level findings |
| non-actionable boilerplate to ignore | Codex "About" block | **exactly two things**: the "Reviewed changes" per-file summary table and the "Add Copilot custom instructions" footer. A `<details><summary>Suppressed comments (N)</summary>` block is **not** boilerplate — despite also being a `<details>` block it carries real findings, and is triaged like any other finding |
| "no meaningful issues" | review says no major issues / equivalent | the body carries no actionable findings, **no** `Suppressed comments (N)` block with N ≥ 1, and there are no (or only resolved) inline comments. The headline "generated no new comments" is **not** sufficient on its own — it co-occurs with a populated suppressed-comments block |
| not-configured signal | a message from the Codex app that is *exclusively* an inability-to-review notice (no `Reviewed commit` marker, no findings) | a **permanent rejection** of the reviewer-request: a `422`/`403`/`404` whose **message** says Copilot review is not enabled. Status alone is never enough — GitHub documents `422` on this endpoint as "Validation failed, or the endpoint has been spammed". Transient statuses (`500`/`502`/`503`/`429`, rate-limit `403`, spam-protection `422`) and bare transport errors are **not** signals — retry them (step 3) |
| quota signal | body contains the case-insensitive substring `reached your codex usage limit` | n/a — Copilot has no comment-based quota notice; a persistent GitHub *rejection* is treated as `not-configured` |
| silence | no response within ~10 min (20×30s polls) → confirm the request is really gone (definite re-read), then re-trigger once → `reason=silent` | same window, but **never re-trigger while the bot is still listed in `reviewRequests`** — it is slow, not silent (latency of ~16 min observed); keep polling to a ~30-min bound |

### Round cap

Both review loops in step 4 are capped by `reviewsCap`, read from
`REPO_ROOT/.claude/quick-dev/config.json` — the same primary-checkout file and the same
`REPO_ROOT` resolution as `references/reviewer-config.md` step 1. Resolve it **once**, here,
before the first trigger:

- The value is an integer ≥ 1 → use it.
- The key is absent, the file is missing, or the value is anything else (`0`, negative,
  non-integer, non-numeric) → use **15**. When the value was present but unusable, say so in
  the final report; never stop the loop over it.

The resolved number caps the reviewer loop and the local fallback loop **independently** —
the fallback restarts its counter at 1, so a run that falls back can perform up to twice the
cap in total. Nothing writes this key; it is hand-edited.

## 1. Load the pull request

- `gh pr view <pr> --json number,title,body,state,isDraft,mergeable,mergeStateStatus,headRefName,baseRefName,reviewDecision,statusCheckRollup,url` (`body` is required later: the local fallback reviewer judges the diff against the PR title and body)
- Fetch all existing review comments with `--paginate` (inline comments, review summaries, issue comments) and the review-thread resolution state via GraphQL — exact commands, the thread query, and the pagination rules are in **`references/github-api.md`**. Read it before the first API call; the pagination and thread-mapping rules there are load-bearing (unpaginated reads silently miss comments; REST alone cannot resolve threads).
- Ensure the PR branch is checked out locally so fixes can be applied: if the current directory is already on `headRefName` (the develop flow's worktree), stay there; otherwise `gh pr checkout <pr>`.
- Require a clean working tree before proceeding (`git status --porcelain` empty): review fixes are committed with `git add -A`, which would sweep pre-existing uncommitted changes into the automated commit and push them. If dirty, stop and ask the user to commit or stash first (non-interactive: stop and report).
- Push any local commits the remote is missing before processing anything: if `git rev-list --count @{upstream}..HEAD` is non-zero (e.g. a prior run committed fixes but its push failed), `git push` first — otherwise the already-replied skip path could resolve threads and merge while the remote head lacks those fixes.

## 2. Process existing review comments

**Before touching any comment**, run the green-CI gate: `gh pr checks <pr>`. If any check is **failing** (not merely pending), fixing it is the first priority — diagnose, push a fix, wait for green. Never process review feedback while a check is red. In this and **every** green-CI gate in this skill (start of each reviewer round, local-loop step 1): `gh pr checks` exiting non-zero with `no checks reported` means the repo defines no checks — the gate passes; treat only actually failing checks as red (same caveat as the step-5 merge gate).

Handle all review feedback with the `quick-dev:receiving-code-review` skill (shipped with this plugin) — verify each point against the code with technical rigor; no performative agreement, no blind implementation.

**Apply judgment — do not apply a change you are not confident improves the code.** Every review comment (bot or human) is a suggestion to evaluate, not an order to follow. The bar to apply is affirmative: you must be able to state why it's an improvement for THIS codebase. If unsure — or it's cosmetic churn / speculative / unverifiable / an equivalent-wording swap — do not apply it; reply with your reasoning (ask the user for anything contentious; non-interactive: decide autonomously and log it in the final report) and leave it. Blindly applying suggestions to "clear" the review adds churn, risks regressions, and dilutes the signal. A well-reasoned decline beats a low-confidence edit.

This judgment bar governs **every** piece of review feedback in this flow — existing comments here, reviewer rounds, human comments arriving mid-loop, and local-reviewer findings (step 4) — and it also governs **loop stopping** in both review loops: when findings become theoretical or insignificant, stop — do not manufacture work to "address" them.

For **each unresolved** thread (skip threads whose GraphQL `isResolved` is `true` — a prior reply alone does not resolve a thread):

1. Read the comment against the actual code and the PR's intent. Validate every suggestion.
2. If a reply was already posted to this comment (this run or a prior aborted run), do not reply again — skip to resolving the thread. Otherwise take exactly one action and reply on that comment:
   - **Agree** → apply the change, reply `Agreed and applied.`
   - **Partially agree** → apply only the correct part, reply with what was and wasn't applied, and why.
   - **Disagree** → no code change, reply with a concise technical reason.
3. Reply in-thread for inline comments; use `gh pr comment` for PR-level notes (commands in `references/github-api.md`).
4. **Resolve the thread** via the GraphQL `resolveReviewThread` mutation — replying does not resolve; without this the merge gate in step 5 can never pass.

**Non-inline feedback has no thread-resolution state and must not be skipped**: review summary bodies and PR-level issue comments with actionable requests (e.g. "add tests") get the same agree/partially/disagree treatment, with the reply posted via `gh pr comment <pr> --body "..."`. Track them by comment ID — that tracking is their only "resolved" marker. Ignore non-actionable bot boilerplate per the bound reviewer's profile (e.g. the Codex "About" block, or Copilot's per-file summary table and custom-instructions footer).

Never respond twice to the same comment — track handled comment IDs. If code changed, commit and push:
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
     - (a) the bot is listed in `gh pr view <pr> --json reviewRequests`, **or**
     - (b) a Copilot review has appeared that was **not in `$SEEN`** (the pre-trigger id
       snapshot) — the bot is **auto-removed** from `reviewRequests` the moment it submits,
       so a review that completes before this recovery read leaves no trace in (a):

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
# immediately BEFORE the trigger — ids of reviews the reviewer has already submitted
SEEN=$(gh api --paginate --slurp "repos/{owner}/{repo}/pulls/<pr>/reviews" \
  | jq -c "[.[][] | select(.user.login == \"copilot-pull-request-reviewer[bot]\" or .user.login == \"Copilot\") | .id]")
```

A **new** review is then any matching review whose `.id` is absent from `$SEEN` — no wall-clock
comparison at all. Do the same for codex (snapshot the ids of its reviews and issue comments).
Keep `$TS` for the report and as a secondary guard, but never let it alone decide whether a
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

Set the round counter to **1** when posting this first trigger (also when the PR had no reviews at all: run the green-CI gate first, then trigger).

## 4. Review loop

Rounds are counted from the first reviewer trigger. **Hard cap: the resolved `reviewsCap` (default 15).** After the capped round is handled, stop looping and go to merge (step 5) regardless of what the reviewer still finds.

**At the start of every round**: `gh pr checks <pr>` — fix any failing check and re-green before handling any review comment.

Poll for a **new** reviewer response every 30 seconds (`sleep 30` — do not busy-loop), reading reviews, issue comments, and inline comments with `--paginate`, acting only on items newer than the newest already seen. A **reviewer response** is a review or comment authored by the bound profile's reviewer bot, created after the round's **trigger timestamp** (step 3: the `@codex review` comment's timestamp for codex, the captured request-start time for copilot). Authorship is an exact match against the profile's **set** of logins — never a substring or prefix test:

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
  - **copilot** → `gh pr view <pr> --json reviewRequests`. Bot **still listed** → the request
    is live and just slow; do **not** re-trigger — keep polling. The request is genuinely gone
    only when the bot is absent **and** no Copilot review has been submitted after the trigger
    timestamp (the bot is auto-removed the moment it submits, so absence alone is ambiguous —
    check for the review too, per step 3).
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
2. Evaluate and handle each per the step-2 rules and judgment bar (agree/partially/disagree, reply once, never twice).
3. **Re-run the GraphQL thread query** (REST polling does not return thread node ids; new comments create new threads) and resolve every thread handled.
4. Commit and push applied changes.
5. If the round counter is below the cap and the round **produced code changes**: increment the counter, re-trigger the bound reviewer per its profile (codex: re-comment `@codex review`; copilot: re-run the reviewer-request command), return to the top of the loop. Do **not** re-trigger when nothing changed: if every finding in the round was rejected with rationale — including rounds whose findings were only theoretical or insignificant, declined under the step-2 judgment bar — the reviewer would repeat the same findings; resolve the threads and treat the loop as ended.

The reviewer loop ends on whichever comes first: **the reviewer reports no meaningful issues** per its profile's "no meaningful issues" row, the **judgment-based stop** in item 5 above, or the **round cap**. Then merge (step 5). If unavailability was detected instead, the local review loop below takes over with its own termination rules.

### Local review loop (reviewer unavailable)

Entered only from unavailability detection — the reviewer loop's structural twin, with "spawn a fresh reviewer agent" replacing "trigger the bound reviewer". Fresh context per round is the point: the reviewer never sees prior rounds' reasoning, so its findings are independent. Round counter starts at 1; **hard cap: the same resolved `reviewsCap`, counted independently of the reviewer loop's rounds** — a runaway backstop only; the judgment-based stops below are expected to end the loop much earlier.

Each round:

1. **Green-CI gate**: `gh pr checks <pr>` — fix any failing check and re-green before reviewing. Also check for new comments since the last round — from humans, other bots, or a late-arriving reviewer response from a pre-switch trigger — and handle them per the step-2 rules; they do not count as local rounds, and a late reviewer arrival never un-does the permanent switch (do not re-trigger).
2. **Spawn a fresh reviewer**: a `general-purpose` agent (synchronous — the loop needs the verdict before continuing), with a self-contained prompt containing:
   - Instruction: apply the `quick-dev:local-code-review` skill (shipped with this plugin) exactly, including its output contract (severity-graded findings and a final `VERDICT: CLEAN` / `VERDICT: NOT-CLEAN` line).
   - Material: the PR diff (`gh pr diff <pr>` or `git diff <base>...HEAD`), the PR title and body (the intent to judge correctness against), and the current HEAD sha to echo as `Reviewed commit: <sha>`.
   - The reviewer is review-only: it must not edit files, commit, or push.
3. **Post the round's findings as a PR comment** (audit trail on the merged PR): header `Local review — round <N> (reviewed commit <sha>)`, then the reviewer's findings and its `VERDICT` line.
4. **Triage** every finding per the step-2 rules and judgment bar (agree / partially agree / disagree). Local findings have no review threads — record each decline's rationale in a follow-up PR comment (or the round comment itself). Apply justified fixes, re-run tests/verification, commit and push; the new HEAD is what the next round reviews.
5. **Terminate or continue:**
   - Verdict is `VERDICT: CLEAN` (zero Critical/Required — only Optional/Nit/FYI findings, or none) **and no code changed this round** → converged; go to merge (step 5). If fixes were applied (e.g. an Optional finding worth taking), the new HEAD has not been reviewed — continue to another round.
   - Every finding this round was declined with rationale (no code changed) → loop ended; a fresh agent on the same code would repeat the same findings; go to merge.
   - **Oscillation guard**: the same Critical/Required finding (or finding-set) recurs across rounds even though fixes addressing it were applied and pushed → stop early and treat it as a disagreed finding (interactive: pause per pause point (a); non-interactive: resolve autonomously and log).
   - Round counter reaches the cap → stop; go to merge under the cap semantics.
   - **Contract violation**: the reviewer's output has no `VERDICT` line, or its verdict contradicts its own listed severities → derive the verdict from the findings (`CLEAN` iff zero Critical/Required) and proceed with these rules. If the output is unusable (no parseable findings at all), discard it and spawn one replacement reviewer without incrementing the counter; if the replacement also fails, stop and report.
   - Otherwise: increment the counter and spawn a fresh reviewer on the new HEAD.

Local-reviewer output consists of plain PR comments — no GraphQL thread resolution applies to them. The all-threads-resolved merge gate in step 5 still applies to all review threads — pre-existing, human, and any reviewer threads, including late arrivals from pre-switch triggers.

## 5. Merge

Enter only when the loop has ended. Hard gates — both hold even under the round cap:

1. **Checks gate**: every **required** check must pass — `gh pr checks <pr> --required`. Beware: this command exits non-zero **both** on failing required checks **and** when no required checks exist at all (cli/cli#9682) — if it fails with "no checks reported", the repo defines no required checks and the required gate is satisfied; do not treat that as a failure. Additionally, no check of any kind may be **failing** (`gh pr checks <pr>`, same "no checks reported" caveat) — a red optional check still blocks until fixed. Pending **optional** checks do not block the merge; pending **required** checks do — wait for them (`gh pr checks <pr> --required --watch`, or a 30-second sleep loop) with a bounded timeout of ~15 minutes; on timeout, stop and report.
2. **All threads resolved**: re-run the GraphQL thread query, paging through every page, and verify every thread has `isResolved: true`.

3. **Caller's pre-merge check**: if `--pre-merge-check` was provided, evaluate it now — after the other gates pass and immediately before the merge command (`git fetch origin` first if the check references remote state). If it fails, apply the remediation the check describes (then re-satisfy gates 1–2 if that pushed new commits); if it cannot be satisfied, stop and report. Never merge with a failing pre-merge check.

Then squash-merge into the PR's base branch (`baseRefName` — never retarget) and delete the remote branch:

```bash
gh pr merge <pr> --squash --delete-branch
```

If the merge command exits non-zero, do **not** re-run it — check `gh pr view <pr> --json state` first. `--delete-branch` can fail on its local-cleanup step *after* the remote squash-merge succeeded (typical when the branch is checked out in a worktree, as in the develop flow — see cli/cli#13380). If state is `MERGED`, the merge succeeded: just finish the remote branch deletion (`git push origin --delete <head-branch>`) and continue. Only if state is still `OPEN` diagnose the merge itself. Leave local branch and worktree removal to the caller.

Confirm `gh pr view <pr> --json state` reports `MERGED` before declaring success. The final report states: which loop ran (the configured reviewer — Codex or Copilot — or the local fallback), rounds run, findings applied vs. declined (with reasons), and any judgment calls resolved autonomously in non-interactive mode. If the round cap was hit, note it and list the findings that were disagreed with or could not be fully addressed. **When the local fallback ran, state prominently that no cross-model reviewer validated this PR**, and why (`quota` / `not-configured` / `error` / `silent`).

## Safety rules

- **Never** merge while any required check is failing or pending.
- **Never** merge while unresolved review threads remain.
- **Never** run more than `reviewsCap` reviewer rounds or `reviewsCap` local review rounds (default 15 each, counted independently).
- **Never** re-trigger the bound reviewer again after unavailability was detected — the switch to the local loop is permanent for the run.
- Red CI takes priority over review handling at the start of every round.
- Always merge into the PR's base branch; never retarget.
- Never respond twice to the same comment; never reapply already-applied changes.
- **Never blind-retry a mutating call whose outcome is unknown** — trigger, comment, reply, thread resolve, or merge. A non-zero `gh` exit can mean the mutation applied and only the response was lost, so re-read the state the call would have changed and decide from that (step 3 for triggers; step 5 already applies this to the merge). Never infer a reviewer's configuration state from a transport failure.
- The judgment bar (step 2) applies to every finding from every source — a well-reasoned decline beats a low-confidence edit, and neither loop manufactures work from theoretical findings.
- If the PR becomes unmergeable, is closed, or has conflicts that cannot be resolved safely: **stop and report** — do not force anything.

## Additional Resources

- **`references/github-api.md`** — exact `gh` commands: paginated comment reads, the GraphQL reviewThreads query and its cursor rules, thread-to-comment mapping, reply and resolve mutations.
- **`references/reviewer-config.md`** — the configurable-reviewer config location and the read-or-prompt-and-persist resolution procedure (shared with `quick-dev:develop`).
