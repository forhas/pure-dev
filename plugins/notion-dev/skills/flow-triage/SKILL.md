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

If the scout fails, returns nothing at all, or its output lacks the required sections, retry once with the same prompt. If it fails again, **degrade**: score `ambiguity`, `novelty`, and `risk` from the description alone; set `blast_radius`, `depth`, `verification_cost`, and `plan_shape` to `null`; treat the result as gray zone with confidence `borderline`. Interactive: present what is known and let the user pick the flow. `--auto`: recommend `feature-dev` and record the degradation in the output's `DRIFT:` line as `scout unavailable — description-only scoring`. In degraded mode the output block (Step 7) uses `TOTAL: n/a (scout degraded)`; per-dimension `null` entries for `blast_radius`, `depth`, `verification_cost`, and `plan_shape`, each justified as `scout unavailable`; `SCOUT-FINDINGS: (unavailable — scout degraded)`; and `MICRO-PLAN: (unavailable — scout degraded)`.

**A zero-byte result is its own failure shape — not a malformed one.** An agent that signals idle with no payload has not returned a report lacking required sections; it has returned nothing, and a check written against output that is *missing or malformed* does not cover an empty result at all. Handle it explicitly: **send one follow-up message** restating the required output format and saying plainly that the reply body is the deliverable — nothing else the agent produced reaches the caller. Measured in a client: six review seats in one run each returned zero bytes, and that single nudge recovered **all six on the first attempt**.

**The nudge is not a remedy, and must never be treated as one.** On the same host and the same plugin version eight hours later, the identical nudge was applied to two agents and recovered neither — each returned zero bytes twice. The two conditions are **indistinguishable at the moment of failure**: both present as a contentless idle, and only the response to the nudge tells them apart. So nudge **once**, then treat a still-empty result as the failure it is. Never read "the agent went idle" as "the agent finished successfully" — that silently converts a seat that never ran into a clean verdict, which is the one outcome an independent-review seat exists to make impossible.

**Distinguish "the scout failed and nothing else is known" from "the scout failed but the caller already holds equivalent findings."** The degradation above assumes the first, and applying it to the second degrades the *recommendation* rather than the evidence. On tickets whose gate involves empirical probing, the caller has often already established the affected files and the relevant precedent by direct reads before dispatching the scout at all — and nulling those dimensions then pushes a well-evidenced ticket into the gray zone on a technicality. So: when the caller holds findings that answer a dimension directly, **score that dimension from them**, cite the direct finding in its justification exactly as a scout finding would be cited, and record the substitution on the `DRIFT:` line as `scout unavailable — scored from caller's direct findings`. Null only the dimensions nothing answers. Measured once in a client, where description-only scoring would have understated a 15/24 ticket. This is not licence to invent evidence: a dimension with no direct finding behind it is still `null`, and a run with no prior findings at all still takes the full degradation above.

**Say what the output block then carries — the degraded-mode rule above is unconditional, and left alone it discards everything this substitution just recovered.** That rule emits `TOTAL: n/a (scout degraded)`, `borderline`, and `--auto` → `feature-dev` whatever was scored, so the 15/24 case it was written for still lands on `feature-dev`. Two states, and only the first is a normal scoring run:

- **All seven dimensions answered** — nothing is `null`, so there is nothing degraded about the score. Compute `TOTAL` normally and route it through the ordinary thresholds and confidence rules, exactly as a delivered scout would have. `--auto` recommends whatever that total selects; it does **not** fall back to `feature-dev`. The `DRIFT:` line still records the substitution — the evidence came from the caller rather than the scout, and that is worth disclosing even though the score is complete.
- **Some answered, some still `null`** — the score is genuinely incomplete, so the degradation above stands: gray zone, confidence `borderline`, `TOTAL: n/a (scout degraded — <k>/7 scored from caller findings)`, and `--auto` recommends `feature-dev`. Each answered dimension still carries its real value and its cited justification rather than `scout unavailable`, so a reader sees what was established; the recommendation is what stays conservative, because one missing dimension can move a total across a threshold.

The distinction is which of the two the run is actually in — never how much evidence it feels like it has.

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
