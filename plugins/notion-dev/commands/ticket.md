---
description: Resolve one Notion ticket with a cohesive implementation owner, independent review, and journaled recording.
argument-hint: "[<ticket>] [--non-interactive] [--flow=lean|superpowers|feature-dev] [| guidance]"
---

# /notion-dev:ticket

Default flow: **lean**. This command's owner investigates and implements the whole cohesive
change. Do not invoke flow-triage, writing-plans or subagent-driven-development by default.
A ticket's risk controls investigation/review depth, not the number of tiny implementation tasks.
Invoke only at the user's request or through an authorized next-task run; never autonomously
select a ticket merely because this command is available.

Explicit `--flow=superpowers` or `--flow=feature-dev`: read
`${CLAUDE_PLUGIN_ROOT}/references/legacy/ticket.md` and execute that opt-in flow.
A pre-0.36 marker/runtime resumes through that reference too; preserve its invocation and budgets.
Do not read legacy workflows on a new lean run. Reject unknown flags/flows.

## 1. Intake and ownership

Read `${CLAUDE_PLUGIN_ROOT}/references/lean-intake.md` and follow it. It owns preflight,
full ticket retrieval, epic/ownership/dependency checks, clarification, runtime readiness,
worktree claim, initial Notion status and optional epic bootstrap. Pass existing next-task
source/context paths; validate identity/freshness before reuse.

Keep `REPO_ROOT`, `RUNTIME_STATE`, `RUN_MARKER`, `WORKTREE`, branch and ticket identity.
All script examples use `python3` as the configured `knowledge.python` executable
(`python` or `py -3` on Windows), not an assumed command.

## 2. Understand and implement

Record runtime stage `implementation`; update the owned marker at meaningful boundaries.
Read project instructions and the full authoritative ticket. Start with relevant epic context,
known constraints and candidate code paths; retrieve further code/history only to answer a
specific question. Persist confirmed decisions, code locations, rejected approaches and open
questions in one compact `context.md` next to runtime state. Never copy whole conversations.

Write an outcome plan in that context: changes, affected contracts, acceptance/edge-case tests,
risks and validation commands. Do not write a code-complete transcription plan or split coupled
function/call-site/test/docs changes into separate worker tasks. The implementation owner may
correct test setup, helper choices and line ranges without asking permission to deviate from
a proposed implementation; requirements and explicit user decisions still govern.

`context.md` owns the compact decision record: decision, essential reason, evidence and release
obligations. Other summaries derive from these facts, not new explanations. Required detail
stays accessible by reference; do not copy the same condition list into every surface by default.

**Design review when warranted:** unresolved architecture, financial/security invariants,
migration/data-loss risk, or a public contract change merits a bounded independent `plan`
worker via `references/runtime.md`. Give it the short decision record and authoritative
requirements, not implementation code written in advance. Resolve its required findings before
coding. For a bug, reproduce the failure and inspect root cause; delegate a separate scout
only for a concrete unanswered question that benefits from independent investigation.

Implement and test in the worktree. Preserve unrelated changes. Use existing helpers. Validate
the actual behavior, including test isolation and assertions that could pass without exercising
the new path. Update contract/docs/generated files required by the ticket. Do not waive release
approval, credentials or scope decisions in non-interactive mode. Ask only for genuinely missing
authority or requirements; stop honestly if they cannot be resolved.

## 3. Validate and prepare the PR

Record runtime stage `validation` and update the owned marker.
Commit the completed source changes with the ticket key; do not commit runtime/context artifacts.
For a plugin repository, bump its manifest once per PR and ensure it exceeds the current base.
Preparation commands that modify tracked files run before final validation; commit their output.

Run the shared verifier, capturing full logs (including named tests), not piped tails:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" verify --project "$REPO_ROOT" --state "$RUNTIME_STATE" --worktree "$WORKTREE"
```
It reuses applicable passing receipts; failed/stale checks execute. Declare ignored/generated
verification inputs with repeated `--depends`; environment-sensitive checks without a complete
dependency declaration must run through `runtime.py verify` without `--reuse`.
On a failing check investigate/fix, respecting each configured step's `retries` limit (default 3);
do not rerun merely to discover the output shape. Report `exit_code`, `duration_seconds` and
the log path returned by the helper. No configured checks: establish appropriate commands with
the user (or from documented project commands when unambiguous), never report untested success.

Push only the ticket branch. Open a PR against `git.prTargetBranch` or `git.baseBranch`.
Keep its body small: requirement/outcome, actual behavior change, verified tests and known risks.
Include all ticket-mandated disclosure/checklist/sign-off wording. Distinguish merge prerequisites
from release-only obligations using the ticket's actual words. Do not invent sign-off.
Avoid volatile counts, file line numbers and narratives unless necessary or generated from evidence.
Render `pr-facts.json` (`requirement`: string; `behavior`, `validation`, `risks`, `mandatory`:
string lists) with `workflow.py pr-body --facts <pr-facts.json> --output <pr-body.md>`.
Use that file for the PR and frozen `pr_body`. Rendering is not verification. Correct to a new
file, reconciling human edits and preserving mandatory wording. Review status stays in runtime,
not a new PR-body history requiring another review.

Through ticket-system, set the PR property. Save branch, tests, PR identity and the implementation
summary in context. Defer the final Notion `Implementation` narrative to recording; preserve
unrelated sections. Do not write review history into the ticket while its source is frozen.

## 4. Review and merge

Invoke `notion-dev:review-and-merge` with PR number, runtime path, marker, authoritative ticket,
inventory and the verification receipts. It owns configured external review, a combined
independent code/completeness review, delta checks and merge gates. Do not separately dispatch
a whole-branch reviewer and then rediscover the same facts in a completeness worker.
Persist the returned structured result and review report; no re-summarization for another agent.

## 5. Record and finish

After confirmed merge, read `${CLAUDE_PLUGIN_ROOT}/references/record.md` and execute its shared
journaled routine **inline**. It is also finalize's routine; do not dispatch a generic record
agent or reload investigation history. Carry the technical knowledge delta already learned.

Run the workspace pass of `notion-dev:session-closeout` over owned artifacts and the finished
draft. Report ticket/PR/merge, requirement and test evidence, Notion/knowledge/epic outcomes,
release obligations and runtime path. Mark the owned run `complete` only after recording and
closeout using `workflow.py complete --state "$RUNTIME_STATE" --marker "$RUN_MARKER"`;
keep evidence outside disposable worktrees. `OUTCOME: resolved` is valid only then.

## Failure and waiting

Non-interactive continues authorized work without suppressing missing authority. Follow
`references/runtime.md` for worker waits, delivery and cancellation; pending is unfinished,
not failed. No duplicate waiters.

On failure preserve the branch/worktree/PR and runtime. Update the owned marker to `stopped`
with the actual cause before ending the turn. Name only artifacts whose existence was checked.
Use `/notion-dev:finalize <pr>` for a PR already opened; otherwise resume this invocation.
Record unexpected failures through issue-log once with evidence, not a new investigation loop.
Never release a primary lock over a record writer that has not been confirmed stopped.
