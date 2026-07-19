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
{"event":"outcome","run_id":"add-api-rate-limiting","ts":"2026-07-17T11:05:00Z","result":"merged","review_rounds":2,"fix_commits":1,"files_changed":6,"insertions":180,"deletions":22,"duration_minutes":65}
```

Field notes:

- `run_id` — the notion-dev commands pass the ticket key (`<KEY>-<id>`); standalone triage derives a kebab-case slug from the description (lowercase, alphanumerics and hyphens, ~40 chars).
- `scores` and `flow_recommended` are `null` on a forced decision (`--forced-flow`), with `"confidence":"forced"`. On a decision made with a **scout degraded** (scout probe failed twice), the unscored dimensions and `total` are `null` (a partial `scores` object) — decision lines with `total: null` are excluded from the gray-zone ±3 score matching. `confidence` may also be `"bug-rule"` — the bug hard rule triggered: `scores` is `null`, and `flow_recommended`/`flow_chosen` are both `"superpowers"`.
- `flow_chosen` ≠ `flow_recommended` records a user override — the strongest calibration signal.
- `result` is one of `"merged"`, `"stopped"`, `"failed"`.
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
