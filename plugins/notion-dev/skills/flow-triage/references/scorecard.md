# Flow-triage scorecard

Score each dimension 0–3 from the scout's findings using the anchors below. When findings sit between anchors, round **up** — underestimating task size is the expensive mistake. Every score needs a one-line justification citing something concrete the scout found.

## Dimensions

| Key | Dimension | 0 | 1 | 2 | 3 | Weight |
|-----|-----------|---|---|---|---|--------|
| `blast_radius` | How much of the repo changes | one file | 2–3 files in one module | several modules in one subsystem, or two subsystems | crosses 3+ subsystems | 1 |
| `depth` | New surface vs deep modification | new isolated surface (new files nothing depends on yet) | additive changes behind existing interfaces | changes behavior of shared code with a handful of dependents | modifies core/shared code many things depend on | 1 |
| `ambiguity` | How specified the ask is | fully specified | minor choices with obvious defaults | one significant open decision | multiple plausible interpretations of the ask | 1 |
| `novelty` | Design precedent in this repo | existing pattern to copy | variation of an existing pattern | new pattern in a familiar domain | design with no precedent in the repo | 1 |
| `risk` | Cost of getting it wrong | cosmetic/internal only | user-visible but easily reversible | touches persistence or external integrations | auth, data migrations, concurrency, or public API contracts | 1 |
| `verification_cost` | Effort to prove it works | trivially unit-testable | unit tests plus modest setup | needs an integration harness | cross-cutting/integration verification or hard-to-test surface | 1 |
| `plan_shape` | Shape of the micro-plan sketch | ≤3 loosely-coupled tasks, no `UNKNOWN:` markers | 4–6 tasks, shallow dependencies, no `UNKNOWN:` markers | 6+ tasks, or one `UNKNOWN:` marker, or a dependency chain 3+ deep | long dependent chains (most tasks depend on a prior one) or 2+ `UNKNOWN:` markers | **2** |

**Total** = `blast_radius + depth + ambiguity + novelty + risk + verification_cost + 2 × plan_shape`. Maximum 24.

## Thresholds

| Total | Recommendation | Confidence |
|-------|----------------|------------|
| ≤ 9 | feature-dev | clear |
| 10–13 | gray zone — apply the gray-zone rule below | borderline |
| ≥ 14 | superpowers | clear |

## Gray-zone rule

Consult the ledger (`references/ledger.md`) for past runs in this repo with a `merged` outcome and a non-null total within ±3 of this one:

- If similar-scored **feature-dev** runs needed ≥3 review rounds or ≥2 post-review fix commits → lean **superpowers**.
- If similar-scored **superpowers** runs merged with ≤1 review round and ≤1 fix commit → lean **feature-dev**.
- No comparable history, or the evidence is mixed → default **feature-dev** (the cheaper flow).

State in the output which past runs (by `run_id`) influenced the lean, or `LEDGER-EVIDENCE: none`.

## Drift check (report-only)

Look at the last 5 runs that have both a decision and an outcome:

- If runs scored ≤9 (feature-dev, clear) repeatedly needed ≥3 review rounds → report: "the rubric may be under-scoring tasks in this repo; consider raising sensitivity."
- If runs scored ≥14 (superpowers, clear) repeatedly merged with ≤1 review round and small diffs → report: "the rubric may be over-scoring tasks in this repo."

Report drift in the `DRIFT:` output line. **Never adjust thresholds or weights yourself** — threshold changes are a human edit to this file.
