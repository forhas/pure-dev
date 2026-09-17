# Parallel Tickets (PR 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let several tickets of one epic resolve in parallel on one machine — each in its own session and worktree — without stepping on each other's pick, brief, primary checkout, or merge; and settle the three decisions PR 1's review filed (#44 run ids, #45 drift on title/order, #46 `--pr` rebase).

**Architecture:** The claim stays the worktree; a JSON run marker under `.claude/notion-dev/runs/` says whether a claim is live. `/notion-dev:ticket` gains an ownership check, marker-driven resume rules, and a `claimed-elsewhere` outcome; `/notion-dev:next-task` skips a lost claim and reads the marker. `review-and-merge` (both plugin copies plus the `.claude/skills/` mirror) rebases once at the merge gate and resolves the manifest-version conflict itself. `knowledge.py next` reports title and order drift. Commands without natural identity generate a per-invocation lock run id. `new-info --pr` rebases its note branch when the epic branch moved.

**Tech Stack:** Markdown instruction files; bash harnesses on `scripts/lib/assert.sh`; Python 3 stdlib; git; `gh`.

**Spec:** `docs/superpowers/specs/2026-09-15-brief-freshness-and-parallel-tickets-design.md` — §7, §8, §9 last row, §10 PR 2, §11 step 2, plus the PR 2 clauses in §2 (drift), §4 (run ids), and §7's last bullet (`--pr` rebase). The spec is the authority; every literal below comes from it.

## Global Constraints

- **CLAUDE.md harness rules** bind every assertion: mechanisms not prose; `assert_present` matches exactly one line per region; A2 label coverage (a backticked span in a label must appear in the regex; `assert.sh` requires this unconditionally, so use lowercase phase words in labels as PR 1 did); declared duplicates use `assert_count` (counts lines); mutation-prove every new assertion; commit before mutating.
- **Only `scripts/lib/assert.sh` helpers** in harnesses; `verify-assertions.sh` audits every harness.
- **Two version bumps, each exactly once**: `plugins/notion-dev/.claude-plugin/plugin.json` `0.25.0 → 0.26.0`; `plugins/quick-dev/.claude-plugin/plugin.json` `0.14.2 → 0.15.0`. Both in Task 6.
- **The `.claude/skills/review-and-merge/` mirror** must stay byte-identical to `plugins/quick-dev/skills/review-and-merge/` (`scripts/verify-mirror.sh`): after editing the quick-dev copy run `cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/`. The `notion-dev` copy is a deliberate fork — apply the same change with its own wording (it has six gates, quick-dev five).
- **Read-once and minimal brief** still bind: no command reads the bundle twice; nothing is added to the brief's format in this PR.
- **Same machine only**: no cross-machine claim; the marker is a local file the flow writes directly (no script).
- **Every line a harness regex must match stays on ONE line.**
- **Commit trailer** on every commit: `Claude-Session: https://claude.ai/code/session_017vRi7JmxR1P7uoGpke4Vhc`.
- **Full suite** before every commit touching a harness or a guarded file: `for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done`.
- **Pinned literals** (one line each, verbatim):

  > **Superseded where the repository disagrees.** This plan is the historical argument for
  > PR #47 (merged as `013ff23`); the shipped files and `scripts/verify-*.sh` are the
  > authority. Three literals below were reversed during implementation and review and are
  > corrected in place, each marked **superseded** with what replaced it. Do not replay a
  > superseded literal — one of them is now affirmatively forbidden by the verify suite.

| id | file | literal |
|---|---|---|
| L1 | ticket.md 1.1 | `[<key>] is In Progress and has no worktree here — held elsewhere` |
| L2 | ticket.md 1.2 | `held by a live session — <phase> since <heartbeat>` |
| L3 | ticket.md 2.1 | `$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json` |
| L4 | ticket.md 2.1 | `OUTCOME: claimed-elsewhere` |
| L5 | ticket.md 2.1 | `"state": "running"` and, on the stop path, `"state": "stopped"` |
| L6 | ticket.md 9 step 1 | `rm -f "$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json"` |
| L7 | next-task.md | `claimed-elsewhere` (step 4: neither a stop nor a resolution) |
| L8 | review-and-merge (both) | `gh pr view <pr> --json mergeStateStatus` |
| L9 | review-and-merge (both) | `git rebase origin/<base>` |
| L10 | review-and-merge (both) | `git push --force-with-lease` |
| L11 | review-and-merge (both) | `.claude-plugin/plugin.json` version conflict rule sentence containing `take the base's value` and `bump class` |
| L12 | knowledge.py / fixtures | `drift: <KEY> title differs from live` and `drift: numbered order differs from derived` |
| L13 | new-info.md, knowledge.md, create-task.md | `<run id>` token definition containing `$(date -u +%Y%m%dT%H%M%SZ)` |
| L14 | new-info.md apply | `git -C $REPO_ROOT rebase origin/<epicBranch>` and `git -C $REPO_ROOT rebase --abort` |
| L15 | signatures.md | **superseded** — no row. `claimed-elsewhere` is a *run outcome*, not an issue-log signature: issue-log's Kind vocabulary is closed, spec §9 was amended, and `scripts/verify-parallel.sh` now asserts the row is **absent**. Adding it turns the suite red. |

---

## File structure

| path | responsibility |
|---|---|
| `plugins/notion-dev/scripts/knowledge.py` | modify — `drift_findings` title/order comparison (#45) |
| `scripts/fixtures/knowledge/next/brief-title.md`, `brief-order.md` | new — drift fixtures |
| `scripts/verify-knowledge-py.sh` | modify — two `nx` cases |
| `plugins/notion-dev/skills/epic-doc/SKILL.md` | modify — `read`'s drift list gains title/order; `refresh` unchanged |
| `plugins/notion-dev/commands/ticket.md` | modify — 1.1 ownership check, 1.2 marker resume rules, 2.1 claim + marker + `claimed-elsewhere`, marker heartbeats, 9 step 1 delete, stop path `stopped` |
| `plugins/notion-dev/commands/next-task.md` | modify — marker validity rules, `claimed-elsewhere` handling |
| `plugins/quick-dev/skills/review-and-merge/SKILL.md`, `.claude/skills/review-and-merge/SKILL.md`, `plugins/notion-dev/skills/review-and-merge/SKILL.md` | modify — rebase at the gate, manifest-version conflict rule |
| `plugins/notion-dev/commands/new-info.md`, `knowledge.md`, `create-task.md` | modify — per-invocation run id (#44); new-info `--pr` rebase (#46) |
| `plugins/notion-dev/skills/issue-log/references/signatures.md` | **superseded** — not modified; see L15 |
| `scripts/verify-parallel.sh` | new — every mechanism above except the script's |
| `plugins/notion-dev/README.md`, both `plugin.json` | modify — running two sessions; versions |

---

### Task 1: `knowledge.py next` — title and order drift (#45)

**Files:**
- Modify: `plugins/notion-dev/scripts/knowledge.py` (`drift_findings`, ~line 1323)
- Create: `scripts/fixtures/knowledge/next/brief-title.md`, `scripts/fixtures/knowledge/next/brief-order.md`
- Modify: `scripts/verify-knowledge-py.sh` (two cases in the `== next ==` block), `plugins/notion-dev/skills/epic-doc/SKILL.md` (`read`'s drift list), `scripts/verify-epic-doc.sh` (one anchor)

**Interfaces:**
- Consumes: `_parse_next` items carry `key`, `title`, `reason`, `bold`; `prev_in_progress` is `{key: since}` (titles on the `In progress:` line are not captured today — capture them: change `_parse_next` to also return `prev_ip_titles` `{key: title}` from `IN_PROGRESS_ITEM_RE.group(2)`, and thread it through `cmd_next` to `drift_findings`).
- Produces: two new finding strings (L12). Exit codes unchanged; a re-wrapped line and a changed reason remain `DRIFT: 0`.

- [ ] **Step 1: Fixtures**

`brief-title.md` = `brief.md` with item 2 reading `2. [STO-73] Alerts — after STO-71` (title `Alerting` → `Alerts`; live title in `state-basic.json` stays `Alerting`).
`brief-order.md` = `brief.md` with the numbered list reading:

```
1. [STO-73] Alerting — after STO-71
2. **[STO-71] Cache metrics** — unblocked; STO-70 landed.
```

(both keys present, order swapped; item 1's bold moves with it).

- [ ] **Step 2: Failing harness cases** (append inside the `== next ==` block, before `printf 'no next heading\n'`):

```bash
nx title 1 "$NX/brief-title.md" "$NX/state-basic.json"
assert_has "next: a stale title is drift"   "$OUT/next-title.err" 'drift: STO-73 title differs from live'
assert_has "next: a stale title is one finding" "$OUT/next-title.err" 'DRIFT: 1'
nx order 1 "$NX/brief-order.md" "$NX/state-basic.json"
assert_has "next: a swapped numbered order is drift" "$OUT/next-order.err" 'drift: numbered order differs from derived'
assert_has "next: a swapped order is one finding" "$OUT/next-order.err" 'DRIFT: 1'
assert_has "next: a re-wrapped item is still not drift" "$OUT/next-wrapped.err" 'DRIFT: 0'
```

(The last line re-asserts the existing wrapped case's output file, which the earlier `nx wrapped` produced — keep it after that case.)

- [ ] **Step 3: Run to see them fail** — `./scripts/verify-knowledge-py.sh | grep -c FAIL` → non-zero.

- [ ] **Step 4: Implement**

In `_parse_next`, alongside `in_progress[pm.group(1)] = pm.group(3)`, record `ip_titles[pm.group(1)] = pm.group(2)`; return it as a sixth value and update `cmd_next`'s unpack. In `drift_findings` add parameters `prev_ip_titles` and compute, after the existing membership loop:

```python
    live_title = {c["key"]: c["title"] for c in state["children"]}
    prev_title = {it["key"]: it["title"] for it in prev_items}
    prev_title.update(prev_ip_titles)
    for k in sorted(k for k in prev_title if k in live_title and prev_title[k] != live_title[k]):
        f.append("drift: %s title differs from live" % k)
    prev_order = [it["key"] for it in prev_items if it["key"] in new_num]
    new_order = [c["key"] for c in numbered if c["key"] in prev_num]
    if prev_order != new_order:
        f.append("drift: numbered order differs from derived")
```

Order the findings so these two come after the membership findings and before the header finding (stderr order is not asserted, but keep it stable). A re-wrapped item has the same title and order, so it stays `DRIFT: 0`; a changed reason is never compared.

- [ ] **Step 5: `read`'s drift list**

In `plugins/notion-dev/skills/epic-doc/SKILL.md`, `read` step 2's `DRIFT` sentence lists the findings; append `; a listed child's title differs from its live title; the numbered order differs from the derived order` (one line with the existing enumeration if it is one line; otherwise a new sentence on one line). `scripts/verify-epic-doc.sh`, `read` region: `assert_present "read: title and order drift are findings" "$ED" "$R0" "$RB" 'title differs from its live title.*numbered order differs'`.

- [ ] **Step 6: Run, commit**

`./scripts/verify-knowledge-py.sh && ./scripts/verify-epic-doc.sh && ./scripts/verify-assertions.sh`, then the full suite. Commit: `feat(knowledge.py): title and order drift (#45)`.

---

### Task 2: `ticket.md` — run marker, ownership check, resume rules, `claimed-elsewhere`

**Files:**
- Modify: `plugins/notion-dev/commands/ticket.md` (1.1 after the epic guard; 1.2's "If the worktree already exists" block; 2.1 around `git worktree add`; the start of Phases 3–9 and Phase 7's round loop for heartbeats; Phase 9 step 1; the failure-and-stop path; Phase 10 report)
- Modify: `plugins/notion-dev/skills/issue-log/references/signatures.md`
- Create: `scripts/verify-parallel.sh` (ticket portion; Tasks 3–5 append)

**Interfaces:**
- Produces: the marker file contract (L3, L5), `OUTCOME: claimed-elsewhere` (L4) as the run's final line on that path, heartbeat discipline, L1/L2/L6.

- [ ] **Step 1: Failing harness** — create `scripts/verify-parallel.sh` (chmod +x), same header style as `scripts/verify-primary-lock.sh` (sources only `scripts/lib/assert.sh`; defines `ok`/`bad`):

```bash
ND=plugins/notion-dev
TICKET=$ND/commands/ticket.md
NT=$ND/commands/next-task.md
SIG=$ND/skills/issue-log/references/signatures.md
L=$(total_lines "$TICKET")
P11=$(find_line "$TICKET" 1 "$L" '^### 1\.1 '); P12=$(find_line "$TICKET" 1 "$L" '^### 1\.2 '); P13=$(find_line "$TICKET" 1 "$L" '^### 1\.3 ')
P21=$(find_line "$TICKET" 1 "$L" '^### 2\.1 '); P3=$(find_line "$TICKET" 1 "$L" '^## Phase 3 ')
P7=$(find_line "$TICKET" 1 "$L" '^## Phase 7 '); P8=$(find_line "$TICKET" 1 "$L" '^## Phase 8 ')
P9=$(find_line "$TICKET" 1 "$L" '^## Phase 9 '); P9H=$(find_line "$TICKET" 1 "$L" '^### Post-merge hooks')
P10=$(find_line "$TICKET" 1 "$L" '^## Phase 10 '); FS=$(find_line "$TICKET" 1 "$L" '^## Failure and stop conditions')
echo "== ticket.md: claim, marker, ownership =="
assert_present "1.1 ownership check: in progress with no worktree of ours aborts \`held elsewhere\`" "$TICKET" "$P11" "$P12" 'is In Progress and has no worktree here — held elsewhere'
assert_present "1.1 ownership check: non-interactive never proceeds" "$TICKET" "$P11" "$P12" 'held elsewhere.*non-interactive mode never'
assert_present "1.2 resume: a \`running\` marker with a fresh heartbeat aborts \`held by a live session\`" "$TICKET" "$P12" "$P13" 'held by a live session — <phase> since <heartbeat>'
assert_present "1.2 resume: \`stopped\`, a heartbeat older than 2 hours, or no marker resumes" "$TICKET" "$P12" "$P13" '`stopped`.*older than 2 hours.*no marker.*resume'
assert_present "1.2 resume: non-interactive never takes over" "$TICKET" "$P12" "$P13" 'non-interactive never takes over'
assert_present "2.1 claim: the marker path" "$TICKET" "$P21" "$P3" '\$REPO_ROOT/\.claude/notion-dev/runs/<KEY>-<id>\.json'
assert_present "2.1 claim: the marker is written with \`\"state\": \"running\"\`" "$TICKET" "$P21" "$P3" '"state": "running"'
assert_present "2.1 claim: a lost race ends with \`OUTCOME: claimed-elsewhere\` before any status change" "$TICKET" "$P21" "$P3" 'OUTCOME: claimed-elsewhere.*before'
assert_order "2.1: worktree add, then marker, then status, then refresh start" "$TICKET" "$P21" "$P3" \
  worktree 'git worktree add <worktree-path>' marker '"state": "running"' status 'updateStatus\(id, "inProgress"\)' refresh 'operation `refresh\(<epic-id>, start <key>\)`'
assert_present "marker discipline: heartbeat at every phase boundary and every review round" "$TICKET" "$P21" "$P3" 'heartbeat.*every phase boundary and every review round'
assert_present "phase 7: the marker is touched after every reviewer round" "$TICKET" "$P7" "$P8" 'touch the marker.*after every'
assert_present "phase 9 step 1: the marker is deleted right after the worktree is removed" "$TICKET" "$P9" "$P9H" 'rm -f "\$REPO_ROOT/\.claude/notion-dev/runs/<KEY>-<id>\.json"'
assert_order "phase 9: worktree removed, then marker deleted" "$TICKET" "$P9" "$P9H" remove 'git worktree remove <worktree-path>' marker 'rm -f "\$REPO_ROOT/\.claude/notion-dev/runs/<KEY>-<id>\.json"'
assert_present "stop path: the marker is set to \`\"state\": \"stopped\"\` with the cause" "$TICKET" "$FS" "$L" '"state": "stopped".*cause'
assert_present "phase 10 report: the marker outcome line" "$TICKET" "$P10" "$FS" '^- \*\*Run marker\*\*'
LS=$(total_lines "$SIG")
# SUPERSEDED (see L15): the row was never added. What ships asserts its absence:
assert_absent "signatures: claimed-elsewhere is a run outcome, never a signature row" "$SIG" 1 "$LS" '^\| `claimed-elsewhere` \|'
```

- [ ] **Step 2: See it fail** — `./scripts/verify-parallel.sh | grep -c FAIL` → non-zero; `./scripts/verify-assertions.sh` passes on the new file.

- [ ] **Step 3: 1.1 ownership check** — after the epic guard paragraph (before `**Epic context.**`), insert:

```
**Ownership check.** When the fetched status equals `statusMap.inProgress` (compare the live option name, never the literal) and no worktree of ours exists at the path 1.2 computes, abort: `[<key>] is In Progress and has no worktree here — held elsewhere`. Another session on this machine, or a person, has the ticket. Interactive mode may proceed on explicit confirmation via `AskUserQuestion` (the user is taking it over on purpose); for `held elsewhere` non-interactive mode never proceeds. In progress **with** our worktree is the resume case 1.2 handles.
```

- [ ] **Step 4: 1.2 resume rules** — replace the line `If the worktree already exists:` with a paragraph, keeping the existing bullet list under it unchanged:

```
If the worktree already exists, read the run marker `$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json` (2.1 defines it) before anything else:
- marker `"state": "running"` and `heartbeat` younger than 2 hours → abort with `held by a live session — <phase> since <heartbeat>`. Interactive mode offers take-over via `AskUserQuestion` (rewrite the marker's `run`, `phase` and `heartbeat` for this run, then continue below); non-interactive never takes over.
- marker `stopped`, a heartbeat older than 2 hours, or no marker at all (a worktree from before markers existed) → resume. **Superseded:** a plain rewrite-and-read is not enough — two sessions that each write and then read their own write both see themselves and both proceed into one worktree. What ships (`plugins/notion-dev/commands/ticket.md` 1.2) claims the resume atomically first: `mkdir` the `<KEY>-<id>.claim` directory (parent created with `mkdir -p`, never the claim itself), retire a claim older than the same 2-hour threshold **by rename**, re-read the marker inside the claim before rewriting it, rewrite it as `running` with a fresh per-invocation `session`, re-read, then `rmdir`. A lost claim aborts with the 1.2 `held by a live session` message and runs **none** of the resume rules.

If the worktree already exists and the marker allows a resume:
```

(The second sentence keeps the existing bullets' antecedent.) Keep L2 and the `stopped`/older-than/no-marker/resume clause each on one line.

- [ ] **Step 5: 2.1 claim, marker, `claimed-elsewhere`** — after the fenced `git worktree add` block and its config sentence, insert:

```
**The claim is the worktree.** `git worktree add … -b ticket/<project.key>-<id>-<slug>` is atomic on one machine: when it fails because the branch already exists and 1.2 found no worktree of ours, another session claimed the ticket in the window between 1.2 and here. End the run with the outcome `claimed-elsewhere` **before** any status change, ledger line, or brief write: print one line, `OUTCOME: claimed-elsewhere — [<key>] branch ticket/<project.key>-<id>-<slug> already exists; another session holds it`, and stop. Nothing to clean, nothing to report beyond that line; `/notion-dev:next-task` reads this outcome and picks another ticket. A `git worktree add` failure for any other reason (path exists, fetch failed) is the ordinary stop.

**Run marker.** Right after the worktree exists, write `$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json` (create the directory; it lives under the self-ignored `.claude/notion-dev/`):

```json
{ "run": "<KEY>-<id>", "worktree": "<worktree-path>", "branch": "ticket/<project.key>-<id>-<slug>",
  "phase": "Phase 2", "heartbeat": "<date -u +%FT%TZ>", "state": "running", "cause": null }
```

Marker discipline for the rest of the run: rewrite `phase` and `heartbeat` at every phase boundary and every review round (Phase 7 says where), set `"state": "stopped"` with `cause` on the failure path, and delete the file in Phase 9 step 1 right after the worktree is removed. A JSON file this flow writes directly; no script. The marker is what tells a second session — and `/notion-dev:next-task` — whether this claim is live (1.2's rules).
```

Keep L3, L4 (`OUTCOME: claimed-elsewhere` with `before` on the same line), `"state": "running"`, and the heartbeat sentence each on one line.

- [ ] **Step 6: Heartbeats** — at the start of `## Phase 3`, `## Phase 4`, `## Phase 5`, `## Phase 6`, `## Phase 7`, `## Phase 8`, `## Phase 9` add one short sentence: `Touch the run marker: \`phase\` = "Phase N", \`heartbeat\` = now.` (Seven lines; the harness does not count them, the 2.1 discipline sentence is the anchor.) In Phase 7, after the sentence that invokes `notion-dev:review-and-merge`, add: `While it runs, touch the marker after every reviewer round it reports (its round log), so a two-hour review does not read as an abandoned claim.` (one line containing `touch the marker` and `after every`).

- [ ] **Step 7: Phase 9 step 1 and the stop path** — in step 1, after `git worktree remove <worktree-path>` (and its `--force` retry sentence), append: `` Then `rm -f "$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json"` — the claim is gone with the worktree. `` In the failure-and-stop bullet, after the `refresh stop` sentence, add: `` Also rewrite the run marker with `"state": "stopped"` and `cause` set to the one-clause cause (the same clause `refresh stop` carried), leaving `worktree` and `branch` in place — 1.2 and `/notion-dev:next-task` read `stopped` as resumable. `` Add a Phase 10 bullet `- **Run marker** — deleted (normal) | left \`stopped\` with the cause (stop path). Omit on \`claimed-elsewhere\`.`

- [ ] **Step 8: signatures** — **superseded; do not perform.** This step originally added a `claimed-elsewhere` row after `lock-timeout:primary`. The ruling reversed during implementation (see L15): `claimed-elsewhere` is a run outcome, issue-log's Kind vocabulary is closed, spec §9 was amended, and `scripts/verify-parallel.sh:68` now asserts the row is **absent**. `signatures.md` is not modified by this plan.

- [ ] **Step 9: Run, mutation-prove, commit** — `./scripts/verify-parallel.sh ./scripts/verify-primary-lock.sh ./scripts/verify-post-merge-ordering.sh ./scripts/verify-epic-doc.sh ./scripts/verify-assertions.sh`, full suite; commit `feat(ticket): run marker, ownership check, marker resume rules, claimed-elsewhere`; then one sed per new assertion → FAIL → restore.

---

### Task 3: `next-task.md` — lost claims and marker-aware validity

**Files:**
- Modify: `plugins/notion-dev/commands/next-task.md` (step 2 validity rules and "Resume first"; step 4)
- Modify: `scripts/verify-parallel.sh` (append)

- [ ] **Step 1: Failing anchors** (append before the final `if`):

```bash
echo "== next-task.md: lost claims and the marker =="
LN=$(total_lines "$NT"); S2=$(find_line "$NT" 1 "$LN" '^### 2\. Pick'); S3=$(find_line "$NT" 1 "$LN" '^### 3\. Delegate'); S4=$(find_line "$NT" 1 "$LN" '^### 4\. After the run'); SR=$(find_line "$NT" 1 "$LN" '^## Report')
assert_present "step 2: an in-progress child with a \`running\` marker is never a candidate" "$NT" "$S2" "$S3" '`running` marker.*never a'
assert_present "step 2: resume first reads the marker (\`stopped\` or none)" "$NT" "$S2" "$S3" 'Resume first.*marker'
assert_present "step 4: \`claimed-elsewhere\` is neither a stop nor a resolution" "$NT" "$S4" "$SR" 'claimed-elsewhere.*neither a stop nor a resolution'
assert_present "step 4: on \`claimed-elsewhere\` DONE is not incremented and the next candidate is picked from the same NEXT" "$NT" "$S4" "$SR" 'claimed-elsewhere.*DONE.*same `NEXT`'
```

- [ ] **Step 2: Edit step 2** — replace the fifth validity bullet's tail "That status with no worktree means someone else has it: skip it, and say so in the report." with: `That status with no worktree means someone else has it: skip it, and say so in the report. With our worktree, read the run marker \`$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<n>.json\`: a \`running\` marker with a heartbeat younger than 2 hours means a live session holds it and it is never a candidate here; \`stopped\`, an older heartbeat, or no marker keeps it a resume candidate.` In **Resume first**, change "that **does** have our worktree" to "that **does** have our worktree and whose marker allows a resume (`stopped`, a heartbeat older than 2 hours, or none — never `running` with a fresh heartbeat)" — keep `Resume first` and `marker` on one line.

- [ ] **Step 3: Edit step 4** — after `DONE += 1.` insert a paragraph: `` **`claimed-elsewhere` first.** A delegated run whose last line is `OUTCOME: claimed-elsewhere` is neither a stop nor a resolution: another session claimed the ticket between this loop's read and the worktree add. Do not increment `DONE`, do not re-read the brief (it did not change), record the decision for the report, and pick the next valid candidate from the same `NEXT` — step 2's rules, skipping the lost key. `` Make `DONE += 1` apply only to merged runs (reword: `DONE += 1` on a merged run.). Keep the two asserted phrases each on one line.

- [ ] **Step 4: Run, mutation-prove, commit** — `./scripts/verify-parallel.sh ./scripts/verify-epic-doc.sh ./scripts/verify-assertions.sh`, full suite; commit `feat(next-task): skip a lost claim; marker-aware resume`.

---

### Task 4: `review-and-merge` — rebase at the gate, manifest-version conflict (both copies)

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md` (§5 Merge, after gate 4 "Completeness gate", before gate 5 "Caller's pre-merge check"), then `cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/`
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md` (same place: after gate 4, before gate 5 "Config pre-merge checks")
- Modify: `scripts/verify-parallel.sh` (append)

**Interfaces:**
- Consumes: gate numbering as it exists (quick-dev 1–5, notion-dev 1–6); the merge code block with `gh pr merge`.
- Produces: an unnumbered `**Rebase at the gate.**` paragraph between gate 4 and the next gate, in both files.

- [ ] **Step 1: Failing anchors** (append):

```bash
echo "== review-and-merge: rebase at the gate (both copies) =="
for f in plugins/quick-dev/skills/review-and-merge/SKILL.md plugins/notion-dev/skills/review-and-merge/SKILL.md; do
  n=$(total_lines "$f"); M5=$(find_line "$f" 1 "$n" '^## 5\. Merge'); SR=$(find_line "$f" "$M5" "$n" '^## Safety rules')
  assert_present "$f: reads \`mergeStateStatus\` at the gate" "$f" "$M5" "$SR" 'gh pr view <pr> --json mergeStateStatus'
  assert_present "$f: \`BEHIND\` or \`DIRTY\` → \`git rebase origin/<base>\` in the worktree" "$f" "$M5" "$SR" '`BEHIND`.*`DIRTY`.*git rebase origin/<base>'
  assert_present "$f: re-run verify, then \`git push --force-with-lease\`" "$f" "$M5" "$SR" 'verify.*git push --force-with-lease'
  assert_present "$f: a clean rebase triggers no new review round" "$f" "$M5" "$SR" 'clean rebase.*no new review round'
  assert_present "$f: \`.claude-plugin/plugin.json\` version conflict: take the base's value and re-apply the bump class" "$f" "$M5" "$SR" '\.claude-plugin/plugin\.json.*take the base.s value.*bump class'
  assert_present "$f: the bump class is derived from merge-base vs head" "$f" "$M5" "$SR" 'bump class.*merge-base'
  assert_present "$f: any other conflict → \`git rebase --abort\` and the unmergeable stop" "$f" "$M5" "$SR" 'git rebase --abort.*unmergeable'
  assert_present "$f: rebase once, at the gate, never per round" "$f" "$M5" "$SR" 'once, at the gate, never per'
  assert_order "$f: completeness gate, rebase, pre-merge check, merge command" "$f" "$M5" "$SR" \
    completeness '^4\. \*\*Completeness gate\*\*' rebase '^\*\*Rebase at the gate\.\*\*' premerge "Caller's pre-merge check" merge '^gh pr merge <pr> '
done
```

(For notion-dev the `premerge` anchor still matches gate 6's line; the order holds because gate 5 config checks sits between rebase and it — that is intended: config checks run on the rebased head.)

- [ ] **Step 2: Edit quick-dev's copy** — insert after gate 4's last paragraph and before `5. **Caller's pre-merge check**`:

```
**Rebase at the gate.** Read `gh pr view <pr> --json mergeStateStatus`. `BEHIND` or `DIRTY` → in the worktree: `git fetch origin <base>` then `git rebase origin/<base>`; re-run the project's verify on the rebased head; `git push --force-with-lease`; re-read `mergeStateStatus` (it must now be `CLEAN`, `UNSTABLE` only if an optional check is pending, or `BLOCKED` only by a gate below — anything else stops). A clean rebase changes no diff, so it triggers no new review round; the final report states that the rebase happened and the new head sha. This runs **once, at the gate, never per round** — a base that moves during review rounds is caught here, not chased.

One conflict class resolves itself: when the rebase stops with the **only** conflicting hunk being `version` in `.claude-plugin/plugin.json`, take the base's value and re-apply this PR's bump class on top, `git add .claude-plugin/plugin.json`, `git rebase --continue`, and re-check that the head's version is strictly greater than the base's (`develop`'s version rule). **Superseded:** the class is **recorded before the rebase, not derived after it** — `review-and-merge/SKILL.md` compares the manifest at `git merge-base origin/<base> HEAD` with the head's and stores the first differing component as `BUMP_CLASS` *before* `git rebase` runs, then re-applies it once the rebase has landed. Deriving it afterwards reads a merge-base that the rebase has already moved. Spec §8 was amended to match; this line was not. Two minor PRs against 0.24.0 land as 0.25.0 and 0.26.0. Any other conflict → `git rebase --abort` and the existing unmergeable stop, worktree and PR left for a person; no automatic resolution of code. A repo without a manifest gets the rebase and nothing else.
```

Then sync the mirror: `cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/` and run `./scripts/verify-mirror.sh`.

- [ ] **Step 3: Edit notion-dev's copy** — the same two paragraphs after gate 4 and before `5. **Config pre-merge checks**`, with two wording changes for the fork: "`develop`'s version rule" → "`/notion-dev:ticket` Phase 6.1's rule", and add one clause to the first paragraph: "`git.mergeStrategy` is unchanged by the rebase." Keep every asserted phrase on one line in both files.

- [ ] **Step 4: Run, mutation-prove, commit** — `./scripts/verify-parallel.sh ./scripts/verify-mirror.sh ./scripts/verify-session-convergence.sh ./scripts/verify-convergence.sh ./scripts/verify-completeness.sh ./scripts/verify-assertions.sh`, full suite (the convergence harnesses anchor §5's structure; if one fails, keep its mechanism on one line, never weaken it). Commit `feat(review-and-merge): rebase once at the merge gate; manifest-version conflict resolves itself` (three files).

---

### Task 5: Per-invocation run ids (#44) and `new-info --pr` rebase (#46)

**Files:**
- Modify: `plugins/notion-dev/commands/new-info.md` (preconditions: token; apply section: rebase clause), `plugins/notion-dev/commands/knowledge.md` (preconditions: token; the three `<run id>` parentheticals), `plugins/notion-dev/commands/create-task.md` (the `create` paragraph's `<run id>`), `plugins/notion-dev/skills/epic-doc/SKILL.md` (write path step 1: one sentence naming the token rule)
- Modify: `scripts/verify-parallel.sh` (append), `scripts/verify-primary-lock.sh` (unchanged unless an anchor breaks — `<run id>` stays the literal in the commands)

- [ ] **Step 1: Failing anchors** (append):

```bash
echo "== per-invocation run ids (#44) =="
for f in plugins/notion-dev/commands/new-info.md plugins/notion-dev/commands/knowledge.md plugins/notion-dev/commands/create-task.md; do
  n=$(total_lines "$f")
  assert_present "$f: defines \`<run id>\` once as a per-invocation token with \`date -u +%Y%m%dT%H%M%SZ\`" "$f" 1 "$n" '<run id>.*\$\(date -u \+%Y%m%dT%H%M%SZ\)'
  assert_absent "$f: no bare per-command label remains as the run id" "$f" 1 "$n" '`<run id>` is `(new-info|knowledge|create-task)`'
done
echo "== new-info --pr rebase (#46) =="
NI=plugins/notion-dev/commands/new-info.md; LI=$(total_lines "$NI"); A0=$(find_line "$NI" 1 "$LI" '^### Apply'); A1=$(find_line "$NI" 1 "$LI" '^### Notion epic')
assert_present "apply: on a later epic under --pr, fetch and rebase the note branch when the epic branch moved" "$NI" "$A0" "$A1" 'git -C \$REPO_ROOT rebase origin/<epicBranch>'
assert_present "apply: a conflicting rebase aborts, releases, and stops with the remaining epics skipped" "$NI" "$A0" "$A1" 'git -C \$REPO_ROOT rebase --abort.*release.*skipped'
assert_order "apply: take, re-checkout, rebase" "$NI" "$A0" "$A1" take 'lock take --run <run id> --section apply' rebase 'git -C \$REPO_ROOT rebase origin/<epicBranch>'
```

- [ ] **Step 2: Token definitions** — in each of the three commands' preconditions (create-task: at the start of the `create` paragraph), add one line: `` `<run id>` = `<command>-$(date -u +%Y%m%dT%H%M%SZ)-<4 hex>` (e.g. `new-info-20260915T101500Z-a3f9`; the hex from `head -c2 /dev/urandom | od -An -tx1 | tr -d ' '`), generated once at the start of this command and carried through every `lock take` and `lock release` of this run — so a second concurrent invocation is a different holder, while this run's own re-takes stay re-entrant. `` Replace the existing parentheticals `` (`<run id>` is `new-info`; … `` / `` (`<run id>` is `knowledge`; … `` / `` `<run id>` is `create-task` `` with `` (`<run id>` from the preconditions; … `` so no bare label remains. In `epic-doc/SKILL.md` write-path step 1, add after the `LOCK_HELD` sentence: `Run ids: a ticket run uses \`<KEY>-<id>\`, finalize \`finalize <pr>\`, next-task \`next-task <KEY>-<n>\`; every other command generates a per-invocation token at its start (its preconditions say how).`

- [ ] **Step 3: `--pr` rebase** — in new-info's apply section, after the sentence that re-checks-out `<noteBranch>` on a later epic (PR 1's `0f91348` wording, "on a later epic … already on"), add: `` Then, under `--pr` on a later epic: `git -C $REPO_ROOT fetch origin <epicBranch>`; when `git -C $REPO_ROOT merge-base --is-ancestor origin/<epicBranch> HEAD` fails — another writer advanced the epic branch since the note branch was cut — `git -C $REPO_ROOT rebase origin/<epicBranch>`: the note commits are local and unpushed, so nothing published is rewritten and no merge commit is manufactured. A conflicting rebase → `git -C $REPO_ROOT rebase --abort`, release the lock, and stop: this epic and every later one are reported `skipped — note branch could not be rebased onto <epicBranch>: <git's message>`, and the note branch is left for a person. `` Keep the two asserted command literals each on one line.

- [ ] **Step 4: Run, mutation-prove, commit** — `./scripts/verify-parallel.sh ./scripts/verify-primary-lock.sh ./scripts/verify-new-info.sh ./scripts/verify-epic-doc.sh ./scripts/verify-assertions.sh`, full suite; commit `feat(notion-dev): per-invocation lock run ids (#44); new-info --pr rebases the note branch (#46)`.

---

### Task 6: README, versions, mutation proof, full suite

**Files:**
- Modify: `plugins/notion-dev/README.md` (`## Epics`: a "Running two sessions" paragraph), `plugins/notion-dev/.claude-plugin/plugin.json` (`0.26.0`), `plugins/quick-dev/.claude-plugin/plugin.json` (`0.15.0`), `plugins/quick-dev/README.md` (one sentence under its review-and-merge section: rebase at the gate)

- [ ] **Step 1: README** — under `## Epics` after the PR 1 paragraphs:

```
**Running two sessions on one epic.** Open a second terminal in the same checkout and run
`/notion-dev:next-task <epic> --depth N` in each. Each session claims its ticket by creating
the worktree, records a run marker under `.claude/notion-dev/runs/`, and moves the ticket to the
brief's `In progress:` line; the other session's next read excludes it. A ticket already
`In Progress` with no worktree here is reported as held elsewhere; a worktree whose marker says
`running` with a heartbeat under two hours is held by a live session; `stopped` or stale markers
resume. Two sessions merging into the same base rebase once at the merge gate, and a
manifest-version conflict resolves itself (two minor bumps land as consecutive minors). Same
machine only.
```

In quick-dev's README, one sentence where review-and-merge is described: "Before merging, a PR that fell behind its base is rebased once at the gate; a `.claude-plugin/plugin.json` version conflict is resolved by re-applying the PR's bump class on the base's version."

- [ ] **Step 2: Versions** — notion-dev `0.25.0 → 0.26.0`; quick-dev `0.14.2 → 0.15.0`. Baselines in `assert_version_above` calls stay.

- [ ] **Step 3: Full suite; commit** — `docs: README — running two sessions; notion-dev 0.26.0, quick-dev 0.15.0`.

- [ ] **Step 4: Mutation proof** — scratchpad script over every assertion added on this branch (`git diff main..HEAD -- scripts/verify-*.sh | grep '^+' | grep -c 'assert_'`) plus the two `knowledge.py` behaviour mutations (drop the title comparison; drop the order comparison). 0 MISS; a MISS is a harness gap fixed and committed.

- [ ] **Step 5: Report** — counts per harness, HIT/MISS totals, commit list. The two-session client verification (spec §11 step 2) is the user's step after the merge, stated in the PR body.
