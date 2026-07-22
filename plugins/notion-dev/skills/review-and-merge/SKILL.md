---
name: review-and-merge
description: This skill should be used when the user asks to "review and merge" a pull request, "merge PR after review", "run the review loop on PR", "drive PR to merge", or when /notion-dev:ticket reaches its review phase or /notion-dev:finalize runs. Resolves existing review comments, loops the configured code reviewer (Codex or Copilot) — falling back to a local fresh-agent review loop when the reviewer is unavailable (quota, not configured, erroring, or silent) — then merges (per the configured strategy) and deletes the remote branch.
argument-hint: "<pr-number> [--non-interactive] [--pre-merge-check \"<requirement>\"]"
---

# review-and-merge

Drive a pull request to a clean, merged state: resolve existing review feedback, run repeated review rounds until no meaningful issues remain, merge (per the configured strategy), and delete the remote branch. Local branch/worktree cleanup is the caller's responsibility (the calling command handles it in its flow).

## Input

Arguments: `$ARGUMENTS` — the PR number, plus optional `--non-interactive`, plus optional `--pre-merge-check "<requirement>"` — a caller-supplied condition (with its remediation) that must hold immediately before the merge command runs; see step 5.

Interactive mode (default) pauses for user input at exactly two points: (a) before merging while findings remain that were disagreed with or could not be addressed (round cap or oscillation guard), and (b) when a review suggestion conflicts with the PR's stated intent and both readings are defensible. With `--non-interactive`, never pause — resolve those calls autonomously and log them in the final report.

If no PR number is given, stop and ask for one. Do not guess.

All GitHub interaction uses the `gh` CLI against the current repository. Run `gh pr view <pr>` up front to confirm the PR exists, is **open**, and is not a draft. If closed/merged/draft, stop and report.

## Reviewer

This skill drives one of two configured reviewers. Resolve which **before step 3**:

1. Read `reviewer` from `.claude/notion-dev.config.json` (primary checkout).
2. If the file has no `reviewer` key (e.g. a project configured before this field existed):
   in interactive mode, ask via `AskUserQuestion` — "Which code reviewer should the review
   loop use?" (**Codex** / **Copilot**) — then write the chosen value back into
   `.claude/notion-dev.config.json` (preserve all other keys; add `"reviewer": "<choice>"`).
   In non-interactive mode, default to `codex` and record it in the report. Always persist
   the `reviewer` key explicitly.

   **This migration must complete before the step-1 clean-tree gate**, and must not leave
   the primary checkout dirty (`.claude/notion-dev.config.json` is normally tracked — see
   `commands/init.md`). So immediately after writing the key, commit just that file:
   `git commit --only .claude/notion-dev.config.json -m "chore(notion-dev): persist reviewer choice"`.
   Exception: if the repo gitignores the path (`git check-ignore -q .claude/notion-dev.config.json`),
   the write touches no tracked state — skip the commit. Either way the working tree is clean
   for the step-1 gate, the write is never swept into a later `review:` fix commit, and the
   caller's post-merge `git pull` cleanup is never blocked by a stray unstaged edit.
3. Bind the **reviewer profile** below; every trigger / re-trigger / reviewer-response /
   unavailability reference in steps 3–5 means the bound profile's row.

| aspect | **codex** | **copilot** |
|---|---|---|
| trigger | comment `@codex review` | request the bot reviewer: `gh api --method POST "repos/{owner}/{repo}/pulls/<pr>/requested_reviewers" -f 'reviewers[]=copilot-pull-request-reviewer[bot]'` (gh substitutes `{owner}`/`{repo}`) |
| re-trigger each round | re-comment `@codex review` | re-run the same reviewer-request command (the bot is auto-removed once it submits) |
| response author (exact login) | `chatgpt-codex-connector[bot]` | `copilot-pull-request-reviewer[bot]` |
| review shape | `COMMENTED` review; actionable findings are inline threads (+ a summary body) | `COMMENTED` review whose findings are **often in the summary body only** — Copilot frequently generates zero inline comments (suppresses low-confidence ones), so the body is a first-class finding source; inline threads appear only when it has line-level findings |
| non-actionable boilerplate to ignore | Codex "About" block | the review body's per-file `<details>` summary table and the "Add Copilot custom instructions" footer |
| "no meaningful issues" | review says no major issues / equivalent | a review whose body is only the overview/per-file summary with no actionable findings and no (or only resolved) inline comments |
| not-configured signal | a message from the Codex app that is *exclusively* an inability-to-review notice (no `Reviewed commit` marker, no findings) | the reviewer-request command exits non-zero (e.g. HTTP 422 → Copilot code review not enabled for the repo/org) |
| quota signal | body contains the case-insensitive substring `reached your codex usage limit` | n/a — Copilot has no comment-based quota notice; a persistent request failure is treated as `not-configured` |
| silence | no response within ~10 min (20×30s polls) → re-trigger once → `reason=silent` | same |

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
- **copilot** → run the reviewer-request command. If it **exits non-zero** (Copilot code
  review not enabled for this repo/org), treat it as `reason=not-configured` immediately:
  post the unavailability note (step 4) and enter the local review loop — do not count a round.

**Record the trigger timestamp** — the poll baseline used in step 4. It must be well-defined for both reviewers, since only codex leaves a comment to key off:
- **codex** → the `created_at` of the `@codex review` comment just posted.
- **copilot** → the current UTC time captured **immediately before** the reviewer-request call (the REST request creates no comment). Capture it before the call so a review that lands during the request is not excluded.

Every re-trigger (the silence retry in step 4, and the next-round trigger in the loop) **refreshes** this timestamp per the same rule.

Set the round counter to **1** when posting this first trigger (also when the PR had no
reviews at all: run the green-CI gate first, then trigger).

## 4. Review loop

Rounds are counted from the first reviewer trigger. **Hard cap: 10 rounds.** After round 10 is handled, stop looping and go to merge (step 5) regardless of what the reviewer still finds.

**At the start of every round**: `gh pr checks <pr>` — fix any failing check and re-green before handling any review comment.

Poll for a **new** reviewer response every 30 seconds (`sleep 30` — do not busy-loop), reading reviews, issue comments, and inline comments with `--paginate`, acting only on items newer than the newest already seen. A **reviewer response** is a review or comment whose author login **exactly equals** the bound profile's response-author login — `chatgpt-codex-connector[bot]` (codex) or `copilot-pull-request-reviewer[bot]` (copilot) — created after the round's **trigger timestamp** (step 3: the `@codex review` comment's timestamp for codex, the captured request-start time for copilot). An exact match, never a substring test. Any other author (humans, CI bots, the *other* reviewer bot) is handled per step-2 rules but neither ends the poll nor counts as a round.

### Reviewer unavailability detection

While polling, watch for signals that the bound reviewer cannot review. Detection is active at **every** poll in **every** round — mid-loop quota exhaustion routes here too. On any signal below: capture the `reason`; **first handle any reviewer content already received** (a real review can arrive in the same poll as a quota notice — process it per the step-2 rules, reply and resolve its threads); then post a brief PR note (`gh pr comment <pr> --body "..."`) stating the reviewer is unavailable (with the reason) and the local review fallback is engaging, and switch **permanently** to the **local review loop** below — never re-trigger the reviewer again this run.

- **Quota** (codex only) — a new bot message whose body contains the case-insensitive substring `reached your codex usage limit`. `reason=quota`. Not applicable to copilot — copilot has no comment-based quota notice.
- **Not-configured / error / refusal**:
  - **codex** — a message from the Codex app itself (author login exactly `chatgpt-codex-connector[bot]`, matching the response filter above) or explicitly about Codex (e.g. a workflow notice that Codex is disabled or not installed) that is *exclusively* an inability-to-review notice: it carries **no** `Reviewed commit` marker and **no** findings. Two guards matter here: the exclusivity guard — a normal review that merely mentions an error while still carrying findings or a reviewed-commit marker is a normal round, not an unavailability signal — and the author guard — another review/CI app's failure notice is never a codex signal. `reason=not-configured` when the message says Codex is disabled / not set up / no app installed; otherwise `reason=error`.
  - **copilot** — the reviewer-request command exits non-zero (e.g. HTTP 422 → Copilot code review not enabled for the repo/org). `reason=not-configured`. A persistent request failure is treated as `not-configured`, not `error`.
- **Silence** — no new reviewer response within **~10 minutes (20 polls)** of a trigger. Do not stall: **re-trigger the bound reviewer once per its profile** (codex: re-comment `@codex review`; copilot: re-run the reviewer-request command), re-poll one more ~10-minute window — this re-trigger does not increment the round counter. If a review lands on the retry, continue normally. If the retry window is also silent: `reason=silent`.

### When a new reviewer response appears

1. Read all new comments from it. **Copilot only**: because Copilot findings are often body-only (it frequently generates zero inline comments), treat the review's summary body as an actionable finding source, parsed via the existing step-2 "non-inline feedback" path (tracked by comment ID — no thread-resolution state). Skip the boilerplate named in the reviewer profile (the per-file `<details>` summary table and the "Add Copilot custom instructions" footer).
2. Evaluate and handle each per the step-2 rules and judgment bar (agree/partially/disagree, reply once, never twice).
3. **Re-run the GraphQL thread query** (REST polling does not return thread node ids; new comments create new threads) and resolve every thread handled — this applies only to threads that actually exist (codex always creates inline threads for line-level findings; Copilot only when it has line-level findings).
4. Re-run the step-2 verification (config `verify.steps`, when present), then commit and push applied changes.
5. If the round counter is below 10 and the round **produced code changes**: increment the counter, re-trigger the bound reviewer per its profile (codex: re-comment `@codex review`; copilot: re-run the reviewer-request command), return to the top of the loop. Do **not** re-trigger when nothing changed: if every finding in the round was rejected with rationale — including rounds whose findings were only theoretical or insignificant, declined under the step-2 judgment bar — the reviewer would repeat the same findings; resolve the threads and treat the loop as ended.

The reviewer loop ends on whichever comes first: **the reviewer reports no meaningful issues** per its profile's "no meaningful issues" row, the **judgment-based stop** in item 5 above, or the **10-round cap**. Then merge (step 5). If unavailability was detected instead, the local review loop below takes over with its own termination rules.

### Local review loop (reviewer unavailable)

Entered only from unavailability detection — the reviewer loop's structural twin, with "spawn a fresh reviewer agent" replacing "trigger the bound reviewer". Fresh context per round is the point: the reviewer never sees prior rounds' reasoning, so its findings are independent. Round counter starts at 1; **hard cap: 10 rounds** — a runaway backstop only; the judgment-based stops below are expected to end the loop much earlier.

Each round:

1. **Green-CI gate**: `gh pr checks <pr>` — fix any failing check and re-green before reviewing. Also check for new comments since the last round — from humans, other bots, or a late-arriving reviewer response from a pre-switch trigger — and handle them per the step-2 rules; they do not count as local rounds, and a late reviewer arrival never un-does the permanent switch (do not re-trigger).
2. **Spawn a fresh reviewer**: a `general-purpose` agent (synchronous — the loop needs the verdict before continuing), with a self-contained prompt containing:
   - Instruction: apply the `notion-dev:local-code-review` skill (shipped with this plugin) exactly, including its output contract (severity-graded findings and a final `VERDICT: CLEAN` / `VERDICT: NOT-CLEAN` line).
   - Material: the PR diff (`gh pr diff <pr>` or `git diff <base>...HEAD`), the PR title and body (the intent to judge correctness against), and the current HEAD sha to echo as `Reviewed commit: <sha>`.
   - The reviewer is review-only: it must not edit files, commit, or push.
3. **Post the round's findings as a PR comment** (audit trail on the merged PR): header `Local review — round <N> (reviewed commit <sha>)`, then the reviewer's findings and its `VERDICT` line.
4. **Triage** every finding per the step-2 rules and judgment bar (agree / partially agree / disagree). Local findings have no review threads — record each decline's rationale in a follow-up PR comment (or the round comment itself). Apply justified fixes, re-run tests/verification, commit and push; the new HEAD is what the next round reviews.
5. **Terminate or continue:**
   - Verdict is `VERDICT: CLEAN` (zero Critical/Required — only Optional/Nit/FYI findings, or none) **and no code changed this round** → converged; go to merge (step 5). If fixes were applied (e.g. an Optional finding worth taking), the new HEAD has not been reviewed — continue to another round.
   - Every finding this round was declined with rationale (no code changed) → loop ended; a fresh agent on the same code would repeat the same findings; go to merge.
   - **Oscillation guard**: the same Critical/Required finding (or finding-set) recurs across rounds even though fixes addressing it were applied and pushed → stop early and treat it as a disagreed finding (interactive: pause per pause point (a); non-interactive: resolve autonomously and log).
   - Round counter reaches 10 → stop; go to merge under the cap semantics.
   - **Contract violation**: the reviewer's output has no `VERDICT` line, or its verdict contradicts its own listed severities → derive the verdict from the findings (`CLEAN` iff zero Critical/Required) and proceed with these rules. If the output is unusable (no parseable findings at all), discard it and spawn one replacement reviewer without incrementing the counter; if the replacement also fails, stop and report.
   - Otherwise: increment the counter and spawn a fresh reviewer on the new HEAD.

Local-reviewer output consists of plain PR comments — no GraphQL thread resolution applies to them. The all-threads-resolved merge gate in step 5 still applies to all review threads — pre-existing, human, and any reviewer threads, including late arrivals from pre-switch triggers.

## 5. Merge

Enter only when the loop has ended. Hard gates — all of these hold even under the round cap:

1. **Checks gate**: every **required** check must pass — `gh pr checks <pr> --required`. Beware: this command exits non-zero **both** on failing required checks **and** when no required checks exist at all (cli/cli#9682) — if it fails with "no checks reported", the repo defines no required checks and the required gate is satisfied; do not treat that as a failure. Additionally, no check of any kind may be **failing** (`gh pr checks <pr>`, same "no checks reported" caveat) — a red optional check still blocks until fixed. Pending **optional** checks do not block the merge; pending **required** checks do — wait for them (`gh pr checks <pr> --required --watch`, or a 30-second sleep loop) with a bounded timeout of ~15 minutes; on timeout, stop and report.
2. **All threads resolved**: re-run the GraphQL thread query, paging through every page, and verify every thread has `isResolved: true`.

3. **Config pre-merge checks**: read `git.preMergeChecks` from
   `.claude/notion-dev.config.json` in the primary checkout (an ordered list of skill names; empty by default).
   Invoke each skill in order via the Skill tool. If any skill signals failure, stop
   and report which check failed and why — never merge past a failing configured check.

4. **Caller's pre-merge check**: if `--pre-merge-check` was provided, evaluate it now — after the other gates pass and immediately before the merge command (`git fetch origin` first if the check references remote state). If it fails, apply the remediation the check describes (then re-satisfy gates 1–3 if that pushed new commits); if it cannot be satisfied, stop and report. Never merge with a failing pre-merge check.

Read the merge strategy from .claude/notion-dev.config.json → git.mergeStrategy (default "squash") in the primary checkout. Then merge (per the configured strategy) into the PR's base branch (`baseRefName` — never retarget) and delete the remote branch:

```bash
gh pr merge <pr> --<strategy> --delete-branch   # <strategy> = git.mergeStrategy, default squash
```

If the merge command exits non-zero, do **not** re-run it — check `gh pr view <pr> --json state` first. `--delete-branch` can fail on its local-cleanup step *after* the remote merge succeeded (typical when the branch is checked out in a worktree, as in the ticket and finalize flows — see cli/cli#13380). If state is `MERGED`, the merge succeeded: just finish the remote branch deletion (`git push origin --delete <head-branch>`) and continue. Only if state is still `OPEN` diagnose the merge itself. Leave local branch and worktree removal to the caller.

Confirm `gh pr view <pr> --json state` reports `MERGED` before declaring success. The final report states: which reviewer/loop ran (Codex, Copilot, or the local fallback), rounds run, findings applied vs. declined (with reasons), the merge commit SHA (`gh pr view <pr> --json mergeCommit` after the merge), the number of fix commits pushed during the loop, and any judgment calls resolved autonomously in non-interactive mode — callers consume the merge SHA and counts for their ticket records and ledger metrics. If the round cap was hit, note it and list the findings that were disagreed with or could not be fully addressed. **When the local fallback ran, state prominently that no cross-model review validated this PR**, and why (`quota` / `not-configured` / `error` / `silent`).

## Safety rules

- **Never** merge while any required check is failing or pending.
- **Never** merge while unresolved review threads remain.
- **Never** run more than 10 reviewer rounds or 10 local review rounds.
- **Never** re-trigger the reviewer (codex comment or copilot reviewer-request) again after unavailability was detected — the switch to the local loop is permanent for the run.
- Red CI takes priority over review handling at the start of every round.
- Always merge into the PR's base branch; never retarget.
- Never respond twice to the same comment; never reapply already-applied changes.
- The judgment bar (step 2) applies to every finding from every source — a well-reasoned decline beats a low-confidence edit, and neither loop manufactures work from theoretical findings.
- If the PR becomes unmergeable, is closed, or has conflicts that cannot be resolved safely: **stop and report** — do not force anything.

## Additional Resources

- **`references/github-api.md`** — exact `gh` commands: paginated comment reads, the GraphQL reviewThreads query and its cursor rules, thread-to-comment mapping, reply and resolve mutations.
