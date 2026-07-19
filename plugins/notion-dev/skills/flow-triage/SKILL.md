---
name: flow-triage
description: This skill should be used when the user runs "/flow-triage" or "/notion-dev:flow-triage", asks "which flow fits this ticket", "triage this ticket", "should this use feature-dev or superpowers", or when a notion-dev command needs to choose a build flow for a ticket. Recommends feature-dev or superpowers via a bug-type hard rule, a codebase-aware scorecard, and a per-repo outcome ledger.
argument-hint: "[--auto] [--advise-only] [--forced-flow=<flow>] [--ticket-type=<type>] [--ledger-root=<path>] [--run-id=<id>] <ticket title + body>"
---

# flow-triage — choose the build flow

Recommend which build flow fits a feature: **feature-dev** (small–medium tasks) or **superpowers** (medium-plus and large tasks). A read-only scout probes the codebase, a deterministic scorecard turns its findings into a score, and a per-repo ledger of past outcomes breaks ties. The heuristic must never block development — every failure degrades to a usable recommendation.

## Input

Arguments: `$ARGUMENTS`

Parse and remove flags; everything remaining is the **ticket description (title + body)** (required — if empty, stop and ask):

- `--auto` — no confirmation prompt; the recommendation is final.
- `--advise-only` — analysis only: no ledger writes of any kind (no decision line, no orphan sweep). Standalone advisory use ("which flow would this be?") should pass this flag — otherwise the run writes a decision line that can never receive a real outcome.
- `--forced-flow=<flow>` — the caller already chose; skip the probe and scoring. Valid values: `feature-dev`, `superpowers`. Anything else: stop and report the two valid values.
- `--ticket-type=<type>` — the ticket's logical type from the ticket system (`feature`, `bug`, `improvement`, `research`, …). Omitted when the ticket database exposes no type property. Drives the bug hard rule (Step 2b).
- `--ledger-root=<path>` — directory containing `.claude/notion-dev/`. Default: `git rev-parse --show-toplevel`. Callers running inside a worktree MUST pass the primary checkout's root explicitly.
- `--run-id=<id>` — ledger join key. Default: kebab-case slug of the description (lowercase, alphanumerics and hyphens, ~40 chars).

## Step 1 — Read the ledger

Read `<ledger-root>/.claude/notion-dev/ledger.jsonl` following the tolerance rules in `references/ledger.md`: missing file → stateless; malformed lines → skip silently. Then, unless `--advise-only`, run the **orphan sweep** defined there (close prior runs' dangling decisions with `result: "stopped"`).

## Step 2 — Forced flow shortcut

If `--forced-flow` was given: skip Steps 3–6. Unless `--advise-only`, ensure the ledger directory exists with its self-ignoring `.gitignore` (commands in `references/ledger.md`), then append a decision line with `scores: null`, `flow_recommended: null`, `confidence: "forced"`, and `flow_chosen` set to the forced value. Emit the output contract (Step 7) with `FLOW:` = forced value, `CONFIDENCE: forced`, `TOTAL: n/a`, `SCORES: n/a`, `LEDGER-EVIDENCE: none`, `DRIFT: none`, `SCOUT-FINDINGS: (skipped — flow was forced)`, `MICRO-PLAN: (skipped — flow was forced)`. Done.

## Step 2b — Bug hard rule

Bugs route to superpowers unconditionally (systematic debugging and TDD discipline beat
speed on defects). This rule runs only when no `--forced-flow` was given — a forced flow
always wins.

Determine bug-ness:
- `--ticket-type` was passed → it is authoritative: `bug` triggers the rule; any other
  value (or `--ticket-type` absent but the description clearly a non-defect) does not.
- `--ticket-type` absent → infer from the description: treat it as a bug only when it
  clearly describes a defect in existing behavior (e.g. "fix", "broken", "crash",
  "regression", an error message, expected-vs-actual symptoms). When in doubt, it is
  not a bug — fall through to the scorecard.

If the rule triggers: skip Steps 3–6. Unless `--advise-only`, ensure the ledger
directory exists with its self-ignoring `.gitignore` (commands in
`references/ledger.md`), then append a decision line with `scores: null`,
`flow_recommended: "superpowers"`, `confidence: "bug-rule"`, and
`flow_chosen: "superpowers"`. Emit the output contract (Step 7) with
`FLOW: superpowers`, `CONFIDENCE: clear`, `TOTAL: n/a`, `SCORES: n/a (bug rule)`,
`LEDGER-EVIDENCE: none`, `DRIFT: none`,
`SCOUT-FINDINGS: (skipped — bug hard rule)`, `MICRO-PLAN: (skipped — bug hard rule)`.
No confirmation prompt — the rule is deterministic. Done.

## Step 3 — Scout probe

Dispatch **one** read-only `Explore` agent (search breadth: medium), synchronously. The scout must not write files, commit, or modify anything. Prompt it with the ticket description (title + body), the current directory as the codebase to probe, and this exact required return format:

```
AFFECTED: <files/modules expected to change, one per line, each with a short why>
PATTERN: <existing repo pattern that already covers this kind of change, or NONE>
OPEN-QUESTIONS: <questions the description leaves unanswered, one per line, or NONE>
MICRO-PLAN:
<ordered implementation task list, one line per task, with "(depends on N)" notes where a task needs an earlier one, and an "UNKNOWN:" prefix on any task whose approach it could not determine>
```

If the scout fails or its output lacks the required sections, retry once with the same prompt. If it fails again, **degrade**: score `ambiguity`, `novelty`, and `risk` from the description alone; set `blast_radius`, `depth`, `verification_cost`, and `plan_shape` to `null`; treat the result as gray zone with confidence `borderline`. Interactive: present what is known and let the user pick the flow. `--auto`: recommend `feature-dev` and record the degradation in the output's `DRIFT:` line as `scout unavailable — description-only scoring`. In degraded mode the output block (Step 7) uses `TOTAL: n/a (scout degraded)`; per-dimension `null` entries for `blast_radius`, `depth`, `verification_cost`, and `plan_shape`, each justified as `scout unavailable`; `SCOUT-FINDINGS: (unavailable — scout degraded)`; and `MICRO-PLAN: (unavailable — scout degraded)`.

## Step 4 — Score

Score the scout's findings on the seven dimensions in `references/scorecard.md`, each with a one-line justification citing something concrete the scout found. Compute `total = blast_radius + depth + ambiguity + novelty + risk + verification_cost + 2 × plan_shape`.

## Step 5 — Recommend

Apply the thresholds in `references/scorecard.md`: ≤9 → `feature-dev`, confidence `clear`; ≥14 → `superpowers`, confidence `clear`; 10–13 → gray zone, confidence `borderline` — apply the scorecard's gray-zone rule against the ledger entries read in Step 1 and note which `run_id`s influenced the lean.

## Step 6 — Drift check

Run the scorecard's report-only drift check over the last 5 completed runs. Any warning goes in the `DRIFT:` output line. Never adjust thresholds or weights.

## Step 7 — Confirm, record, output

1. **Confirm** (skip with `--auto`): present the full output block below, then ask the user to confirm the recommendation or override to the other flow (AskUserQuestion; on `borderline` confidence, say explicitly that their judgment matters most in the gray zone). `flow_chosen` is whatever they pick; with `--auto` it equals the recommendation.
2. **Record** (skip with `--advise-only`): ensure the ledger directory exists with its self-ignoring `.gitignore` (commands in `references/ledger.md`), then append the decision line per the schema there.
3. **Output** — end with exactly this block so callers can parse it:

```
FLOW: <feature-dev|superpowers>
CONFIDENCE: <clear|borderline|forced>
TOTAL: <n>/24
SCORES:
- blast_radius: <n> — <justification>
- depth: <n> — <justification>
- ambiguity: <n> — <justification>
- novelty: <n> — <justification>
- risk: <n> — <justification>
- verification_cost: <n> — <justification>
- plan_shape: <n> (weight 2) — <justification>
LEDGER-EVIDENCE: <none | which run_ids influenced the decision and how>
DRIFT: <none | warning text>
SCOUT-FINDINGS:
<the scout's AFFECTED / PATTERN / OPEN-QUESTIONS sections verbatim, or "(skipped — flow was forced)" / "(unavailable — scout degraded)">
MICRO-PLAN:
<the scout's micro-plan sketch verbatim>
```

`FLOW:` reflects `flow_chosen` (post-confirmation), not the raw recommendation. Callers hand the `MICRO-PLAN:` block to the chosen flow as seed context.
