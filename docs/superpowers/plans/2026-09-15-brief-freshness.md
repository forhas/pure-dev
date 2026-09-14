# Brief Freshness (PR 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the epic brief true after every change that affects the epic — ticket start, stop, create, resolution, new info, and Notion drift — with one deterministic derivation of `## Next`, one write path that converges under concurrent writers, and one lock on the primary checkout.

**Architecture:** `scripts/knowledge.py` gains two subcommands: `next` renders the `## Next` region, the header, and the stop bullet from a JSON of live state and reports drift; `lock` implements the primary-checkout lock as a `mkdir` directory. `skills/epic-doc/SKILL.md` gains a fourth operation, `refresh`, and a `## The write path` section that every commit from the primary checkout follows (fetch, ff-pull, derive, commit by pathspec, push, converge on rejection, three attempts). The call sites (`ticket`, `finalize`, `next-task`, `new-info`, `create-task`, the `knowledge` command and skill) take the lock around their primary-checkout sections and invoke `refresh` at the moments spec §6 names.

**Tech Stack:** Markdown instruction files; bash harnesses on `scripts/lib/assert.sh`; Python 3.8+ standard library; git.

**Spec:** `docs/superpowers/specs/2026-09-15-brief-freshness-and-parallel-tickets-design.md` — §1–§6, §9 (first three rows), §10 (PR 1), §11 step 1. PR 2 (§7, §8) is **not** in this plan.

## Global Constraints

- **CLAUDE.md harness rules** bind every assertion: assert mechanisms not prose; `assert_present` matches exactly one line per region; a backticked literal, ALL-CAPS key, `--flag` or `<placeholder>` in a label must appear in the regex (A2); declared duplicates use `assert_count`; `assert_count` counts **lines**; every new assertion is mutation-proven (break the file, see `FAIL`, restore) and the work is committed **before** mutating.
- **Only `scripts/lib/assert.sh` helpers** in harnesses. `verify-knowledge-py.sh` may run `python3` and `git` and compare exit codes; comparisons of captured output use `assert_has` / `assert_lacks` / `assert_identical`.
- **`knowledge.py` stays stdlib-only and never parses YAML.** `next` and `lock` add no imports beyond `json`, `os`, `re`, `sys`, `time`, `shutil`, `datetime`, `argparse`.
- **Version bump exactly once**: `plugins/notion-dev/.claude-plugin/plugin.json` `0.24.0 → 0.25.0`, in Task 7.
- **`notion-dev` has no `.claude/skills` mirror.** Nothing under `.claude/skills/` changes.
- **The brief stays minimal.** The only additions to the brief format are the `In progress:` line, the stop bullet, and the new `Updated: … after` values. No task adds anything else to the template.
- **`read` writes nothing** and takes no lock; it may run `knowledge.py next` on a temp copy for drift.
- **The lock guards exactly the sections in spec §4's table**, no more. `git worktree add`, read-only `git status` / `git rev-parse`, and all work inside a worktree never take it.
- **Commit trailer** on every commit: `Claude-Session: https://claude.ai/code/session_01EPBePxetmA6tMtXPRtRxHd`.
- **Run the full suite** (`for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done`) before every commit that touches a harness or a guarded file.
- **Pinned literals.** Tasks 4–7 write these lines verbatim (one line, never wrapped) and the harnesses assert them. A task that needs to deviate stops and reports.

| id | file | literal (one line) |
|---|---|---|
| L1 | epic-doc/SKILL.md | `## \`refresh(<epic-id>, <reason>)\` — the derived writer` |
| L2 | epic-doc/SKILL.md | `## The write path — every commit from the primary checkout` |
| L3 | epic-doc/SKILL.md | `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" next --brief <tmp brief> --state <tmp state.json> --today <YYYY-MM-DD>` |
| L4 | epic-doc/SKILL.md | `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section <name> --wait <seconds>` |
| L5 | epic-doc/SKILL.md | `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>` |
| L6 | epic-doc/SKILL.md | `git rev-list origin/<epicBranch>..HEAD` |
| L7 | epic-doc/SKILL.md | `git reset --hard origin/<epicBranch>` |
| L8 | epic-doc/SKILL.md | `EPIC-DOC: created \| updated \| closed \| refreshed \| unchanged \| none \| failed` |
| L9 | epic-doc/SKILL.md (read) | `DRIFT: true` |
| L10 | epic-doc/SKILL.md (template) | `In progress: [STO-72] Backfill v2 — since 2026-09-15` |
| L11 | epic-doc/SKILL.md | `Three attempts.` |
| L12 | epic-doc/SKILL.md | `LOCK_HELD` (appears in the write path step 1 and step 5) |
| L13 | ticket.md Phase 2 | `operation \`refresh(<epic-id>, start <key>)\`` |
| L14 | ticket.md stop path | `operation \`refresh(<epic-id>, stop <key> <phase> <cause> <worktree-path>)\`` |
| L15 | next-task.md | `operation \`refresh(<epic-id>, drift)\`` |
| L16 | create-task.md | `operation \`refresh(<epic-id>, create <key>)\`` |
| L17 | every locked section | `knowledge.py" lock take --run <run id> --section <section> --wait <600\|3600>` with the section word from spec §4's table |
| L18 | every locked section | `knowledge.py" lock release --run <run id>` |
| L19 | signatures.md | rows `lock-stale:primary` and `lock-timeout:primary` |
| L20 | commit subjects (epic-doc) | `docs(epic): <KEY>-<n> start <key>`, `docs(epic): <KEY>-<n> stop <key>`, `docs(epic): <KEY>-<n> create <key>`, `docs(epic): <KEY>-<n> refresh` |

---

## File structure

| path | responsibility |
|---|---|
| `plugins/notion-dev/scripts/knowledge.py` | modify — add `next` (render `## Next`, header, stop bullet; drift) and `lock` (take/release/status) |
| `scripts/fixtures/knowledge/next/` | new — the base brief, state JSONs, expected outputs for `next` |
| `scripts/verify-knowledge-py.sh` | modify — `next` cases, `lock` cases, the two-clone convergence case |
| `plugins/notion-dev/skills/epic-doc/SKILL.md` | modify — `refresh`, the write path, drift in `read`, `record`/`note` reworded to the shared derivation, output block |
| `scripts/verify-epic-doc.sh` | modify — anchors for the above |
| `plugins/notion-dev/commands/ticket.md` | modify — Phase 2 `refresh start`, stop path `refresh stop`, `record` lock section |
| `plugins/notion-dev/commands/finalize.md` | modify — `record` lock section |
| `plugins/notion-dev/commands/next-task.md` | modify — drift refresh + splice, bootstrap under the lock |
| `plugins/notion-dev/commands/new-info.md` | modify — `apply` lock section, `LOCK_HELD` to `note --apply` and `capture --fact` |
| `plugins/notion-dev/commands/create-task.md` | modify — `refresh create` |
| `plugins/notion-dev/commands/knowledge.md` | modify — `capture` / `migrate` lock section |
| `plugins/notion-dev/skills/knowledge/SKILL.md` | modify — `capture` commits through the write path |
| `plugins/notion-dev/skills/issue-log/references/signatures.md` | modify — two rows, `partial:epic-doc` row widened |
| `scripts/verify-primary-lock.sh` | new — take/release pairing per section, wait values, `read` takes nothing |
| `scripts/verify-knowledge.sh`, `scripts/verify-new-info.sh` | modify — anchors that moved |
| `plugins/notion-dev/README.md` | modify — `In progress:` line, the lock directory |
| `plugins/notion-dev/.claude-plugin/plugin.json` | modify — `0.25.0` |

---

### Task 1: `knowledge.py next` — the deterministic `## Next` renderer

**Files:**
- Modify: `plugins/notion-dev/scripts/knowledge.py` (add a `next` section before `# CLI`, register the subparser in `main()`)
- Create: `scripts/fixtures/knowledge/next/brief.md`, `brief-drift.md`, `state-basic.json`, `state-start.json`, `state-stop.json`, `state-create.json`, `state-complete.json`, `state-client-shaped.json`, `expected-start.md`, `expected-stop.md`, `expected-restart.md`, `expected-create.md`, `expected-drift.md`, `expected-complete.md`
- Test: `scripts/verify-knowledge-py.sh` (append a `== next ==` block)

**Interfaces:**
- Consumes: `die`, `_git_toplevel` (existing helpers in `knowledge.py`).
- Produces: `python3 knowledge.py next --brief <path> --state <json> [--reason <word> [<key>]] [--today YYYY-MM-DD]` → stdout: the whole brief with the `## Next` region, header and stop bullet rewritten, LF endings; stderr: one `drift: …` line per finding then `DRIFT: <n>`; exit 0 identical, 1 differs, 2 malformed. Task 4's skill text cites this command as L3.

- [ ] **Step 1: Write the base fixture brief**

`scripts/fixtures/knowledge/next/brief.md` (LF endings, trailing newline):

```
---
type: Epic
title: "[STO-60] Wallet Indexing"
description: "Index every wallet once."
status: stable
epic: STO-60
generated: { by: notion-dev:epic-doc, at: 2026-09-13T00:00:00Z }
sources:
  - { id: epic, resource: "https://notion.so/STO-60", title: "[STO-60] Wallet Indexing" }
---
# [STO-60] Wallet Indexing
Epic: https://notion.so/STO-60 · Status: open · Updated: 2026-09-14 after [STO-70]

## Why
Wallets are indexed twice today.

## Goal
Index every wallet once.

## Where we stand
STO-70 landed the backfill.

## Open threads
- **Waiting on customer logs** for v1.4.2 — blocks STO-22. Unblocked by: logs attached to STO-22.

## Decisions & constraints
- Cache TTL is 60s.

## Next
1. **[STO-71] Cache metrics** — unblocked; STO-70 landed.
2. [STO-73] Alerting — after STO-71
In progress: [STO-72] Backfill v2 — since 2026-09-14
Blocked: STO-22 (see Open threads).
```

`brief-drift.md`: identical except the `## Next` region reads:

```
## Next
1. **[STO-70] Backfill** — first in phase order.
2. [STO-71] Cache metrics — after STO-70
Blocked: STO-22 (see Open threads).
```

- [ ] **Step 2: Write the state fixtures**

`state-basic.json`:

```json
{
  "epic": { "key": "STO-60", "status_class": "open" },
  "children": [
    { "key": "STO-22", "id": 22, "title": "Customer replay", "status_class": "open", "blocked_by": [], "phase": 1, "step": 1 },
    { "key": "STO-70", "id": 70, "title": "Backfill", "status_class": "resolved", "blocked_by": [], "phase": 2, "step": 1 },
    { "key": "STO-71", "id": 71, "title": "Cache metrics", "status_class": "open", "blocked_by": ["STO-70"], "phase": 2, "step": 2 },
    { "key": "STO-72", "id": 72, "title": "Backfill v2", "status_class": "in_progress", "blocked_by": [], "phase": 2, "step": 3 },
    { "key": "STO-73", "id": 73, "title": "Alerting", "status_class": "open", "blocked_by": ["STO-71"], "phase": 3, "step": 1 }
  ],
  "thread_blocked": ["STO-22"]
}
```

`state-start.json`: `state-basic.json` with STO-71's `status_class` set to `"in_progress"`.

`state-stop.json`: `state-basic.json` plus a top-level key:

```json
  "stop": { "key": "STO-72", "phase": "Phase 7", "cause": "review loop stalled", "worktree": "../demo-worktrees/demo-STO-72" }
```

`state-create.json`: `state-basic.json` plus one child appended:

```json
    { "key": "STO-74", "id": 74, "title": "Dashboards", "status_class": "open", "blocked_by": [], "phase": 3, "step": 2 }
```

`state-complete.json`: `state-basic.json` with `epic.status_class` `"resolved"` and every child's `status_class` `"resolved"`.

`state-client-shaped.json`: 12 children shaped like a real client epic — ids 101–112, phases 1–4 with two or three steps each, three resolved (101, 102, 103), one in_progress (105), `blocked_by` chains 104→103, 106→105, 107→106, 108→104, 109–112 with `blocked_by: []`, `thread_blocked: ["STO-110"]`, phase `null` and step `null` on STO-112. Titles are any short noun phrases. This fixture is only run for exit code and the partition invariant (step 6), never byte-compared.

- [ ] **Step 3: Write the expected outputs**

Each `expected-*.md` is `brief.md` byte-for-byte except the header line, the `## Next` region, and (for stop/restart) the `## Open threads` region, replaced as follows. All are produced with `--today 2026-09-15`.

`expected-start.md` (`state-start.json`, `--reason start STO-71`):

```
Epic: https://notion.so/STO-60 · Status: open · Updated: 2026-09-15 after start [STO-71]
```
```
## Next
1. [STO-73] Alerting — after STO-71
In progress: [STO-71] Cache metrics — since 2026-09-15, [STO-72] Backfill v2 — since 2026-09-14
Blocked: STO-22 (see Open threads).
```

`expected-stop.md` (`state-stop.json`, `--reason stop STO-72`):

```
Epic: https://notion.so/STO-60 · Status: open · Updated: 2026-09-15 after stop [STO-72]
```
```
## Open threads
- **Waiting on customer logs** for v1.4.2 — blocks STO-22. Unblocked by: logs attached to STO-22.
- **[STO-72] stopped at Phase 7** — review loop stalled; worktree at ../demo-worktrees/demo-STO-72. Unblocked by: /notion-dev:ticket STO-72 (resumes).
```
```
## Next
1. **[STO-71] Cache metrics** — unblocked; STO-70 landed.
2. [STO-73] Alerting — after STO-71
Blocked: STO-22, STO-72 (see Open threads).
```

`expected-restart.md` (input `expected-stop.md`, `state-basic.json`, `--reason start STO-72`): the `## Open threads` region of `brief.md` (bullet gone), header `Updated: 2026-09-15 after start [STO-72]`, and:

```
## Next
1. **[STO-71] Cache metrics** — unblocked; STO-70 landed.
2. [STO-73] Alerting — after STO-71
In progress: [STO-72] Backfill v2 — since 2026-09-15
Blocked: STO-22 (see Open threads).
```

`expected-create.md` (`state-create.json`, `--reason create STO-74`): header `after create [STO-74]` and:

```
## Next
1. **[STO-71] Cache metrics** — unblocked; STO-70 landed.
2. [STO-73] Alerting — after STO-71
3. [STO-74] Dashboards — ready
In progress: [STO-72] Backfill v2 — since 2026-09-14
Blocked: STO-22 (see Open threads).
```

`expected-drift.md` (input `brief-drift.md`, `state-basic.json`, no `--reason`): header `Updated: 2026-09-15 after refresh` and (note: no trailing period — the reason is templated, not preserved):

```
## Next
1. **[STO-71] Cache metrics** — unblocked; STO-70 landed
2. [STO-73] Alerting — after STO-71
In progress: [STO-72] Backfill v2 — since 2026-09-15
Blocked: STO-22 (see Open threads).
```

`expected-complete.md` (`state-complete.json`, no `--reason`): header `Status: closed · Updated: 2026-09-15 after refresh` and:

```
## Next
epic complete
```

- [ ] **Step 4: Write the failing harness block**

Append to `scripts/verify-knowledge-py.sh` before its final exit-code summary (find the existing `if [ "$fails" -gt 0 ]` tail and insert above it):

```bash
echo "== next: renders ## Next, the header and the stop bullet deterministically =="
NX=$FX/next
TODAY=2026-09-15
nx() { # name, expected-exit, brief, state, [reason args...]
  local name=$1 want=$2 brief=$3 state=$4; shift 4
  python3 "$PY" next --brief "$brief" --state "$state" --today "$TODAY" "$@" \
    > "$OUT/next-$name.md" 2> "$OUT/next-$name.err"; local got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL: next-$name exited $got, wanted $want"; cat "$OUT/next-$name.err"; fails=$((fails+1))
  else echo "ok: next-$name exit $got"; fi
}
nx basic    0 "$NX/brief.md"          "$NX/state-basic.json"
assert_identical "next: a true brief re-renders byte-identical" "$OUT/next-basic.md" "$NX/brief.md"
assert_has "next: a true brief reports DRIFT: 0" "$OUT/next-basic.err" 'DRIFT: 0'
nx start    1 "$NX/brief.md"          "$NX/state-start.json"    --reason start STO-71
assert_identical "next: start moves the key to In progress with today's since and keeps the other since" \
  "$OUT/next-start.md" "$NX/expected-start.md"
nx stop     1 "$NX/brief.md"          "$NX/state-stop.json"     --reason stop STO-72
assert_identical "next: stop adds the thread bullet and moves the key to Blocked" \
  "$OUT/next-stop.md" "$NX/expected-stop.md"
nx restart  1 "$NX/expected-stop.md"  "$NX/state-basic.json"    --reason start STO-72
assert_identical "next: start removes the stop bullet and restores In progress" \
  "$OUT/next-restart.md" "$NX/expected-restart.md"
nx create   1 "$NX/brief.md"          "$NX/state-create.json"   --reason create STO-74
assert_identical "next: create appends the new child as ready" "$OUT/next-create.md" "$NX/expected-create.md"
assert_has "next: create reports the missing key as drift" "$OUT/next-create.err" 'drift: STO-74 missing from ## Next'
nx drift    1 "$NX/brief-drift.md"    "$NX/state-basic.json"
assert_identical "next: drift repairs a resolved item, a missing child and the In progress line" \
  "$OUT/next-drift.md" "$NX/expected-drift.md"
assert_has "next: drift names the resolved item"   "$OUT/next-drift.err" 'drift: STO-70 listed, live status resolved'
assert_has "next: drift names the missing child"   "$OUT/next-drift.err" 'drift: STO-73 missing from ## Next'
assert_has "next: drift names the missing In progress line" "$OUT/next-drift.err" 'drift: In progress line missing'
assert_has "next: drift counts four findings"      "$OUT/next-drift.err" 'DRIFT: 4'
nx complete 1 "$NX/brief.md"          "$NX/state-complete.json"
assert_identical "next: a resolved epic renders epic complete and Status: closed" \
  "$OUT/next-complete.md" "$NX/expected-complete.md"
nx rerender 0 "$OUT/next-start.md"    "$NX/state-start.json"
assert_identical "next: re-rendering its own output is byte-identical" "$OUT/next-rerender.md" "$OUT/next-start.md"
nx client   1 "$NX/brief.md"          "$NX/state-client-shaped.json"
# partition invariant: every unresolved key appears in exactly one of the three lists
if python3 - "$NX/state-client-shaped.json" "$OUT/next-client.md" <<'PYEOF'
import json, re, sys
state = json.load(open(sys.argv[1])); text = open(sys.argv[2], encoding="utf-8").read()
region = text.split("\n## Next\n", 1)[1].split("\n## ", 1)[0].splitlines()
num = [m.group(1) for ln in region for m in [re.match(r"^\d+\. (?:\*\*)?\[([A-Z0-9-]+)\]", ln)] if m]
ip = re.findall(r"\[([A-Z0-9-]+)\] [^,]*? — since \d{4}-\d{2}-\d{2}", next((l for l in region if l.startswith("In progress: ")), ""))
bl = re.findall(r"[A-Z][A-Z0-9]+-\d+", next((l for l in region if l.startswith("Blocked: ")), ""))
want = sorted(c["key"] for c in state["children"] if c["status_class"] != "resolved")
got = sorted(num + ip + bl)
sys.exit(0 if got == want else print("partition:", got, "wanted", want))
PYEOF
then ok "next: client-shaped partitions every unresolved child exactly once"; else bad "next: client-shaped partition is wrong"; fi
printf 'no next heading\n' > "$OUT/next-bad.md"
nx malformed 2 "$OUT/next-bad.md" "$NX/state-basic.json"
```

- [ ] **Step 5: Run the harness to see it fail**

Run: `./scripts/verify-knowledge-py.sh 2>&1 | grep -c 'FAIL'`
Expected: non-zero — every `next-*` case fails with `invalid choice: 'next'`.

- [ ] **Step 6: Implement `next`**

Insert before the `# CLI` banner in `plugins/notion-dev/scripts/knowledge.py`:

```python
# ---------------------------------------------------------------------------
# next — render `## Next`, the header line and the stop bullet (spec §5)
# ---------------------------------------------------------------------------

KEY_RE = re.compile(r"[A-Z][A-Z0-9]{1,9}-\d+")
NEXT_ITEM_RE = re.compile(
    r"^(\d+)\. (\*\*)?\[([A-Z][A-Z0-9]{1,9}-\d+)\] (.*?)(\*\*)?(?: — (.*))?$")
IN_PROGRESS_RE = re.compile(r"^In progress: (.*)$")
IN_PROGRESS_ITEM_RE = re.compile(r"^\[([A-Z][A-Z0-9]{1,9}-\d+)\] (.*?) — since (\d{4}-\d{2}-\d{2})$")
BLOCKED_RE = re.compile(r"^Blocked: (.*)$")
HEADER_RE = re.compile(r"^(Epic: .*? · Status: )(open|closed)( · Updated: )(\d{4}-\d{2}-\d{2}) after (.*)$")
STOP_BULLET_RE = re.compile(r"^- \*\*\[([A-Z][A-Z0-9]{1,9}-\d+)\] stopped at ")
STATUS_CLASSES = ("resolved", "in_progress", "open")


def _section(lines, heading):
    """(start, end) of the region headed by `heading`, end exclusive; (None, None) if absent."""
    start = None
    for i, ln in enumerate(lines):
        if ln.rstrip() == heading:
            start = i
            break
    if start is None:
        return None, None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return start, end


def _parse_next(body):
    items, in_progress, blocked, complete = [], {}, [], False
    for ln in body:
        s = ln.strip()
        if not s:
            continue
        if s == "epic complete":
            complete = True
            continue
        m = NEXT_ITEM_RE.match(s)
        if m:
            items.append({"key": m.group(3), "title": m.group(4),
                          "reason": m.group(6) or "", "bold": bool(m.group(2))})
            continue
        m = IN_PROGRESS_RE.match(s)
        if m:
            for part in m.group(1).split(", "):
                pm = IN_PROGRESS_ITEM_RE.match(part.strip())
                if pm:
                    in_progress[pm.group(1)] = pm.group(3)
            continue
        m = BLOCKED_RE.match(s)
        if m:
            blocked = KEY_RE.findall(m.group(1))
    return items, in_progress, blocked, complete


def _order_key(c):
    return (c.get("phase") is None, c.get("phase") or 0,
            c.get("step") is None, c.get("step") or 0, c["id"])


def _validate_state(state):
    try:
        epic = state["epic"]
        children = state["children"]
        assert epic["status_class"] in STATUS_CLASSES
        for c in children:
            assert isinstance(c["key"], str) and KEY_RE.fullmatch(c["key"])
            assert isinstance(c["id"], int) and isinstance(c["title"], str)
            assert c["status_class"] in STATUS_CLASSES
            assert isinstance(c.get("blocked_by", []), list)
            for p in ("phase", "step"):
                assert c.get(p) is None or isinstance(c[p], int)
        assert isinstance(state.get("thread_blocked", []), list)
    except (KeyError, AssertionError, TypeError):
        die("next: malformed state JSON (spec §5 shape)")


def derive_next(state, stopped_keys):
    """Partition the unresolved children: (in_progress, blocked, numbered, first)."""
    by_key = {c["key"]: c for c in state["children"]}

    def resolved(k):
        c = by_key.get(k)
        return c is None or c["status_class"] == "resolved"

    thread_blocked = set(state.get("thread_blocked", []))
    inprog, blocked, numbered = [], [], []
    for c in sorted((c for c in state["children"] if c["status_class"] != "resolved"), key=_order_key):
        if c["key"] in stopped_keys:
            blocked.append(c)
        elif c["status_class"] == "in_progress":
            inprog.append(c)
        elif c["key"] in thread_blocked:
            blocked.append(c)
        else:
            numbered.append(c)
    first = next((c for c in numbered if all(resolved(k) for k in c.get("blocked_by", []))), None)
    if first is not None:
        numbered.remove(first)
        numbered.insert(0, first)
    return inprog, blocked, numbered, first, resolved


def _item1_reason(first, prev_items, resolved):
    prev1 = prev_items[0] if prev_items else None
    if prev1 and prev1["key"] == first["key"] and prev1["reason"]:
        return prev1["reason"]
    for it in prev_items:
        if it["key"] == first["key"] and it["reason"].startswith("after "):
            landed = [k for k in KEY_RE.findall(it["reason"]) if resolved(k)]
            if landed:
                return "unblocked; " + ", ".join(landed) + " landed"
    return "first in phase order"


def render_next(state, inprog, blocked, numbered, first, resolved, prev_items, prev_in_progress, today):
    if state["epic"]["status_class"] == "resolved":
        return ["## Next", "epic complete"]
    out = ["## Next"]
    for i, c in enumerate(numbered, 1):
        if c is first:
            out.append("%d. **[%s] %s** — %s" % (i, c["key"], c["title"],
                                                 _item1_reason(first, prev_items, resolved)))
        else:
            waits = [k for k in c.get("blocked_by", []) if not resolved(k)]
            out.append("%d. [%s] %s — %s" % (i, c["key"], c["title"],
                                             ("after " + ", ".join(waits)) if waits else "ready"))
    if inprog:
        out.append("In progress: " + ", ".join(
            "[%s] %s — since %s" % (c["key"], c["title"], prev_in_progress.get(c["key"], today))
            for c in sorted(inprog, key=lambda c: c["id"])))
    if blocked:
        out.append("Blocked: " + ", ".join(c["key"] for c in sorted(blocked, key=lambda c: c["id"]))
                   + " (see Open threads).")
    return out


def drift_findings(state, prev_items, prev_in_progress, prev_blocked, header_status,
                   inprog, blocked, numbered):
    f = []
    live = {c["key"]: c["status_class"] for c in state["children"]}
    prev_num = {it["key"] for it in prev_items}
    prev_ip = set(prev_in_progress)
    prev_bl = set(prev_blocked)
    new_num = {c["key"] for c in numbered}
    new_ip = {c["key"] for c in inprog}
    new_bl = {c["key"] for c in blocked}
    for k in sorted(prev_num | prev_ip | prev_bl):
        if live.get(k, "resolved") == "resolved":
            f.append("drift: %s listed, live status resolved" % k)
    for k in sorted(new_num | new_ip | new_bl):
        if k not in prev_num and k not in prev_ip and k not in prev_bl:
            f.append("drift: %s missing from ## Next" % k)
        elif k in new_ip and k not in prev_ip:
            f.append("drift: %s listed as %s, live status in_progress"
                     % (k, "next" if k in prev_num else "blocked"))
        elif k in new_num and k in prev_ip:
            f.append("drift: %s listed as in progress, live status open" % k)
        elif k in new_bl and k not in prev_bl:
            f.append("drift: %s listed as %s, held by a thread"
                     % (k, "next" if k in prev_num else "in progress"))
    live_status = "closed" if state["epic"]["status_class"] == "resolved" else "open"
    if header_status != live_status:
        f.append("drift: header Status %s, live %s" % (header_status, live_status))
    if new_ip and not prev_ip:
        f.append("drift: In progress line missing")
    return f


def stop_bullet(stop):
    return ("- **[%s] stopped at %s** — %s; worktree at %s. Unblocked by: /notion-dev:ticket %s (resumes)."
            % (stop["key"], stop["phase"], stop["cause"], stop["worktree"], stop["key"]))


def _remove_stop_bullet(lines, ts, te, key):
    i = ts + 1
    while i < te:
        m = STOP_BULLET_RE.match(lines[i])
        if m and m.group(1) == key:
            j = i + 1
            while j < te and lines[j].startswith("  "):
                j += 1
            del lines[i:j]
            return lines, te - (j - i)
        i += 1
    return lines, te


def _append_bullet(lines, ts, te, bullet):
    k = te
    while k > ts + 1 and lines[k - 1].strip() == "":
        k -= 1
    lines.insert(k, bullet)
    return lines, te + 1


def cmd_next(a):
    try:
        with open(a.brief, encoding="utf-8", newline=None) as fh:
            text = fh.read()
    except OSError as e:
        die("next: cannot read brief: %s" % e)
    try:
        with open(a.state, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError) as e:
        die("next: cannot read state: %s" % e)
    _validate_state(state)
    today = a.today or datetime.date.today().isoformat()
    reason_word, reason_key = (a.reason + [None])[:2] if a.reason else (None, None)
    if reason_word not in (None, "start", "stop", "create", "resolve", "new-info"):
        die("next: --reason must be start|stop|create|resolve|new-info [<key>]")
    if reason_word in ("start", "stop", "create", "resolve") and not (reason_key and KEY_RE.fullmatch(reason_key)):
        die("next: --reason %s needs a <KEY>-<n>" % reason_word)

    lines = text.split("\n")
    trailing_newline = text.endswith("\n")
    if trailing_newline:
        lines = lines[:-1]
    original = list(lines)

    header_idx = next((i for i, ln in enumerate(lines) if HEADER_RE.match(ln)), None)
    if header_idx is None:
        die("next: no header line (Epic: … · Status: … · Updated: …)")
    ns, ne = _section(lines, "## Next")
    if ns is None:
        die("next: no `## Next` heading")
    ts, te = _section(lines, "## Open threads")
    if reason_word in ("start", "stop") and ts is None:
        die("next: no `## Open threads` heading, needed for --reason %s" % reason_word)

    if ts is not None:
        if reason_word == "start":
            lines, te = _remove_stop_bullet(lines, ts, te, reason_key)
        elif reason_word == "stop":
            stop = state.get("stop")
            if not stop or stop.get("key") != reason_key:
                die("next: --reason stop %s needs state.stop for that key" % reason_key)
            lines, te = _remove_stop_bullet(lines, ts, te, reason_key)
            lines, te = _append_bullet(lines, ts, te, stop_bullet(stop))
        stopped = {STOP_BULLET_RE.match(ln).group(1) for ln in lines[ts + 1:te] if STOP_BULLET_RE.match(ln)}
    else:
        stopped = set()

    header_idx = next(i for i, ln in enumerate(lines) if HEADER_RE.match(ln))
    ns, ne = _section(lines, "## Next")
    prev_items, prev_ip, prev_bl, _prev_complete = _parse_next(lines[ns + 1:ne])
    inprog, blocked, numbered, first, resolved = derive_next(state, stopped)
    region = render_next(state, inprog, blocked, numbered, first, resolved, prev_items, prev_ip, today)
    tail = []
    k = ne
    while k > ns + 1 and lines[k - 1].strip() == "":
        k -= 1
        tail.append("")
    lines[ns:ne] = region + tail

    hm = HEADER_RE.match(lines[header_idx])
    findings = drift_findings(state, prev_items, prev_ip, prev_bl, hm.group(2), inprog, blocked, numbered)
    changed = lines != original
    if changed:
        live_status = "closed" if state["epic"]["status_class"] == "resolved" else "open"
        what = {"start": "start [%s]", "stop": "stop [%s]", "create": "create [%s]",
                "resolve": "[%s]"}.get(reason_word)
        what = (what % reason_key) if what else ("new-info" if reason_word == "new-info" else "refresh")
        lines[header_idx] = "%s%s%s%s after %s" % (hm.group(1), live_status, hm.group(3), today, what)

    sys.stdout.write("\n".join(lines) + "\n")
    for f in findings:
        sys.stderr.write(f + "\n")
    sys.stderr.write("DRIFT: %d\n" % len(findings))
    sys.exit(1 if changed else 0)
```

Add `import datetime` alongside the existing imports if absent. Register in `main()` after `p_migrate`:

```python
    p_next = sub.add_parser(
        "next", help="render the brief's ## Next region, header and stop bullet from live state (spec §5)")
    p_next.add_argument("--brief", required=True, help="the brief to render against")
    p_next.add_argument("--state", required=True, help="live-state JSON (spec §5 shape)")
    p_next.add_argument("--reason", nargs="+", default=None,
                        help="start|stop|create|resolve <KEY>-<n>, or new-info; omitted = refresh")
    p_next.add_argument("--today", default=None, help="YYYY-MM-DD (default: today, UTC)")
    p_next.set_defaults(func=cmd_next)
```

The existing `die` exits 2, which is `next`'s malformed-input code.

- [ ] **Step 7: Run the harness to see it pass**

Run: `./scripts/verify-knowledge-py.sh`
Expected: every `next-*` line `ok`, every `assert_*` in the block `PASS`, the pre-existing cases untouched. Fix byte differences by correcting the expected fixture only when the spec agrees with the script's output; otherwise fix the script.

- [ ] **Step 8: Commit**

```bash
git add plugins/notion-dev/scripts/knowledge.py scripts/fixtures/knowledge/next scripts/verify-knowledge-py.sh
git commit -m "feat(knowledge.py): next — deterministic ## Next renderer with drift findings

Claude-Session: https://claude.ai/code/session_01EPBePxetmA6tMtXPRtRxHd"
```

---

### Task 2: `knowledge.py lock` — the primary-checkout lock

**Files:**
- Modify: `plugins/notion-dev/scripts/knowledge.py` (add a `lock` section, register the subparser)
- Test: `scripts/verify-knowledge-py.sh` (append a `== lock ==` block)

**Interfaces:**
- Produces: `knowledge.py lock take --run <id> --section <name> [--wait <seconds>] [--root <dir>]` (exit 0 taken or re-entrant, 1 timeout with `held by <run> (<section>) since <iso>` on stdout, prints `stale: run: <old run>` when it broke an abandoned lock); `lock release --run <id> [--root <dir>]` (exit 0 released, 1 not held by that run); `lock status [--root <dir>]` (prints `free` or `held by …`, exit 0). Default root: `<git toplevel>/.claude/notion-dev/locks`. Task 4 cites `take`/`release` as L4/L5.

- [ ] **Step 1: Write the failing harness block**

Append to `scripts/verify-knowledge-py.sh` after the `next` block:

```bash
echo "== lock: mkdir lock on the primary checkout =="
LK=$(mktemp -d)
lk() { # name, expected-exit, args...
  local name=$1 want=$2; shift 2
  python3 "$PY" lock "$@" --root "$LK" > "$OUT/lock-$name.txt" 2>&1; local got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL: lock-$name exited $got, wanted $want"; cat "$OUT/lock-$name.txt"; fails=$((fails+1))
  else echo "ok: lock-$name exit $got"; fi
}
lk status-free 0 status
assert_has "lock: status reports free"                    "$OUT/lock-status-free.txt" 'free'
lk take-a 0 take --run STO-70 --section record --wait 0
assert_has "lock: owner file names the run"               "$LK/primary/owner" 'run: STO-70'
assert_has "lock: owner file names the section"           "$LK/primary/owner" 'section: record'
lk take-b 1 take --run STO-71 --section start --wait 0
assert_has "lock: a second run is told the holder"        "$OUT/lock-take-b.txt" 'held by STO-70 (record) since'
lk take-a-again 0 take --run STO-70 --section record --wait 0
assert_has "lock: the holder re-enters"                   "$OUT/lock-take-a-again.txt" 'reentrant'
lk release-b 1 release --run STO-71
assert_has "lock: release by another run is refused"      "$OUT/lock-release-b.txt" 'held by STO-70'
lk release-a 0 release --run STO-70
lk status-free-2 0 status
assert_has "lock: released reports free"                  "$OUT/lock-status-free-2.txt" 'free'
lk release-none 1 release --run STO-70
assert_has "lock: release when free says not held"        "$OUT/lock-release-none.txt" 'not held'
mkdir -p "$LK/primary"
printf 'run: STO-9\nsection: record\nsince: 2000-01-01T00:00:00Z\n' > "$LK/primary/owner"
lk take-stale 0 take --run STO-71 --section start --wait 0
assert_has "lock: an abandoned owner is broken and named" "$OUT/lock-take-stale.txt" 'stale: run: STO-9'
assert_has "lock: after breaking, the new run holds it"   "$LK/primary/owner" 'run: STO-71'
lk release-71 0 release --run STO-71
rm -rf "$LK"
```

- [ ] **Step 2: Run the harness to see it fail**

Run: `./scripts/verify-knowledge-py.sh 2>&1 | grep -c 'lock-.*FAIL\|FAIL: lock'`
Expected: non-zero (`invalid choice: 'lock'`).

- [ ] **Step 3: Implement `lock`**

Insert before the `# CLI` banner:

```python
# ---------------------------------------------------------------------------
# lock — the primary-checkout lock (spec §4)
# ---------------------------------------------------------------------------

LOCK_STALE_SECONDS = 30 * 60
LOCK_POLL_SECONDS = 15
LOCK_TIME_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _lock_dir(a):
    root = a.root
    if not root:
        top = _git_toplevel(os.getcwd()) or os.getcwd()
        root = os.path.join(top, ".claude", "notion-dev", "locks")
    return os.path.join(root, "primary")


def _read_owner(d):
    kv = {}
    try:
        with open(os.path.join(d, "owner"), encoding="utf-8") as fh:
            for ln in fh:
                if ": " in ln:
                    k, v = ln.rstrip("\n").split(": ", 1)
                    kv[k] = v
    except OSError:
        pass
    return kv


def _owner_age(kv):
    try:
        since = datetime.datetime.strptime(kv.get("since", ""), LOCK_TIME_FMT)
    except ValueError:
        return LOCK_STALE_SECONDS + 1  # unreadable owner counts as abandoned
    return (datetime.datetime.utcnow() - since).total_seconds()


def _held_line(kv):
    return "held by %s (%s) since %s" % (kv.get("run", "?"), kv.get("section", "?"), kv.get("since", "?"))


def _write_owner(d, run, section):
    now = datetime.datetime.utcnow().strftime(LOCK_TIME_FMT)
    with open(os.path.join(d, "owner"), "w", encoding="utf-8") as fh:
        fh.write("run: %s\nsection: %s\nsince: %s\n" % (run, section, now))


def cmd_lock(a):
    d = _lock_dir(a)
    if a.op == "status":
        kv = _read_owner(d) if os.path.isdir(d) else {}
        print(_held_line(kv) if kv else "free")
        sys.exit(0)
    if a.op == "release":
        kv = _read_owner(d) if os.path.isdir(d) else {}
        if not kv:
            print("not held")
            sys.exit(1)
        if kv.get("run") != a.run:
            print("refused: " + _held_line(kv))
            sys.exit(1)
        shutil.rmtree(d)
        print("released")
        sys.exit(0)
    # take
    deadline = time.time() + a.wait
    while True:
        try:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            os.mkdir(d)
            _write_owner(d, a.run, a.section)
            print("taken")
            sys.exit(0)
        except FileExistsError:
            pass
        kv = _read_owner(d)
        if kv.get("run") == a.run:
            print("reentrant")
            sys.exit(0)
        if _owner_age(kv) > LOCK_STALE_SECONDS:
            print("stale: run: %s" % kv.get("run", "?"))
            shutil.rmtree(d, ignore_errors=True)
            continue
        if time.time() >= deadline:
            print(_held_line(kv))
            sys.exit(1)
        time.sleep(LOCK_POLL_SECONDS)
```

Add `import shutil`, `import time`, `import datetime` if absent. Register in `main()`:

```python
    p_lock = sub.add_parser("lock", help="the primary-checkout lock (spec §4)")
    lock_sub = p_lock.add_subparsers(dest="op", required=True)
    p_take = lock_sub.add_parser("take")
    p_take.add_argument("--run", required=True)
    p_take.add_argument("--section", required=True)
    p_take.add_argument("--wait", type=int, default=600, help="seconds to wait (default 600)")
    p_rel = lock_sub.add_parser("release")
    p_rel.add_argument("--run", required=True)
    p_stat = lock_sub.add_parser("status")
    for p in (p_take, p_rel, p_stat):
        p.add_argument("--root", default=None, help="locks directory (default: <git toplevel>/.claude/notion-dev/locks)")
        p.set_defaults(func=cmd_lock)
```

- [ ] **Step 4: Run the harness to see it pass**

Run: `./scripts/verify-knowledge-py.sh`
Expected: every `lock-*` line `ok` and every lock `assert_*` `PASS`.

- [ ] **Step 5: Commit**

```bash
git add plugins/notion-dev/scripts/knowledge.py scripts/verify-knowledge-py.sh
git commit -m "feat(knowledge.py): lock — mkdir lock on the primary checkout, re-entrant, stale after 30m

Claude-Session: https://claude.ai/code/session_01EPBePxetmA6tMtXPRtRxHd"
```

---

### Task 3: Two-clone convergence — the write path's git recipe under a rejected push

**Files:**
- Test: `scripts/verify-knowledge-py.sh` (append a `== write path ==` block)
- Create: `scripts/fixtures/knowledge/next/state-converge-a.json`, `state-converge-b.json`

**Interfaces:**
- Consumes: `knowledge.py next` (Task 1).
- Produces: nothing new; proves the recipe Task 4 writes as the write path's step 4.

- [ ] **Step 1: Write the state fixtures**

`state-converge-a.json`: a copy of `state-create.json` (STO-74 exists; A will `create` it).
`state-converge-b.json`: `state-create.json` with STO-71's `status_class` set to `"in_progress"` — B's live view already includes A's new child and its own claim, as Notion would.

- [ ] **Step 2: Write the failing harness block**

```bash
echo "== write path: a rejected push converges by re-deriving against the fresh brief =="
CV=$(mktemp -d)
G="git -c user.name=t -c user.email=t@t -c init.defaultBranch=main -c commit.gpgsign=false"
$G init -q --bare "$CV/origin.git"
$G clone -q "$CV/origin.git" "$CV/a" 2>/dev/null
mkdir -p "$CV/a/knowledge/epic"; cp "$NX/brief.md" "$CV/a/knowledge/epic/STO-60-wallet-indexing.md"
( cd "$CV/a" && $G add -A && $G commit -q -m seed && $G push -q origin main ) 2>/dev/null
$G clone -q "$CV/origin.git" "$CV/b" 2>/dev/null
B=knowledge/epic/STO-60-wallet-indexing.md
# A: create STO-74 and push
python3 "$PY" next --brief "$CV/a/$B" --state "$NX/state-converge-a.json" --today 2026-09-14 --reason create STO-74 > "$CV/a/out.md" 2>/dev/null
cp "$CV/a/out.md" "$CV/a/$B"
( cd "$CV/a" && $G commit -q --only -m "docs(epic): STO-60 create STO-74" -- "$B" && $G push -q origin main ) 2>/dev/null \
  && ok "write path: A's commit and push land" || bad "write path: A's commit or push failed"

# B, stale clone: start STO-71, push rejected
python3 "$PY" next --brief "$CV/b/$B" --state "$NX/state-converge-b.json" --today 2026-09-15 --reason start STO-71 > "$CV/b/out.md" 2>/dev/null
cp "$CV/b/out.md" "$CV/b/$B"
( cd "$CV/b" && $G commit -q --only -m "docs(epic): STO-60 start STO-71" -- "$B" ) 2>/dev/null
if ( cd "$CV/b" && $G push -q origin main ) 2>/dev/null; then bad "write path: B's stale push should be rejected"; else ok "write path: B's stale push is rejected"; fi
# the recipe: exactly one local commit ahead, fetch, reset --hard, re-derive, commit, push
( cd "$CV/b" && $G fetch -q origin main && n=$($G rev-list origin/main..HEAD | wc -l | tr -d ' ') && [ "$n" -eq 1 ] ) \
  && ok "write path: rev-list shows exactly one local commit before the reset" || bad "write path: rev-list count is not 1"
( cd "$CV/b" && $G reset -q --hard origin/main ) 2>/dev/null
python3 "$PY" next --brief "$CV/b/$B" --state "$NX/state-converge-b.json" --today 2026-09-15 --reason start STO-71 > "$CV/b/out2.md" 2>/dev/null
cp "$CV/b/out2.md" "$CV/b/$B"
( cd "$CV/b" && $G commit -q --only -m "docs(epic): STO-60 start STO-71" -- "$B" && $G push -q origin main ) 2>/dev/null \
  && ok "write path: the re-derived commit pushes (ATTEMPTS: 2)" || bad "write path: second push failed"
$G clone -q "$CV/origin.git" "$CV/c" 2>/dev/null
assert_has "write path: origin carries B's start"          "$CV/c/$B" 'In progress: [STO-71] Cache metrics — since 2026-09-15, [STO-72] Backfill v2 — since 2026-09-14'
assert_has "write path: origin still carries A's created child" "$CV/c/$B" '2. [STO-74] Dashboards — ready'
assert_has "write path: the header names B's start"        "$CV/c/$B" 'after start [STO-71]'
( cd "$CV/c" && $G log --format=%s ) > "$OUT/cv-log.txt"
assert_lacks "write path: no merge commit was manufactured" "$OUT/cv-log.txt" 'Merge'
rm -rf "$CV"
```

- [ ] **Step 3: Run to see it pass**

Run: `./scripts/verify-knowledge-py.sh`
Expected: all `write path:` lines `PASS`. This block is proven both directions: temporarily change `--reason start STO-71` in the second B render to `--reason start STO-73` and confirm the `In progress` assertion fails; restore.

- [ ] **Step 4: Commit**

```bash
git add scripts/verify-knowledge-py.sh scripts/fixtures/knowledge/next/state-converge-a.json scripts/fixtures/knowledge/next/state-converge-b.json
git commit -m "test(knowledge.py): two-clone convergence proves the write path's rejected-push recipe

Claude-Session: https://claude.ai/code/session_01EPBePxetmA6tMtXPRtRxHd"
```

---

### Task 4: `epic-doc` — `refresh`, the write path, drift in `read`

**Files:**
- Modify: `plugins/notion-dev/skills/epic-doc/SKILL.md`
- Test: `scripts/verify-epic-doc.sh`

**Interfaces:**
- Consumes: L3–L7 (Tasks 1–2 commands).
- Produces: the `refresh` operation (L1), `## The write path` (L2), the extended output block (L8), `DRIFT:` in `read` (L9), commit subjects (L20), `LOCK_HELD` (L12). Tasks 5–6 cite these by name.

- [ ] **Step 1: Write the failing anchors**

Add to `scripts/verify-epic-doc.sh` after the existing `read` region block (inside the `if [ -n "$R0" ] && [ -n "$R1" ]` body or as a sibling block using the same variables):

```bash
# ---------------------------------------------------------------------------
echo "== epic-doc: refresh and the write path (spec 2026-09-15 §2–§3) =="
RF=$(find_line "$ED" 1 "$L" '^## `refresh\(<epic-id>, <reason>\)` — the derived writer$')
WP=$(find_line "$ED" 1 "$L" '^## The write path — every commit from the primary checkout$')
OB=$(find_line "$ED" 1 "$L" '^## Output block$')
[ -n "$RF" ] && ok "epic-doc defines \`refresh(<epic-id>, <reason>)\`" || bad "epic-doc lacks the refresh heading (L1)"
[ -n "$WP" ] && ok "epic-doc defines \`## The write path\`" || bad "epic-doc lacks the write path heading (L2)"
if [ -n "$RF" ] && [ -n "$WP" ]; then
  assert_present "template carries the \`In progress:\` line" "$ED" 1 "$R0" '^In progress: \[STO-72\] Backfill v2 — since 2026-09-15$'
  assert_present "refresh: the four reasons are \`start\`, \`stop\`, \`create\`, \`drift\`" "$ED" "$RF" "$WP" '`start <KEY>-<n>`.*`stop <KEY>-<n> <phase> <cause> <worktree-path>`.*`create <KEY>-<n>`.*`drift`'
  assert_present "refresh: derivation is \`knowledge.py\` \`next\` with \`--brief\`, \`--state\`, \`--today\`" "$ED" "$RF" "$WP" 'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/knowledge.py" next --brief <tmp brief> --state <tmp state.json> --today <YYYY-MM-DD>'
  assert_present "refresh: \`stop\` adds the bullet, \`start\` removes it" "$ED" "$RF" "$WP" '`stop` adds .* `start` removes'
  assert_present "refresh: byte-identical → \`unchanged\`, no commit" "$ED" "$RF" "$WP" 'Byte-identical .* `unchanged`, no commit'
  assert_present "write path step 1: \`lock take\` unless \`LOCK_HELD\`" "$ED" "$WP" "$OB" 'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/knowledge.py" lock take --run <run id> --section <name> --wait <seconds>.*LOCK_HELD'
  assert_present "write path step 2: \`git pull --ff-only origin <epicBranch>\`" "$ED" "$WP" "$OB" 'git pull --ff-only origin <epicBranch>'
  assert_present "write path step 4: \`git rev-list origin/<epicBranch>..HEAD\` must name one commit" "$ED" "$WP" "$OB" 'git rev-list origin/<epicBranch>\.\.HEAD'
  assert_present "write path step 4: \`git reset --hard origin/<epicBranch>\` only after the rev-list proof" "$ED" "$WP" "$OB" 'git reset --hard origin/<epicBranch>'
  assert_present "write path step 4: \`Three attempts.\`" "$ED" "$WP" "$OB" 'Three attempts\.'
  assert_present "write path step 5: \`lock release\` unless \`LOCK_HELD\`" "$ED" "$WP" "$OB" 'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/knowledge.py" lock release --run <run id>.*LOCK_HELD'
  assert_order "write path: lock, ff-pull, commit, push, converge, unlock in that order" "$ED" "$WP" "$OB" \
    take 'lock take --run' pull 'git pull --ff-only origin <epicBranch>' commit 'git commit --only' revlist 'git rev-list origin/<epicBranch>\.\.HEAD' reset 'git reset --hard origin/<epicBranch>' release 'lock release --run'
  assert_present "output block lists \`refreshed\` and \`unchanged\`" "$ED" "$OB" "$L" '^EPIC-DOC: created \| updated \| closed \| refreshed \| unchanged \| none \| failed$'
  assert_present "output block carries \`IN-PROGRESS:\`" "$ED" "$OB" "$L" '^IN-PROGRESS: '
  assert_present "output block carries \`DRIFT:\`" "$ED" "$OB" "$L" '^DRIFT: '
  assert_present "output block carries \`ATTEMPTS:\`" "$ED" "$OB" "$L" '^ATTEMPTS: '
  assert_present "read reports \`DRIFT: true\` and writes nothing" "$ED" "$R0" "$RB" 'DRIFT: true.*writes nothing'
  assert_absent "read never takes the lock" "$ED" "$R0" "$RB" 'lock take'
  assert_present "record step 2 recomputes \`## Next\` through \`refresh\`'s derivation" "$ED" "$R1" "$R2" '`## Next` — recompute through `refresh`'
  assert_present "record commits through the write path" "$ED" "$R1" "$R2" 'through `## The write path`'
  assert_count "commit subjects: after, bootstrap, note, start, stop, create, refresh (lines citing \`docs(epic):\`)" "$ED" 1 "$L" 'docs\(epic\):' 8
fi
```

The last line replaces the existing `assert_count … 'docs\(epic\):' 4`; delete that one. Set the count to the number of **lines** that carry `docs(epic):` after your edit (target 8: the existing four plus the L20 sentence, the write-path commit line, and the two `refresh` paragraphs — recount and fix the label and number to the truth).

- [ ] **Step 2: Run to see it fail**

Run: `./scripts/verify-epic-doc.sh | grep -c FAIL`
Expected: non-zero.

- [ ] **Step 3: Edit the template and the operations list**

In `## The file`'s template, insert after line `2. [STO-71] Cache metrics — after STO-70 (reads its index).`:

```
In progress: [STO-72] Backfill v2 — since 2026-09-15
```

In the intro paragraph, extend "written by …" with: `— and by \`refresh\`, which every start, stop, create and drift repair calls (see below).` Change "All three operations" to "All four operations".

Add to **Rules of content**, after the `## Next` bullet:

```
- **The three lists of `## Next` partition the unresolved children with no overlap**: the numbered
  list (runnable now or after a listed dependency), `In progress:` (claimed — every child whose
  live status is `statusMap.inProgress`, comma-separated in numeric-id order, each
  `[<KEY>-<n>] <title> — since <YYYY-MM-DD>`, the date the line first named the key), and
  `Blocked:` (held by an open thread). A child in none of the three is a defect `refresh`
  repairs, never a warning. An in-progress child that a thread also names is `In progress:` —
  the claim wins. Item 1 is never in progress. A stopped run is one thread bullet,
  `- **[<KEY>-<n>] stopped at <phase>** — <cause>; worktree at <path>. Unblocked by: /notion-dev:ticket <KEY>-<n> (resumes).`,
  and its key is `Blocked:` until a `start` removes the bullet.
```

- [ ] **Step 4: Add `DRIFT:` to `read`**

In `read` step 2, after `BOOTSTRAP`, add:

```
   — and `DRIFT`. `read` writes the root document to a temp file, assembles the §5 state JSON
   from `CHILDREN` and the epic's live status (`status_class` = `resolved` when the status is in
   the resolved set, `in_progress` when it equals `statusMap.inProgress`, else `open`; every
   unresolved child's `## Blocked by` keys, `metadata.phaseProperty`, `metadata.stepProperty`
   from one `fetchTicket` each — the same fetches `record` step 2 makes), runs the derivation
   command `refresh` names with no `--reason`, and reads only its stderr: `DRIFT: 0` → `DRIFT:
   false`; otherwise `DRIFT: true` with the `drift:` lines verbatim. `read` still writes nothing —
   not the brief, not a lock, nothing in the primary checkout: it runs before any worktree exists.
   Whoever writes next repairs the drift — `/notion-dev:ticket` through its Phase 2 `start`,
   `/notion-dev:next-task` through `refresh drift`.
```

- [ ] **Step 5: Add the `refresh` section**

Insert a new `## ` section between `## Bootstrap` and `## \`record(<id>)\``:

```
## `refresh(<epic-id>, <reason>)` — the derived writer

Recomputes the derived parts of the brief from live state and nothing else: the header's
`Status:` and `Updated:`, the whole `## Next` region, and — for two reasons — one stop bullet
under `## Open threads`. `<reason>` is one of `start <KEY>-<n>`, `stop <KEY>-<n> <phase> <cause> <worktree-path>`, `create <KEY>-<n>`, `drift`.

| reason | caller | effect beyond `## Next` |
|---|---|---|
| `start <KEY>-<n>` | `/notion-dev:ticket` Phase 2, after `updateStatus(id, "inProgress")` | removes that key's stop bullet when one exists |
| `stop <KEY>-<n> <phase> <cause> <worktree-path>` | `/notion-dev:ticket`'s failure-and-stop path | adds (or replaces) that key's stop bullet |
| `create <KEY>-<n>` | `/notion-dev:create-task` after a ticket gets an epic parent | none |
| `drift` | `/notion-dev:next-task` step 1 on `DRIFT: true` | none |

**Inputs, all live:** `fetchTicket(<epic-id>).status`, `listEpicChildren(<epic-id>)`, and one
`fetchTicket` per unresolved child for its `## Blocked by` keys, `metadata.phaseProperty` and
`metadata.stepProperty` — exactly what `record` step 2 fetches. `refresh` never reads the Notion
epic page body and never runs `iwe`.

**Derivation.** Write the current brief (loaded from `origin/<epicBranch>` by the write path's
step 2) to a temp file, assemble the state JSON `read` describes (plus `stop: { key, phase,
cause, worktree }` on a `stop`), and run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" next --brief <tmp brief> --state <tmp state.json> --today <YYYY-MM-DD>
```

with `--reason <word> <key>` for `start`, `stop` and `create`, and no `--reason` for `drift`. Its
stdout is the new brief in full — the `## Next` region, the header and the stop bullet rewritten,
every other byte preserved; its stderr lists the drift it repaired. The script partitions the
unresolved children, orders the numbered list by phase, step, then numeric id, puts the first
child whose every `## Blocked by` key is resolved at item 1 with its reason preserved when item 1
did not change (else `unblocked; <dep> landed` or `first in phase order`), writes `In progress:`
with each key's `since` preserved, and `Blocked:` from the threads' keys plus every stop bullet's
key. `stop` adds the bullet; `start` removes it. `Status: closed` and `epic complete` exactly when
the epic's live status is in the resolved set. Exit 0 means the brief was already true.

**Outcome.** Byte-identical brief → `unchanged`, no commit, `COMMIT: none`. Otherwise commit
through `## The write path` below with the subject `docs(epic): <KEY>-<n> start <key>`,
`docs(epic): <KEY>-<n> stop <key>`, `docs(epic): <KEY>-<n> create <key>` or `docs(epic): <KEY>-<n> refresh`,
by the pathspec `-- <brief path> <knowledge.dir>/index.md` (the catalog bullet rule of "The file"
applies here too), and return `refreshed`.

**Best-effort**, like every operation here: `failed` is recorded by the caller as
`partial:epic-doc` and never stops a run — except that `/notion-dev:next-task` does not select
from a brief whose drift refresh failed.
```

- [ ] **Step 6: Add `## The write path` section**

Insert immediately after the `refresh` section (before `## \`record(<id>)\``):

```
## The write path — every commit from the primary checkout

`refresh`, `record`, `record --bootstrap`, `note --apply` and `notion-dev:knowledge` `capture`
(both forms) commit and push from `$REPO_ROOT` through these five steps and no others. Stated
once here; the others cite it.

1. **Lock.** Unless the caller passed `LOCK_HELD`, take the primary lock:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section <name> --wait <seconds>` — `LOCK_HELD` means an enclosing section already holds it.
   Exit 1 → `failed`, `CAUSE: primary lock held by <run> (<section>) since <time>`; a printed
   `stale:` line → record `lock-stale:primary` per `notion-dev:issue-log` and name the old owner
   in the report. Read-only checks of the primary and `git worktree add` never take it.
2. **Establish the base.** `git -C $REPO_ROOT fetch origin <epicBranch>`. The primary must be on
   `<epicBranch>`; the operations whose contract allows a checkout — `refresh` (all reasons) and
   `record --bootstrap` — run `git -C $REPO_ROOT checkout <epicBranch>` when the primary is clean
   outside the exempt paths; the others assert the branch as before. Then
   `git -C $REPO_ROOT pull --ff-only origin <epicBranch>`. A `--ff-only` failure → `failed`,
   `CAUSE: <epicBranch> has diverged from origin` — never stash, never reset a diverged base.
   After this step the three ref assertions of `/notion-dev:ticket` Phase 9 hold by
   construction, and the porcelain check on the operation's pathspec must be empty, as before.
3. **Derive and commit.** Write the files, `git add` them, then, if
   `git diff --cached --quiet -- <pathspec>` succeeds → `unchanged`, `COMMIT: none`, go to 5.
   Otherwise `git commit --only -m "<subject>" -- <pathspec>`.
4. **Push, converge on rejection.** `git push origin <epicBranch>`. On a non-fast-forward
   rejection: `git -C $REPO_ROOT fetch origin <epicBranch>`, then assert
   `git rev-list origin/<epicBranch>..HEAD` names **exactly one** commit — this attempt's own.
   Anything else → `failed`, commit left in place, `CAUSE: push rejected — <git's message>`,
   as before. One commit → `git reset --hard origin/<epicBranch>` (safe only here: step 2
   required a clean pathspec and the rev-list proved the sole local commit is ours), re-derive
   against the fresh files, and go back to step 3. **Three attempts.** `record` and `note --apply`
   re-apply their diff *semantically* — the bullets they add and remove, the sentence they
   restate — to the fresh brief; `refresh` and `capture` simply re-derive. The third rejection
   is `failed` with the local commit left in place and the caller's `blocked:` closeout line, as
   before. Under `--branch <noteBranch>` there is no push and no retry.
5. **Unlock.** Unless the caller passed `LOCK_HELD`:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`. Report
   `ATTEMPTS: <n>` — the number of times step 3 ran.
```

- [ ] **Step 7: Reword `record` and `note` to the shared derivation and the write path**

In `record` step 2, replace the `## Next` bullet with:

```
   - `## Next` — recompute through `refresh`'s derivation: assemble the state JSON from
     `listEpicChildren(<epic-id>)` and one `fetchTicket` per unresolved child, run the
     `knowledge.py next` command `refresh` names with `--reason resolve <ticket key>`, and take
     its `## Next` region and header; the open threads this step wrote decide `thread_blocked`.
```

In `record` step 4, replace the sentence beginning `**Commit by pathspec, never the whole index:**` through the push sentence with: `**Commit and push through \`## The write path\`** — subject \`docs(epic): <KEY>-<n> after <ticket key>\`, pathspec \`-- <brief path> <knowledge.dir>/index.md [<seed path>]\` (\`--only\`, for the reason the write path gives). The path's byte-identical test is the existing "already recorded" rule: \`THREADS: +0 -0\`, no commit, no push.` Keep the `Push rejected` step 5 but reword its first clause to `after the write path's third attempt`.

In `note` test 4, replace `recompute \`## Next\` exactly as \`record\` step 2 does:` with `recompute \`## Next\` through \`refresh\`'s derivation with \`--reason new-info\`, as \`record\` step 2 does:`. In `note --apply` step 3, replace the commit-and-push sentence with `commit and push through \`## The write path\` — subject \`docs(epic): note <KEY>-<n> — <short fact>\`, the same pathspec; skipped push under \`--branch\`.`

Reword `record`'s preconditions paragraph's first sentence to: `Called from \`$REPO_ROOT\`, after cleanup, with the primary on the base branch, inside the caller's \`record\` lock section (\`LOCK_HELD\`). The write path's step 2 establishes what the post-merge-hook step asserts:` and keep the three lines.

- [ ] **Step 8: Extend the output block**

Replace the output block with:

```
EPIC-DOC: created | updated | closed | refreshed | unchanged | none | failed
PATH: knowledge/epic/STO-60-wallet-indexing.md              (omit on none)
SEED: docs/STO-67-release-plan.md · last at a1b2c3d         (only when created from a seed)
THREADS: +2 -1                                              (bullets added / removed this run)
NEXT: [STO-70] Backfill historic wallets — <reason>         (or `epic complete`, or `blocked: <thread>`)
IN-PROGRESS: STO-72                                         (keys on the In progress line; `none` when empty)
DRIFT: <one line per repaired finding>                      (or `none`)
COMMIT: <sha> | none
ATTEMPTS: 1                                                 (write-path attempts)
CAUSE: <failed assertion, lock timeout, or push rejection>  (only on failed)
```

Add after the existing `closed means …` paragraph: `` `refreshed` and `unchanged` are `refresh`'s two success values. ``

- [ ] **Step 9: Run the suite; fix wrapped literals**

Run: `./scripts/verify-epic-doc.sh && ./scripts/verify-new-info.sh && ./scripts/verify-knowledge.sh`
Expected: all `PASS`. `verify-new-info.sh` and `verify-knowledge.sh` anchor lines in `note` and `record` that you reworded — when one fails, re-read its label and regex, keep the mechanism it guards in the new wording on one line, and never weaken the regex.

- [ ] **Step 10: Commit**

```bash
git add plugins/notion-dev/skills/epic-doc/SKILL.md scripts/verify-epic-doc.sh
git commit -m "feat(epic-doc): refresh — derived ## Next, one write path that converges, drift in read

Claude-Session: https://claude.ai/code/session_01EPBePxetmA6tMtXPRtRxHd"
```

---

### Task 5: `ticket.md` and `finalize.md` — `refresh start`, `refresh stop`, the `record` lock section

**Files:**
- Modify: `plugins/notion-dev/commands/ticket.md` (Phase 2, Phase 8.2 opening, Phase 10 after `record`, failure-and-stop path, report bullets), `plugins/notion-dev/commands/finalize.md` (Phase 3 opening, Phase 5 after `record`)
- Create: `scripts/verify-primary-lock.sh` (ticket and finalize portion; Task 6 adds the rest)

**Interfaces:**
- Consumes: L1, L2, L12 (Task 4).
- Produces: L13, L14, L17/L18 for sections `start`, `record`, `stop`.

- [ ] **Step 1: Write the failing harness**

Create `scripts/verify-primary-lock.sh`:

```bash
#!/usr/bin/env bash
# The primary-checkout lock — every section that commits from the primary checkout or rewrites
# the Notion epic page takes `knowledge.py lock take` and releases it, with the wait spec §4
# assigns; `read` never takes it.
#
# Spec: docs/superpowers/specs/2026-09-15-brief-freshness-and-parallel-tickets-design.md §4, §6
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
TICKET=$ND/commands/ticket.md
FINALIZE=$ND/commands/finalize.md
NT=$ND/commands/next-task.md
NI=$ND/commands/new-info.md
KC=$ND/commands/knowledge.md
CT=$ND/commands/create-task.md
ED=$ND/skills/epic-doc/SKILL.md
KS=$ND/skills/knowledge/SKILL.md

TAKE='knowledge\.py" lock take --run <run id> --section '
REL='knowledge\.py" lock release --run <run id>'

# section <label> <file> <start-ere> <end-ere> <section-word> <wait>
section() {
  local label=$1 f=$2 s_re=$3 e_re=$4 word=$5 wait=$6
  local L; L=$(total_lines "$f")
  local s; s=$(find_line "$f" 1 "$L" "$s_re")
  [ -n "$s" ] || { bad "$label: start anchor not found ($s_re)"; return; }
  local e; e=$(find_line "$f" "$((s + 1))" "$L" "$e_re"); [ -n "$e" ] || e=$L
  assert_present "$label: takes the lock with \`--section $word\` and \`--wait $wait\`" "$f" "$s" "$e" "${TAKE}${word} --wait ${wait}"
  assert_present "$label: releases the lock (\`lock release\`)" "$f" "$s" "$e" "$REL"
  assert_order "$label: take before release" "$f" "$s" "$e" take "${TAKE}${word}" release "$REL"
}

echo "== ticket.md =="
section "ticket Phase 2 start"   "$TICKET" '^## Phase 2 '  '^## Phase 3 '            start  600
section "ticket record section"  "$TICKET" '^### 8\.2 '    '^\*\*Closeout — zero tails' record 3600
section "ticket stop path"       "$TICKET" '^## Failure and stop conditions' '^## [^F]' stop 600
echo "== finalize.md =="
section "finalize record section" "$FINALIZE" '^## Phase 3 ' '^\*\*Closeout — zero tails' record 3600

L=$(total_lines "$TICKET")
P2=$(find_line "$TICKET" 1 "$L" '^## Phase 2 '); P3=$(find_line "$TICKET" 1 "$L" '^## Phase 3 ')
assert_present "ticket Phase 2: \`refresh(<epic-id>, start <key>)\` after \`updateStatus(id, \"inProgress\")\`" "$TICKET" "$P2" "$P3" 'operation `refresh\(<epic-id>, start <key>\)`'
assert_order "ticket Phase 2: worktree, then status, then refresh start" "$TICKET" "$P2" "$P3" \
  worktree 'git worktree add <worktree-path>' status 'updateStatus\(id, "inProgress"\)' refresh 'operation `refresh\(<epic-id>, start <key>\)`'
FS=$(find_line "$TICKET" 1 "$L" '^## Failure and stop conditions')
assert_present "ticket stop path: \`refresh(<epic-id>, stop <key> <phase> <cause> <worktree-path>)\`" "$TICKET" "$FS" "$L" 'operation `refresh\(<epic-id>, stop <key> <phase> <cause> <worktree-path>\)`'
P82=$(find_line "$TICKET" 1 "$L" '^### 8\.2 '); P10=$(find_line "$TICKET" 1 "$L" '^## Phase 10 ')
assert_present "ticket 8.2: \`epic-update\` runs with \`LOCK_HELD\`" "$TICKET" "$P82" "$P10" 'epic-update.*LOCK_HELD'
assert_present "ticket Phase 10: \`record\` runs with \`LOCK_HELD\`" "$TICKET" "$P10" "$L" 'operation `record\(<id>\)`.*LOCK_HELD'
assert_present "ticket Phase 9 hooks: \`notion-dev:knowledge\` hook receives \`LOCK_HELD\`" "$TICKET" "$P82" "$P10" 'hook receives .*LOCK_HELD'
assert_present "ticket report names lock waits" "$TICKET" "$P10" "$L" '^- \*\*Lock waits\*\*'

echo "== epic-doc read takes nothing =="
LE=$(total_lines "$ED"); R0=$(find_line "$ED" 1 "$LE" '^## `read\('); RB=$(find_line "$ED" 1 "$LE" '^## Bootstrap')
assert_absent "epic-doc read never takes the lock" "$ED" "$R0" "$RB" 'lock take'

if [ "$fails" -gt 0 ]; then echo "verify-primary-lock: $fails FAIL"; exit 1; fi
echo "verify-primary-lock: all PASS"
```

`chmod +x scripts/verify-primary-lock.sh`. Task 6 appends the next-task, new-info, knowledge and create-task sections to this file.

- [ ] **Step 2: Run to see it fail**

Run: `./scripts/verify-primary-lock.sh | grep -c FAIL` — Expected: non-zero. Also `./scripts/verify-assertions.sh` must pass on the new harness (it sources only `assert.sh`).

- [ ] **Step 3: Edit `ticket.md` Phase 2**

After the `updateStatus(id, "inProgress")` bullet and before `All subsequent file work happens in the worktree.`, insert:

```
**Mark the brief — the `start` section.** When the ticket has an epic (`metadata.parentTaskProperty` non-empty), from `$REPO_ROOT`:

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section start --wait 600` — `<run id>` is `<KEY>-<id>`. Exit 1 → record `lock-timeout:primary` per `notion-dev:issue-log`, skip this section, and say so in the report; a `stale:` line → record `lock-stale:primary`.
2. Invoke the `notion-dev:epic-doc` skill, operation `refresh(<epic-id>, start <key>)`, passing `REPO_ROOT`, `<epicBranch>` and `LOCK_HELD`. It moves the ticket to the brief's `In progress:` line, repairs any drift 1.1's `read` reported, removes a stop bullet left by an earlier stopped run of this ticket, and commits `docs(epic): <KEY>-<n> start <key>` to `<epicBranch>` through the write path. Record its block as `EPIC_DOC_START`; `failed` → `partial:epic-doc`, never a stop.
3. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`.

The worktree exists before this section (2.1) and the status is set before it, so the claim precedes every mirror of it. The primary is clean by precondition, which is what lets the write path check out `<epicBranch>` there.
```

- [ ] **Step 4: Edit `ticket.md` Phase 8.2, Phase 9 hooks, Phase 10**

At the top of `### 8.2 Update the epic`, before `Invoke the \`notion-dev:epic-update\` skill`, insert:

```
**The `record` section begins here and ends after Phase 10's `record`.** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section record --wait 3600` — `<run id>` is `<KEY>-<id>`. Exit 1 → stop per "Failure and stop conditions" with `CAUSE: primary lock held by <run> (<section>) since <time>`: cleanup cannot be skipped, so the run does not proceed without the lock. A `stale:` line → record `lock-stale:primary` and name the old owner in the report. Everything from here to the end of Phase 10's epic-doc step — `epic-update`'s rewrite of the Notion epic page, cleanup's checkout and pull of the primary, the post-merge hooks, and `record` — runs with the lock held; the invocations below pass `LOCK_HELD` so none of them takes it again.
```

Change the `epic-update` invocation sentence to add `, and \`LOCK_HELD\`` to its context list (so the line reads `… Pass \`REVIEW_REPORT\` (Phase 7), \`$REPO_ROOT\` and \`LOCK_HELD\` as context.` — one line containing both `epic-update` and `LOCK_HELD`).

In `### Post-merge hooks`, change `The hook receives \`<ticket-id>\`, \`<merge-sha>\`, the ticket body, \`KNOWLEDGE_CONTEXT\`, and this run's review report — nothing from Notion.` to `The hook receives \`<ticket-id>\`, \`<merge-sha>\`, the ticket body, \`KNOWLEDGE_CONTEXT\`, this run's review report, and \`LOCK_HELD\` — nothing from Notion.`

In Phase 10's epic-doc paragraph, add `LOCK_HELD` to the context list so the sentence `invoke the \`notion-dev:epic-doc\` skill, operation \`record(<id>)\`, from \`$REPO_ROOT\`, passing as context: \`REPO_ROOT\`, \`LOCK_HELD\`, …` is one line containing both literals. After that paragraph, add:

```
**The `record` section ends here:** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>` — on this path and on every failure inside the section, before anything else is reported.
```

Add to the Phase 10 summary bullets, after the post-merge hooks bullet:

```
- **Lock waits** — one line per section that waited: `waited <m>m for <run> (<section>)`; a broken stale lock: `broke stale lock held by <run> since <time>`. Omit the line entirely when no section waited.
- **Brief at start** — `EPIC_DOC_START`'s outcome (`refreshed` / `unchanged` / `failed` with `CAUSE:`) and its `DRIFT:` line when it was not `none`. Omit when the ticket had no epic.
```

- [ ] **Step 5: Edit the failure-and-stop path**

In the `**On any unrecoverable failure**` bullet, after the sentence ending `The Notion ticket stays "In Progress" — no failure status is ever written to Notion.`, append:

```
Also best-effort, before stopping, when the ticket has an epic — the `stop` section: confirm the primary is clean outside the exempt paths (`git -C $REPO_ROOT status --porcelain`), else skip with `brief not marked: primary checkout dirty` in the stop report; `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section stop --wait 600` (exit 1 → skip, `lock-timeout:primary`); invoke the `notion-dev:epic-doc` skill, operation `refresh(<epic-id>, stop <key> <phase> <cause> <worktree-path>)`, with `REPO_ROOT`, `<epicBranch>`, `LOCK_HELD`, `<phase>` the phase that failed, `<cause>` one clause, `<worktree-path>` from 1.2/2.1 — it writes the stop bullet, moves the ticket to `Blocked:`, and commits `docs(epic): <KEY>-<n> stop <key>`; then `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`. When the failure happened inside the `record` section, that section's release runs first, and this one takes the lock afresh. Print the `EPIC-DOC:` block in the stop report.
```

- [ ] **Step 6: Edit `finalize.md`**

At the top of `## Phase 3 — Record`, before `### 3.1`, insert the same `record`-section paragraph as ticket 8.2 with `<run id>` = `finalize <pr>` (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section record --wait 3600`). Add `LOCK_HELD` to 3.2's `epic-update` context and Phase 5's `record` context exactly as in ticket. After Phase 5's epic-doc paragraph, add the same `**The \`record\` section ends here:**` release line. Add the `**Lock waits**` report bullet.

- [ ] **Step 7: Run the suite**

Run: `for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done`
Expected: all pass. `verify-post-merge-ordering.sh` asserts Phase 9's order and the hook contract; the new lines must not sit between the mechanisms it orders (a `lock` line before 8.2 and after Phase 10's record is outside its regions). If it fails, move the inserted paragraph, never the harness.

- [ ] **Step 8: Commit**

```bash
git add plugins/notion-dev/commands/ticket.md plugins/notion-dev/commands/finalize.md scripts/verify-primary-lock.sh
git commit -m "feat(ticket,finalize): refresh start/stop, record section under the primary lock

Claude-Session: https://claude.ai/code/session_01EPBePxetmA6tMtXPRtRxHd"
```

---

### Task 6: `next-task`, `new-info`, `create-task`, the `knowledge` command and skill, signatures

**Files:**
- Modify: `plugins/notion-dev/commands/next-task.md`, `new-info.md`, `create-task.md`, `knowledge.md`; `plugins/notion-dev/skills/knowledge/SKILL.md`; `plugins/notion-dev/skills/issue-log/references/signatures.md`
- Test: `scripts/verify-primary-lock.sh` (append), `scripts/verify-knowledge.sh`, `scripts/verify-new-info.sh` (anchors)

**Interfaces:**
- Consumes: L1, L2, L12 (Task 4); the `section` helper of `verify-primary-lock.sh` (Task 5).
- Produces: L15, L16, L19; sections `drift`, `bootstrap`, `apply`, `capture`, `migrate`, `create`.

- [ ] **Step 1: Append the failing anchors to `scripts/verify-primary-lock.sh`** (before the final `if [ "$fails" -gt 0 ]`):

```bash
echo "== next-task.md =="
section "next-task bootstrap" "$NT" '^\*\*`BOOTSTRAP: true`' '^\*\*`DRIFT: true`' bootstrap 600
section "next-task drift"     "$NT" '^\*\*`DRIFT: true`'     '^### 2\. Pick' drift 600
LN=$(total_lines "$NT"); S1=$(find_line "$NT" 1 "$LN" '^### 1\. Read the brief'); S2=$(find_line "$NT" 1 "$LN" '^### 2\. Pick')
assert_present "next-task step 1: \`refresh(<epic-id>, drift)\` on \`DRIFT: true\`" "$NT" "$S1" "$S2" 'operation `refresh\(<epic-id>, drift\)`'
assert_present "next-task step 1: splices the refreshed brief into \`KNOWLEDGE_CONTEXT\` — no second retrieve" "$NT" "$S1" "$S2" 'replace the root document of .*KNOWLEDGE_CONTEXT.*no second `retrieve`'
assert_present "next-task step 1: a failed drift refresh stops the loop" "$NT" "$S1" "$S2" 'drift refresh .*`EPIC-DOC: failed` → stop'
echo "== new-info.md =="
section "new-info apply" "$NI" '^### Apply' '^### Notion epic' apply 600
LI=$(total_lines "$NI"); A0=$(find_line "$NI" 1 "$LI" '^### Apply'); A1=$(find_line "$NI" 1 "$LI" '^### Notion epic')
assert_present "new-info apply: \`note --apply\` receives \`LOCK_HELD\`" "$NI" "$A0" "$A1" 'operation `note --apply <epic-id>`.*LOCK_HELD'
assert_present "new-info apply: \`capture --fact\` receives \`LOCK_HELD\`" "$NI" "$A0" "$A1" 'operation `capture --fact <fact> <epic-id>`.*LOCK_HELD'
echo "== knowledge.md =="
section "knowledge capture" "$KC" '^## `capture <ticket-id> <merge-sha>`$' '^## `migrate`$' capture 600
section "knowledge migrate" "$KC" '^## `migrate`$' '^## `curate`$'  migrate 600
echo "== create-task.md =="
section "create-task create" "$CT" '^### 3\.2 ' '^## Phase 4' create 600
LC=$(total_lines "$CT"); C0=$(find_line "$CT" 1 "$LC" '^### 3\.2 '); C1=$(find_line "$CT" 1 "$LC" '^## Phase 4')
assert_present "create-task 3.2: \`refresh(<epic-id>, create <key>)\` after the page has a parent" "$CT" "$C0" "$C1" 'operation `refresh\(<epic-id>, create <key>\)`'
assert_present "create-task 3.2: skipped under \`LOCK_HELD\` (epic-update filing)" "$CT" "$C0" "$C1" 'invoked with `LOCK_HELD`'
echo "== knowledge skill: capture commits through the write path =="
LK=$(total_lines "$KS")
assert_present "knowledge capture: commits and pushes through \`## The write path\`" "$KS" 1 "$LK" 'through `## The write path`'
assert_absent "knowledge capture: no longer states its own push (\`Then push as\`)" "$KS" 1 "$LK" 'Then push as `epic-doc record` pushes'
echo "== signatures =="
SIG=$ND/skills/issue-log/references/signatures.md; LS=$(total_lines "$SIG")
assert_present "signature \`lock-stale:primary\`"   "$SIG" 1 "$LS" '^\| `lock-stale:primary` \| unexpected \|'
assert_present "signature \`lock-timeout:primary\`" "$SIG" 1 "$LS" '^\| `lock-timeout:primary` \| degraded \|'
assert_present "signature \`partial:epic-doc\` now covers \`refresh\` in \`next-task.md\` and \`create-task.md\`" "$SIG" 1 "$LS" '^\| `partial:epic-doc` \| degraded \| `ticket.md`, `finalize.md`, `next-task.md`, `create-task.md` \|.*refresh'
```

If `verify-knowledge.sh` anchored the sentence you replaced in `knowledge/SKILL.md`, update that anchor to the write-path citation (same label meaning, new mechanism) — never delete the assertion.

- [ ] **Step 2: Run to see it fail** — `./scripts/verify-primary-lock.sh | grep -c FAIL` → non-zero.

- [ ] **Step 3: Edit `next-task.md` step 1**

Wrap the bootstrap paragraph: before `git -C $REPO_ROOT checkout <epicBranch> && …` insert `` `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section bootstrap --wait 600` (`<run id>` is `next-task <KEY>-<n>`; exit 1 → stop with `CAUSE: primary lock held by <run> (<section>) since <time>` — a brief that cannot be committed is not a basis for selection), then `` and pass `LOCK_HELD` to `record --bootstrap`; after `Then re-run step 1's \`retrieve\`` add `` , and `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>` first ``. Keep each `lock` literal on one line.

After the bootstrap paragraph add:

```
**`DRIFT: true` — repair the brief before picking.** `read` compared the brief's three lists and header against the live children and found them apart (a resolved child still listed, a child in the wrong list, a missing child, a header status that disagrees). From `$REPO_ROOT`: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section drift --wait 600`, then invoke the `notion-dev:epic-doc` skill, operation `refresh(<epic-id>, drift)`, passing `REPO_ROOT`, `<epicBranch>` and `LOCK_HELD`, then `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`. Then **splice, do not re-read**: replace the root document of the held `KNOWLEDGE_CONTEXT` with the refreshed brief and re-parse `NEXT`, `BLOCKED`, `STATUS` from it — no second `retrieve`; the bundle's other concepts did not change. A drift refresh that returns `EPIC-DOC: failed` → stop with its `CAUSE:` — selection from a brief that could not be repaired is guessing, the same rule the bootstrap applies. `unchanged` cannot occur here (`read` found drift), but is handled as `refreshed` if it does.
```

- [ ] **Step 4: Edit `new-info.md` `### Apply`**

At the top of `### Apply`, before `**\`BOOTSTRAP: true\` first.**`, insert: `` **The `apply` section.** Once per run, before the first epic's apply: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section apply --wait 600` (`<run id>` is `new-info`; exit 1 → report every epic as `skipped — primary lock held by <run> (<section>) since <time>`, record `lock-timeout:primary`, and go to the report). Every `record --bootstrap`, `note --apply` and `capture --fact` below receives `LOCK_HELD`. After the last epic — on every path, including a rejected push that stopped the loop — `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`. `` Then add `LOCK_HELD` to the context lists of the `note --apply <epic-id>` sentence and the `capture --fact <fact> <epic-id>` sentence so each is one line containing both literals. The release sentence must sit inside `### Apply` (before `### Notion epic`).

- [ ] **Step 5: Edit `knowledge.md` (command)**

In `## \`capture <ticket-id> <merge-sha>\``: first step `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section capture --wait 600` (`<run id>` is `knowledge`), pass `LOCK_HELD` to the skill, last step `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`. Same for `## \`migrate\`` with `--section migrate`. `curate` writes nothing and takes no lock.

- [ ] **Step 6: Edit `skills/knowledge/SKILL.md` `capture`**

Replace the paragraph beginning `Then push as \`epic-doc record\` pushes` (SKILL.md ~line 274) and any rejected-push wording that follows it in `capture` with: `Then commit and push through \`## The write path\` of \`notion-dev:epic-doc\` — the same five steps, with the subjects above and the pathspec \`-- <knowledge.dir>\`; \`capture\` re-derives on a rejected push exactly as \`refresh\` does, and under \`--branch\` there is no push. The caller's \`LOCK_HELD\` is passed through.` Keep the four precondition lines (they are what the write path's step 2 establishes) and keep `KNOWLEDGE:` / `COMMIT:` unchanged.

- [ ] **Step 7: Edit `create-task.md` 3.2**

After the `createTicket` result handling (after the ticket exists with `parent: EPIC_ID`), add:

```
**Mark the brief — the `create` section.** When `parent` was set: skip, saying why, when this command was invoked with `LOCK_HELD` (it is `epic-update` filing follow-ups; the enclosing `record` recomputes `## Next` moments later), when `git ls-tree -r --name-only origin/<epicBranch> -- <knowledge.dir>/epic/` lists no `<KEY>-<n>-*.md` for the epic (no brief yet — bootstrap will list this ticket), or when `git -C $REPO_ROOT status --porcelain` shows a tracked modification outside `/notion-dev:ticket`'s exempt paths. Otherwise, from `$REPO_ROOT` (the first path of `git worktree list`): `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section create --wait 600` (`<run id>` is `create-task`; exit 1 → skip, record `lock-timeout:primary`), invoke the `notion-dev:epic-doc` skill, operation `refresh(<epic-id>, create <key>)`, passing `REPO_ROOT`, `<epicBranch>` (`git.prTargetBranch`, falling back to `git.baseBranch`) and `LOCK_HELD`, then `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>`. Best-effort: `failed` → `partial:epic-doc`; the report's epic line gains ` · brief: refreshed | unchanged | skipped (<why>) | failed`. For a mission, one `refresh create <key>` per created task, inside one take/release.
```

- [ ] **Step 8: Edit `signatures.md`**

Widen the `partial:epic-doc` row's source column to `` `ticket.md`, `finalize.md`, `next-task.md`, `create-task.md` `` and append to its description: `; or a \`refresh\` (start, stop, create, drift) that returned \`failed\``. Add two rows after `partial:knowledge-capture`:

```
| `lock-stale:primary` | unexpected | any locked section | `knowledge.py lock take` broke an `owner` older than 30 minutes; the report names the old owner |
| `lock-timeout:primary` | degraded | any best-effort locked section | `knowledge.py lock take` timed out (`--wait 600`); the section was skipped and the report says which |
```

- [ ] **Step 9: Run the suite; fix anchors** — `for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done` → all pass. `verify-new-info.sh` and `verify-knowledge.sh` may anchor the sentences you reworded; keep the mechanism on one line and the regex intact.

- [ ] **Step 10: Commit**

```bash
git add plugins/notion-dev/commands plugins/notion-dev/skills/knowledge/SKILL.md plugins/notion-dev/skills/issue-log/references/signatures.md scripts/verify-primary-lock.sh scripts/verify-knowledge.sh scripts/verify-new-info.sh
git commit -m "feat(notion-dev): drift refresh, create refresh, apply/capture/migrate sections under the primary lock

Claude-Session: https://claude.ai/code/session_01EPBePxetmA6tMtXPRtRxHd"
```

---

### Task 7: README, version, mutation proof, full suite

**Files:**
- Modify: `plugins/notion-dev/README.md` (`## Epics` / `### Knowledge bundle`), `plugins/notion-dev/.claude-plugin/plugin.json`
- Test: every `scripts/verify-*.sh`; `scripts/verify-epic-doc.sh` version floor if it has one

- [ ] **Step 1: README**

Under `## Epics`, after the paragraph that describes the brief, add:

```
**`## Next` is kept true by the plugin, not by hand.** Its three lists partition the epic's
unresolved children: the numbered list (item 1 is the next ticket a session can start), an
`In progress:` line (claimed tickets, with the date each was claimed), and `Blocked:` (held by an
open thread). A ticket run marks the brief when it starts (`docs(epic): … start`), when it stops
with a worktree left behind (`… stop`, which also adds an open-thread bullet naming the worktree
and how to resume), and when it resolves (`… after`); `/notion-dev:create-task` marks a new child
(`… create`); and any read that finds the brief apart from Notion repairs it on the next write
(`… refresh`). Nothing polls Notion.

**One writer at a time on the primary checkout.** Every section that commits from the primary
checkout takes a directory lock at `.claude/notion-dev/locks/primary/` (self-ignored). A stuck
lock older than 30 minutes is broken and reported. Run reports list any wait.
```

- [ ] **Step 2: Version**

`plugins/notion-dev/.claude-plugin/plugin.json`: `"version": "0.24.0"` → `"0.25.0"`. If `verify-epic-doc.sh` or another harness asserts a version floor with `assert_version_above`, leave its baseline as is (it is a floor, not an equality).

- [ ] **Step 3: Full suite**

Run: `for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done`
Expected: no `FAILED:` line.

- [ ] **Step 4: Commit before mutating**

```bash
git add plugins/notion-dev/README.md plugins/notion-dev/.claude-plugin/plugin.json
git commit -m "docs(notion-dev): README — brief freshness and the primary lock; 0.25.0

Claude-Session: https://claude.ai/code/session_01EPBePxetmA6tMtXPRtRxHd"
```

- [ ] **Step 5: Mutation proof**

Write `$SCRATCH/mutate-brief-freshness.sh` (scratchpad, never committed) that, for every new assertion in `verify-epic-doc.sh`, `verify-primary-lock.sh`, `verify-knowledge-py.sh` (`next`, `lock`, write-path blocks) and the widened anchors in `verify-knowledge.sh` / `verify-new-info.sh`, applies one targeted `sed` that removes or alters the guarded line, runs the harness, records `HIT` when it reports `FAIL` and `MISS` otherwise, then `git checkout -- <file>`. Mutations to script behaviour: flip `first` to the last candidate, drop the `since` preservation, make `stop` not append, make `lock take` succeed on a held lock, make the stale threshold 0. Target: 0 MISS. Each MISS is a harness gap: add the assertion or fixture, commit, re-run.

- [ ] **Step 6: Regression proof on real-shaped data**

Run `python3 plugins/notion-dev/scripts/knowledge.py next --brief scripts/fixtures/knowledge/next/brief.md --state scripts/fixtures/knowledge/next/state-client-shaped.json --today 2026-09-15` and paste the rendered `## Next` region into the PR body, with one sentence on why the partition is right. The controller, not this task, runs the same command against a live children capture from a client epic (Notion access) and records the result in the PR body.

- [ ] **Step 7: Final full run and report**

Run the full suite once more; report the assertion counts per harness, the mutation HIT/MISS totals, and the commit list.
