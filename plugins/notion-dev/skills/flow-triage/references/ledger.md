# Flow-triage outcome ledger

Per-repo memory of triage decisions and their outcomes. Read by the flow-triage skill (gray-zone tie-break, drift check); written by flow-triage (decision lines) and by the notion-dev commands' cleanup steps — `/notion-dev:ticket` Phase 9 and `/notion-dev:finalize` Phase 4 (outcome lines).

## Location

`<repo root>/.claude/notion-dev/ledger.jsonl` — in the **primary checkout** of the target repo, never inside a feature worktree (worktrees get deleted).

On first write, create the directory with a self-ignoring gitignore so ledger appends never dirty the tree and never touch the repo's tracked `.gitignore`:

```bash
mkdir -p .claude/notion-dev
[ -f .claude/notion-dev/.gitignore ] || printf '*\n' > .claude/notion-dev/.gitignore
```

Teams that want to share calibration can delete that `.gitignore` and commit the ledger — the format doesn't care.

## Format

Append-only JSONL. Two event kinds, joined by `run_id`:

```json
{"event":"decision","run_id":"add-api-rate-limiting","ts":"2026-07-17T10:00:00Z","description":"Add rate limiting to the API","scores":{"blast_radius":1,"depth":2,"ambiguity":1,"novelty":1,"risk":2,"verification_cost":1,"plan_shape":1},"total":10,"flow_recommended":"feature-dev","flow_chosen":"superpowers","confidence":"borderline","ledger_influenced":false}
{"event":"outcome","run_id":"add-api-rate-limiting","ts":"2026-07-17T11:05:00Z","result":"merged","review_rounds":2,"fix_commits":1,"files_changed":6,"insertions":180,"deletions":22,"duration_minutes":65,"plan_review_findings":5,"plan_review_accepted":3,"plan_review_declined":2,"plan_review_unresolved":0,"triage_absorbed":2,"triage_filed":1,"triage_dropped":1,"triage_reclassified":0,"completeness_criteria":4,"completeness_met":4,"completeness_unverified":0,"completeness_items":0}
```

Field notes:

- `run_id` — the notion-dev commands pass the ticket key (`<KEY>-<id>`); standalone triage derives a kebab-case slug from the description (lowercase, alphanumerics and hyphens, ~40 chars).
- `scores` and `flow_recommended` are `null` on a forced decision (`--forced-flow`), with `"confidence":"forced"`. On a decision made with a **scout degraded** (scout probe failed twice), the unscored dimensions and `total` are `null` (a partial `scores` object) — decision lines with `total: null` are excluded from the gray-zone ±3 score matching. `confidence` may also be `"bug-rule"` — the bug hard rule triggered: `scores` is `null`, and `flow_recommended`/`flow_chosen` are both `"superpowers"`.
- `flow_chosen` ≠ `flow_recommended` records a user override — the strongest calibration signal.
- `result` is one of `"merged"`, `"stopped"`, `"failed"`.
- `plan_review_*` — written by the `plan-review` step on the `superpowers` build path (total findings, accepted, declined, and accepted-but-unfixed). All `null` wherever there is no review signal: the `feature-dev` path, which has no plan artifact to review, and a degraded review, where the reviewer never ran — `null` rather than the zeros a degraded output block carries, since `0` findings would be indistinguishable from a review that ran clean. Added after the original schema; readers must tolerate their absence in older lines.
- `triage_absorbed` / `triage_filed` / `triage_dropped` / `triage_reclassified` — the run's **code-review** triage outcome, counted from `review-and-merge`'s `ABSORBED` / `FILED` / `DROPPED` lists only. `plan-review`'s `TRIAGE:` items are deliberately **excluded**: its `absorb` items become plan tasks and are built as ordinary work, so they can never be reclassified at the merge gate. Counting them would inflate the denominator and understate `triage_reclassified / triage_absorbed`, which is the one ratio these fields exist to expose. The counts are how many code-review findings were absorbed into this change, filed as their own work, dropped with a rationale, and — of the absorbed ones — how many were later **reclassified** to `file` at the merge gate. `triage_reclassified` is the calibration signal: an item is `absorb` precisely because no blast-radius criterion was true, so a run that reclassifies a large share of them is evidence the criteria are miscalibrated or that round-cap pressure is driving escapes. Compare it against `triage_absorbed`, not against the total. All four are `null` — never `0` — wherever no review produced a triage (a degraded review, or a run that stopped before review), since `0` would be indistinguishable from a run that triaged nothing. Added after the original schema; readers must tolerate their absence in older lines.
- `completeness_criteria` / `completeness_met` / `completeness_unverified` / `completeness_items` — the completeness gate's outcome: how many acceptance criteria it evaluated, how many settled as `met` after the gate resolved their citations, how many it could not settle at all, and how many items it raised across its three charges. `completeness_unverified` is the health signal for the check itself — a run that cannot verify its own criteria has not passed them, and a rising rate means the verifier or its citations are failing rather than the work improving. Compare `completeness_met` against `completeness_criteria`, never against the item count. All four are `null` — never `0` — wherever no completeness check ran: a run with no criteria file and no changed prose, or one that stopped before the gate. `0` would be indistinguishable from a check that ran and found everything met, which is the opposite conclusion. That is also distinct from `CRITERIA-TOTAL: 0`, which the gate reports whenever it ran its claim and caveat charges but had no criteria file to check — a check that ran and found nothing, not one that never ran; that `0` belongs in `completeness_criteria` as a real `0`, not a `null`. Added after the original schema; readers must tolerate their absence in older lines.
- Any outcome metric that cannot be determined is `null`, never guessed.

## Reading rules (tolerance)

- File missing or empty → proceed stateless; never create it just to read.
- Skip lines that are not valid JSON or lack `event`/`run_id` — silently, without failing the run.
- A `decision` with no matching `outcome` is an **orphan** (a run that died before its command's cleanup/ledger step).

## Orphan sweep

When flow-triage reads the ledger at the start of a run (not in `--advise-only` mode), it appends a closing outcome for every orphan from a **previous** run:

```json
{"event":"outcome","run_id":"<orphan run_id>","ts":"<now UTC>","result":"stopped","review_rounds":null,"fix_commits":null,"files_changed":null,"insertions":null,"deletions":null,"duration_minutes":null}
```

Abandoned runs stay recorded for future calibration analysis; the gray-zone rule itself only consumes runs whose outcome is `merged`.
