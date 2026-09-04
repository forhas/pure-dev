# feedback-harvest — design

**Date**: 2026-09-04
**Status**: approved, pending implementation plan

## Problem

Client repos that install `notion-dev` accumulate a runtime issue log at
`.claude/notion-dev/notion-dev-issues.md`, written by the `notion-dev:issue-log` skill at the
moment each deviation happens. Two such clients exist today
(`smart-contracts-foundry`, `BTC-Gateway`) and between them hold ~28 signatures, a dozen of
which carry an explicit `Suggest …` note naming a concrete plugin change.

There is no counterpart to `issue-log` on the maintainer side. The log is *written* by a
mechanism and *read* by recall — which is exactly the asymmetry `issue-log`'s own header warns
about. The evidence that this happens ad hoc rather than systematically is already in the
tree: `plugins/notion-dev/commands/ticket.md:371` cites *"Measured on `notion-dev` 0.20.2:
BTC-Gateway STO-77 wrote no `review-report-STO-77.md` at all"* — one entry, harvested by hand,
while the rest of that file's entries sat unread.

The consequence is not that feedback is lost. It is that feedback is harvested **selectively
and invisibly**: nothing records which entries were considered and rejected, so the same
entry is re-read on every future pass, and an entry that was rejected for a good reason is
indistinguishable from one nobody ever looked at.

## What this builds

A repo-local maintainer skill, `feedback-harvest`, that runs in `pure-dev` and drives one
harvest to completion: read the client logs → triage each signature to exactly one of five
dispositions → apply the warranted fixes in one PR → archive the evidence in this repo →
reset the client logs.

## Non-goals

- **Not a client-facing feature.** It never ships to anyone who installs `quick-dev` or
  `notion-dev`.
- **Not a replacement for `issue-log`.** The write side is unchanged.
- **Not an automatic fixer.** Every applied change requires a stated reason why it improves the
  plugin. A signature is a suggestion to evaluate, never an instruction to follow.
- **Not multi-PR.** One harvest is one PR, per this repo's convergence rule.

---

## 1. Placement and the mirror carve-out

`pure-dev` drives its own work from `.claude/skills/`, not from installed plugins — the
`review-and-merge` and `session-closeout` skills available in a session here come from the
mirror, and neither plugin is installed. So an invocable skill must live under
`.claude/skills/`, which `scripts/verify-mirror.sh` currently requires to be a byte-identical
mirror of `plugins/quick-dev/skills/`.

`feedback-harvest` belongs to neither shipped plugin. It is a workflow for maintaining *this
marketplace*, and putting it in `quick-dev` (a generic feature-development plugin) or
`notion-dev` (whose skills are not mirrored, so it would still not be invocable here) would
misfile it either way.

**Resolution: a tracked repo-local allowlist.**

- New file `.claude/skills/REPO-LOCAL` — newline-delimited skill directory names, `#` comments
  allowed, tracked by git.
- `verify-mirror.sh` gains one rule: every directory under `.claude/skills/` is **either** a
  `quick-dev` mirror **or** named in `REPO-LOCAL`. A directory in neither still FAILs, so the
  mechanism `.gitignore` relies on — "an unmatched scratch file here is visible to `git add -A`,
  and this loop is what makes that exposure safe" — is preserved rather than weakened.

Three guards stop the carve-out becoming a hiding place:

| Guard | Defect it prevents |
|---|---|
| A `REPO-LOCAL` name must have **no** `plugins/quick-dev/skills/` counterpart | A drifted mirror relabelling itself repo-local to dodge parity |
| Every `REPO-LOCAL` name must exist on disk | Stale entries silently widening the exemption |
| Repo-local files are still checked for git-trackedness | The exact failure the `.gitignore` comment records — a mirrored skill that passed locally and vanished on a fresh checkout |

`REPO-LOCAL` itself must be tracked. The existing single-path `review-and-merge/README.md`
exception stays as it is; it is not folded into the new manifest, because it is a *file*
exception inside a mirror, not a directory exception.

## 2. Client discovery

`$REPO_ROOT/.claude/notion-dev/clients.txt` — one absolute repo path per line, `#` comments
allowed. Untracked: `.gitignore`'s `.claude/*` already covers it, and `!.claude/skills/`
does not re-include it.

- Explicit paths passed as skill arguments override the file entirely.
- File absent and no arguments → the skill asks for the paths and offers to write the file.
- A listed path that is not a directory, or holds no
  `.claude/notion-dev/notion-dev-issues.md`, is **reported and skipped**, never silently
  dropped.

Untracked is deliberate: the client paths are machine-specific (one is a WSL-mapped Windows
path) and `pure-dev` is a public marketplace repo.

## 3. Procedure

Eight phases. Two orderings are load-bearing and are asserted by the harness: **5 before 6**
(redact before the archive is written) and **8 after 7** (reset only after the merge).

### Phase 1 — Read prior harvests

Read every `docs/feedback/*.md` archive before reading any client log.

This is what makes `decline` a durable decision rather than a per-run coin flip: a signature
that reappears is matched against its prior disposition and rationale, and re-evaluated
against the *new* evidence (higher occurrence count, a newer version range, a different
`Observed`). Without this step a declined item is silently re-triaged from scratch every
harvest, and the rationale written last time is never read.

### Phase 2 — Collect

For each client, parse `## <signature>` sections. Record per section: signature, `Kind`,
`Occurrences`, `First seen` / `Last seen` (timestamp **and** version), `Where`, `Expected`,
`Observed`, `Effect`, `Context`, plus any free-form `Recurrence …` / `Correction …`
subsections, and the client's repo name.

**Group across clients by signature, then confirm or split by reading both `Observed`
fields.** `issue-log` dedups per repo, so the same signature in two logs may be one condition
or two. `mcp-unavailable:notion` is the live example: in one client the server registered and
its tool listing timed out; in the other no `mcp__notion__*` tool was ever registered at all.
Same signature, different conditions.

### Phase 3 — Triage

Every signature ends in exactly **one** of five dispositions. There is no sixth, and
"revisit later" is not one.

| Disposition | Meaning | Requires |
|---|---|---|
| `apply` | Real, plugin-owned, and the improvement is statable in one sentence | The change, in this PR |
| `stale` | Already fixed | The current plugin text that covers it, cited by `file:line` |
| `decline` | Real observation; the remedy is wrong, unjustified, or costs more than it buys | A written rationale |
| `track` | Real and warranted, too large for this PR | A GitHub issue that **exists now**, with its URL |
| `blocked` | Cannot be acted on from here, for a named **external** cause | The cause, and what would unblock it |

These are `session-closeout`'s three states plus the two that are decisions rather than loose
ends. `blocked` carries the same externality bound `scripts/verify-blocked-disposition.sh`
enforces elsewhere: a plugin-internal cause is a tail wearing a label.

Four rules the client data forces, each of which a naive reading gets wrong:

1. **"Not the plugin's bug" ≠ "no plugin change."** The `unexpected:missing-env-local-in-worktree`
   entry says outright that the worktree is created correctly and that gitignored files are
   gitignored by design — *and* that a one-line note in `ticket.md` Phase 2.1 would remove the ambiguity
   cheaply, because the failure looks like a deploy regression right before a merge gate. Every
   host-caused or client-setup-caused entry is evaluated for a documentation fix before being
   dismissed.

2. **An entry's own stated cause is evidence, not a finding.** The `unexpected:dependsOnProperty`
   entry recorded a mechanism ("self-relations are inherently symmetric") that was later
   disproved, and its own correction notes that the drop-and-recreate never took effect.
   Triage re-derives the cause; it does not inherit the entry's conclusion.

3. **An old `First seen` version is a `stale` candidate, never a `stale` verdict.** Confirm by
   reading the current plugin text. Several entries here were recorded against `0.12.2` against a
   plugin now at `0.21.0`, and some of those defects are still present.

4. **A recurrence subsection outranks the original.** `unexpected:cleanup-order` carries three
   appended recurrences, the last of which reports a *second consumer* of the same defect
   (`git.postMergeHooks`) and a wider exposure window than when it was first filed. Triage reads
   the whole section, not its first ten lines.

### Phase 4 — Apply

Every `apply` item becomes a change in `plugins/`. Per this repo's rules:

- **One PR.** Widening it is cheaper than splitting it; "it touches a file this PR wasn't
  already changing" is not a reason to defer.
- **Do not file what you are about to fix.** `track` is for what genuinely cannot land here,
  not for what would be more comfortable in its own PR.
- **Shared behaviour changes in both plugins.** `notion-dev` vendors adapted forks of several
  `quick-dev` skills; when a fix lands in shared behaviour, both copies change and the
  deliberately-differing wording (plugin names, config paths, reviewer defaults) is checked.
- **Version bump exactly once per PR**, on each plugin the PR touches, per the policy in
  `plugins/quick-dev/skills/develop/SKILL.md`.
- **Every `apply` is covered by an assertion** in some `scripts/verify-*.sh` — extending an
  existing standing-invariant harness where one fits, rather than minting a change-scoped one
  with a version floor. Each new assertion is mutation-tested: break the file it guards,
  confirm `FAIL`, restore — with the work committed **first**, so an undo cannot revert it.

### Phase 5 — Redaction gate

**Runs before the archive is written, not as a cleanup after.** `pure-dev` is public and the
client logs do not honour `issue-log`'s own redaction contract in practice. This is measured,
not hypothetical — present in the live logs today:

| Forbidden by `issue-log`, present in a client log | Example |
|---|---|
| Full database / page ids | a full 32-hex database id, and a `collection://` identifier |
| Email addresses | a maintainer's own address |
| Personal names | a workspace named after a person |
| Absolute filesystem paths | a Windows checkout path |
| URLs | the `collection://` reference above |

The gate applies `issue-log`'s **Forbidden, without exception** list verbatim — ticket titles
and bodies, PR titles/descriptions/contents, diffs and code, Notion user ids, emails, personal
names, full database ids, full page ids, absolute paths, URLs of any kind.

The forbidden list is the gate, not the per-field whitelist. So these are **kept**: the
signature, `Kind`, occurrence counts, timestamps and versions, ticket keys (`STO-77` —
explicitly permitted in `Where`), truncated database ids (`db=…327627`), client repo names
(already cited in `ticket.md`), bare PR numbers, and commit shas. A full database id is
truncated to its last six characters rather than removed, so it still groups.

If any client entry text cannot be redacted without destroying the finding, the finding is
**paraphrased in the archive** and the original is not reproduced.

### Phase 6 — Archive

`docs/feedback/YYYY-MM-DD-harvest.md`, committed with the PR. On a same-day collision, suffix
`-2`, `-3`.

One `##` section per triaged signature, holding: the signature; every client that observed it
with that client's occurrence count and version range; the redacted entry text; the
disposition; the rationale; and the resulting change — `file:line`, commit sha, or issue URL.

The archive is the durable record. Once the client log is reset it is the only place the
occurrence counts, first-seen versions, and rejection rationales still exist.

### Phase 7 — PR and merge

Hand the branch to the existing `review-and-merge` skill rather than reimplementing a review
or merge loop. Its **final sweep** is where anything the harvest was tempted to file as
`track` gets taken back into the PR instead; its `--pre-merge-check` hook is where
`session-closeout`'s completion pass runs.

The PR body names every disposition and its count, so the merge record says what was decided
about entries that produced no diff — the `stale` and `decline` items are otherwise invisible
in a diff-shaped review.

### Phase 8 — Reset

**After the merge. Never before.** A reset before merge destroys the only copy of feedback for
a PR that might not land.

Removal is surgical, matched on **signature and occurrence count as harvested**:

1. Locate `## <signature>`; confirm its `**Occurrences**` integer and `**Last seen**` line
   still match what Phase 2 recorded.
2. Match → delete the section, from its `##` heading to the line before the next `##` heading
   or EOF.
3. Mismatch → **leave it in place and report it.** The client appended to or incremented that
   signature since the harvest, and the new evidence has not been triaged.
4. All five dispositions are removed, `decline` and `track` included. Their durable home is the
   archive and the issue; leaving them means re-triaging them next harvest.
5. The file header is never deleted, and the file itself is never deleted or truncated.

`.claude/notion-dev/` is self-gitignored in the client repo (`printf '*\n'`), so the issue log
is untracked there: reset is a plain file edit, with no commit and no push into a client repo.

### Closeout

`session-closeout` runs before any "done", per this repo's zero-tails rule. Its workspace pass
additionally confirms that the reset ran for **every** client the harvest read — a harvest that
merged its PR and left a client log untouched has silently guaranteed the next harvest will
re-triage everything it just decided.

---

## 4. Verification

New harness `scripts/verify-feedback-harvest.sh` — standing-invariant style, no version floor,
discovered by `.github/workflows/verify.yml`'s glob with no workflow edit. It asserts
mechanisms, not prose:

- All five dispositions appear in the skill's disposition table, and `blocked` carries the
  externality bound.
- The redaction gate is ordered **before** the archive write (`assert_order`).
- The reset is ordered **after** the merge (`assert_order`).
- Removal is signature-and-occurrence matched, and the skill states that truncation is never
  used (`assert_has` on the mechanism, `assert_lacks` on a truncate instruction).
- Phase 1's prior-archive read is present, since it is what makes `decline` durable.
- The mismatch branch of the reset leaves the section in place rather than force-removing it.

`scripts/verify-mirror.sh` gains the `REPO-LOCAL` rules from §1, including the three guards.
It remains a standing invariant.

Both are covered by `verify-assertions.sh`'s existing A3 no-opt-out check automatically, since
it globs `scripts/verify-*.sh`.

## 5. Accepted limitations

- **A concurrent increment is lost.** If a client run increments a harvested signature's
  `Occurrences` between Phase 2 and Phase 8, the mismatch branch fires and the section survives —
  correct. If it increments *and* the harvest re-reads a matching count, the increment is
  dropped. This mirrors `issue-log`'s own accepted read-modify-write race: the log is
  diagnostics, not accounting.
- **The harvest cannot see runs that died.** `issue-log`'s header states it: a killed run leaves
  nothing behind to record its own death, so a short log is not evidence of a healthy client. The
  archive inherits that limitation and must not be read as a complete account.
- **Reset loses cumulative occurrence history for re-declined items.** Phase 1's prior-archive
  read mitigates this by carrying the previous count and rationale forward, but a signature that
  reappears starts counting from 1 in the client log.
