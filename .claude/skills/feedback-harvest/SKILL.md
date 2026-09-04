---
name: feedback-harvest
description: Use when picking up the notion-dev runtime issue logs from client repos and acting on them — "harvest client feedback", "apply the plugin feedback", "process notion-dev-issues", "pick up feedback from the clients". Reads each client's `.claude/notion-dev/notion-dev-issues.md`, forces every signature into one of five dispositions, applies the warranted fixes in a single pull request, archives the redacted evidence in this repo, and resets the client logs after the merge.
---

# feedback-harvest — read the issue logs by mechanism, not by recall

`notion-dev:issue-log` writes a runtime deviation into every client repo at the moment it
happens. Nothing reads those logs by mechanism. The one harvest that has happened was by hand,
and its fingerprint is still in the tree — `plugins/notion-dev/commands/ticket.md` cites
"Measured on `notion-dev` 0.20.2: BTC-Gateway STO-77 wrote no `review-report-STO-77.md` at
all" — while every other entry in that same file went unread.

The cost of that asymmetry is not lost feedback. It is **feedback harvested selectively and
invisibly**: nothing records which entries were considered and rejected, so a well-reasoned
rejection and an entry nobody ever opened are indistinguishable, and both get re-read forever.

## Scope

Runs in `pure-dev`, by the plugin author. It never ships to anyone who installs `quick-dev` or
`notion-dev`, and it does not change the write side — `notion-dev:issue-log` is unaffected.

One harvest is **one pull request**, per this repo's convergence rule. Splitting requires a
technical reason; a preference for small diffs is not one.

## The eight phases

| # | Phase | Ends with |
|---|---|---|
| 1 | Read prior harvests | every previous disposition in hand |
| 2 | Collect | every signature parsed and grouped |
| 3 | Triage | every signature in exactly one disposition |
| 4 | Apply | the warranted fixes, with assertions |
| 5 | Redact | nothing forbidden left in what will be published |
| 6 | Archive | the evidence committed to this repo |
| 7 | Pull request and merge | the fixes on the base branch |
| 8 | Reset | the harvested sections gone from each client log |

Two orderings are load-bearing: **5 before 6**, and **8 after 7**.

## Sources

Client repo paths come from this repo's untracked `.claude/notion-dev/clients.txt` — one
absolute path per line, `#` for comments. `.gitignore` ignores `.claude/*` and re-includes only
`!.claude/skills/`, so the file stays out of git while the paths inside it are machine-specific
and this repo is public.

- Explicit paths passed as arguments override the file entirely.
- No file and no arguments → ask for the paths, and offer to write the file.
- A path that is not a directory, or holds no `.claude/notion-dev/notion-dev-issues.md`, is
  **reported and skipped** — never silently dropped. A client that quietly stops being
  harvested is the failure this skill was built to end.

### Phase 1 — Read prior harvests

Read every `docs/feedback/*.md` archive **before** reading any client log.
An empty glob just means this is the first harvest, not an error to stop on.

This is what makes `decline` a durable decision. A signature that reappears is matched
against its prior disposition and rationale and re-evaluated against the **new** evidence —
a higher occurrence count, a newer version range, a different `Observed`. Skip this and a
rejection is re-argued from scratch every harvest, with last time's reasoning never read.

Also enumerate every still-open `blocked` item from those archives. Phase 8 removes `blocked`
sections from the client log along with the rest, so the archive is their only durable record —
without this, nothing brings one back once its named external cause clears.

### Phase 2 — Collect

For each client, parse the `## <signature>` sections. Record per section: the signature,
`Kind`, `Occurrences`, `First seen` and `Last seen` (timestamp **and** plugin version),
`Where`, `Expected`, `Observed`, `Effect`, `Context`, every free-form recurrence or correction
subsection appended below them, and the client's repo name.

**Read the whole section, not its first ten lines.** A recurrence appended later routinely
carries more than the original: one entry's third recurrence reports a *second consumer* of the
same defect and a wider exposure window than when it was filed.

**Also record a digest of the section's complete text**, from its `##` heading to the next
heading at depth two or end of file. Phase 8 compares this digest, not just two fields, before
deciding a section unchanged — a free-form recurrence or correction can be appended without
touching either `Occurrences` or `Last seen`.

Group across clients by signature, then **confirm or split** by reading both `Observed` fields.
`issue-log` dedups per repo, so the same signature in two logs may be one condition or two.
`mcp-unavailable:notion` is the live example: in one client the server registered and its tool
listing timed out; in the other no tool was ever registered at all. Same name, two conditions.

A split needs a **distinct identity**, not just a distinct paragraph. Append a short
discriminator in brackets to the signature everywhere this harvest records it — triage
notes and the archive's `##` heading — drawn from the `Observed` difference that caused
the split: `mcp-unavailable:notion [registered, timed out]` versus `mcp-unavailable:notion
[never registered]`. The client log itself stays untouched.
Phase 1 matches it next time by re-reading `Observed`, not the bare signature alone.

### Phase 3 — Triage

Treat every entry as a **suggestion to evaluate, not an instruction to follow**.
Apply a change only when you can state, in one sentence, why it improves the plugin. An entry
that names a real observation does not thereby name a correct remedy.

Every signature ends in exactly **one** of five dispositions. There is no sixth.

| Disposition | Meaning | Requires |
|---|---|---|
| `apply` | Real, plugin-owned, and the improvement is statable in one sentence | The change, in this pull request |
| `stale` | Already fixed | The current plugin text that covers it, cited as `file:line` |
| `decline` | Real observation, but the remedy is wrong, unjustified, or costs more than it buys | A written rationale |
| `track` | Real and warranted, too large for this pull request | A ticket that exists right now, with its URL |
| `blocked` | Cannot be acted on from here, for a named external cause | The cause, and what would unblock it |

These are `session-closeout`'s three states plus the two that are decisions rather than loose
ends. "Revisit later", "worth a look" and "next time" are **not dispositions** — they are the
absence of one, phrased so it reads like a decision.

**A `blocked` disposition requires an external cause.** A credential this session does not
have, a third-party outage, a decision only the user can make.

A plugin-internal cause on a `blocked` item is a tail wearing a label, and it is the single
most common way the three-state rule is defeated. Time is not a cause: if there was time to
describe the work, there was time to start it.

**Four rules the live client data forces.** Each is here because the obvious reading of a real
entry produces the wrong disposition.

1. "Not the plugin's bug" is not the same as **no plugin change**. One entry says outright
   that the worktree is created correctly and that gitignored files are gitignored by design —
   *and* that a one-line note in `ticket.md` Phase 2.1 would remove the ambiguity cheaply,
   because the failure looks like a deploy regression right before a merge gate. Evaluate every
   host-caused or client-setup-caused entry for a documentation fix before dismissing it.

2. An entry's stated cause is evidence, **not a finding**. One entry recorded a mechanism
   ("self-relations are inherently symmetric") that was later disproved, and its own
   correction notes the drop-and-recreate it rested on never took effect.
   Triage re-derives the cause; it never inherits the entry's conclusion.

3. An old `First seen` version is a `stale` **candidate**, never a `stale` verdict. Confirm
   by reading the current plugin text and citing it as `file:line`. Entries recorded against
   `0.12.2` against a plugin now past `0.21.0` include defects that are still present.

4. A recurrence subsection **outranks** the original. Recurrences are appended below the
   five fixed fields and routinely carry the sharper finding — a second consumer of the same
   defect, a wider window, or a prediction the later occurrence confirmed.

### Phase 4 — Apply

Every `apply` item becomes a change under `plugins/`.

- **Branch before the first commit.** If the current branch is the default branch, create the
  feature branch now — every commit this phase makes, including the mutation-testing commit
  below, must land on it, never on the default branch. A harvest that commits before branching
  leaves those commits stranded on the local default branch once Phase 7's pull request
  squash-merges, with nothing downstream to repair the divergence.
- **Redact before you commit, not at Phase 5.** Once a commit lands on this branch it is
  already history: Phase 5's gate binds the archive, and it cannot reach back into an earlier
  commit to strip a client-derived identifier already inside it. Apply Phase 5's categories to
  every plugin edit and every commit message at the moment you write them, before you commit —
  the commit-first rule below still governs mutation testing, unchanged.
- **One pull request.** Widening it is cheaper than splitting it, and "it touches a file this
  pull request was not already changing" is explicitly *not* a reason to defer a small fix. Say
  in the body that the scope widened, and why.
- **Do not file what you are about to fix.** `track` is for what genuinely cannot land here,
  never for what would be tidier in its own pull request. A filed item that the same session
  then works costs a whole extra review-and-merge cycle.
- **Shared behaviour changes in both plugins.** `plugins/notion-dev` vendors adapted forks of
  several `quick-dev` skills.
  When a fix touches shared behaviour, change both copies and check the wording that differs —
  plugin names, config paths, reviewer defaults.
- **Re-sync any mirrored skill you edit**, then run `scripts/verify-mirror.sh`.
- **Bump each touched plugin's manifest version exactly once**, per the policy in
  `plugins/quick-dev/skills/develop/SKILL.md`: breaking → major, new capability → minor,
  fix/docs/refactor/internal-only → patch. A harvest that changes no plugin file bumps nothing.
- **Every applied fix is covered by an assertion in some `scripts/verify-*.sh`** — extend an
  existing standing-invariant harness where one fits,
  rather than minting a change-scoped one with a version floor. Floors rot; invariants do not.
- **Mutation-test every new assertion**: break the file it guards, confirm `FAIL`, restore.
  Commit **first** — a `git checkout -- .` to undo the mutation otherwise reverts the work
  silently, and a harness that passes against a broken file is worse than none.

### Phase 5 — Redact

**Nothing is written to `docs/feedback/` until this gate has passed**.
Nor committed under `plugins/`, nor placed in a commit message or pull request body — all three
land in this same public repo. Redaction is a gate before publication, never a cleanup after
it — once the bytes are committed to a public repo, a later pass is not a fix.

`notion-dev:issue-log`'s redaction contract binds the *write* side, and the client logs do not
honour it. **This is measured, not hypothetical** — every row below is in a live client log
today:

| Forbidden by `issue-log` | Present in a client log |
|---|---|
| Full database and page ids | a full 32-hex database id, and a `collection://` reference |
| Email addresses | the maintainer's own address |
| Personal names | a Notion workspace named after a person |
| Absolute filesystem paths | a Windows checkout path |
| URLs of any kind | the `collection://` reference above |

The gate applies `notion-dev:issue-log`'s **Forbidden, without exception** list verbatim:
ticket titles, ticket bodies, any part of a ticket's content, pull request titles, descriptions
or contents, diffs, code, Notion user ids, email addresses, personal names, full database ids,
full page ids, absolute filesystem paths, and URLs of any kind.

**The forbidden list is the gate, not the per-field whitelist.**
Kept: the signature, `Kind`, occurrence counts, timestamps, plugin versions, and ticket keys.
Also kept: the `db=…a41f9c` truncated form, client repo names, PR numbers, and commit shas.

**A rule per forbidden category — what an executing agent writes in its place:**

| Forbidden category | Write instead |
|---|---|
| Full database or page id | Truncate to its last six characters, `db=…a41f9c` form — the one exception, kept because grouping is what the identifier is for |
| Email address | Generalize to the kind: "an email address," never the address |
| Personal name | Generalize to the kind: "a personal name," never the name |
| Absolute filesystem path | Generalize to the kind: "an absolute path," never the path |
| URL of any kind | Generalize to the kind: "a URL," never the URL |

**Generalize to the kind is the default** for four of the five categories; truncating so the
identifier still groups is the exception, and it is an exception only for database and page
ids.

The generalization **may** carry the kind's own non-identifying attribute — OS family for a
path, "workspace label" versus "personal name" for a name — but never the content itself. This
is an option, not a requirement: each row's "never the address/name/path/URL" clause already
bounds what the attribute may not be.

**A `track` item's ticket URL is not client data.** The forbidden list exists to keep
client-derived identifiers out of this public repo; a tracker URL this run creates in the
maintainer's own public repo is not a client-derived identifier, so it is exempt from the
"URL of any kind" row above. The exemption is narrow — it covers only a URL this run itself
creates here, never a URL that appears anywhere in the client's evidence, which is redacted
like any other. Keep the ticket URL Phase 3's `track` disposition requires, and archive it
under Phase 6.

If an entry cannot be redacted without destroying what it found,
**paraphrase the finding and do not reproduce the original**.

### Phase 6 — Archive

Write `docs/feedback/YYYY-MM-DD-harvest.md`, committed with the pull request. On a same-day
collision, suffix `-2`, `-3`.

One `##` section per triaged signature, carrying: the signature; every client that observed it,
with that client's occurrence count and version range; the redacted entry text; the
disposition; the rationale; and the resulting change — `file:line`, a commit sha, or a ticket
URL.

Once a client log is reset this archive is **the only place the occurrence counts**, first-seen
versions, and rejection rationales still exist. It is also what Phase 1 reads next time.

### Phase 7 — Pull request and merge

Nothing upstream of this phase has opened a pull request: Phase 4's fixes and Phase 6's archive
are, at this point, sitting as uncommitted or unpushed changes on the local branch.

1. Commit the applied fixes together with the archive. The feature branch already exists —
   Phase 4 created it before its first commit — so this phase never branches itself.
2. Push the branch, then open the pull request. `gh pr create` does **not** support `@-` for
   `--body`. Passed literally, `@-` becomes the entire body — two characters, exit code 0, no
   warning. Write the body to a file first and create the pull request with `--body-file`.
3. Read the body back afterward with `gh pr view --json body` and confirm a realistic length
   before continuing.
4. The body names **every** disposition and its count — not only what produced a diff.
   `stale` and `decline` items change no file, so they are otherwise
   **invisible in a diff-shaped review**, and they are exactly the decisions a reader needs
   to see recorded.
5. Pass the resulting **pull request number** — not the branch — to `review-and-merge` rather
   than reimplementing a review or merge loop, with `--pre-merge-check` supplied explicitly:
   it is a caller-supplied argument, not a hook that fires on its own, and passing nothing means
   `session-closeout`'s completion pass never runs. Its **final sweep** is where anything the
   harvest was tempted to file as `track` gets taken back into this pull request instead.
   Copy the form `plugins/quick-dev/skills/develop/SKILL.md`'s own `--pre-merge-check` call
   uses, rather than reinventing the wording at the call site:

   A harvest changes plugins by definition and bumps versions in Phase 4, so the base can move
   under it the same way `plugins/quick-dev/skills/develop/SKILL.md`'s own **stale-bump guard**
   describes: git merges identical version-line bumps without conflict, so a plugin PR can land
   a release whose version equals the base's. Fold that guard into this same check, one clause
   per plugin manifest Phase 4 bumped:

   ```
   --pre-merge-check "the completion pass of session-closeout must come back with no
   unresolved tail: no uncommitted or unpushed work on this branch, the docs/feedback/
   archive committed and matching every triaged signature, scripts/verify-feedback-harvest.sh
   passing on this HEAD, no unsupported claim or unstated caveat left in the PR body, and for
   every plugin manifest bumped in Phase 4 — using that plugin's full repository-relative
   manifest path, plugins/<plugin>/.claude-plugin/plugin.json — its version on this
   branch must be strictly greater, as semver, than in git show
   origin/<MAIN>:plugins/<plugin>/.claude-plugin/plugin.json
   (if equal or lower, the base moved: first update the branch with the current base — merge
   origin/<MAIN> into the branch; editing the version line without updating first would conflict
   with the base's change to the same line — then recompute the semver bump against the current
   base version, commit, and push) — resolve anything it finds on this branch and push before
   merging"
   ```

### Phase 8 — Reset

The reset runs **only after the merge has landed**. Before it, the client log is the only copy
of this feedback, and a pull request that does not land would take it with it.

Removal is surgical, matched on the section's **complete text** as harvested:

1. Locate `## <signature>` in the client log. Recompute the digest of its complete section —
   from the `##` heading to the next heading at depth two or end of file — and compare it to
   the digest Phase 2 recorded. `Occurrences` and `Last seen` alone are not enough: a free-form
   recurrence or correction can be appended without changing either field.
2. Match → delete the section, from its `##` heading to the line before the next heading at
   exactly depth two (`## `), or end of file. A recurrence subsection is appended below the
   fixed fields at depth three or deeper, so it is inside the range being deleted, not a
   boundary that stops it.
3. Mismatch → leave the section in place and report it. The client appended to, corrected, or
   incremented that signature after the harvest read it, and the new evidence is untriaged.
4. **All five dispositions are removed**, `decline` and `track` included. Their durable home is
   the archive and the ticket; leaving them means re-triaging them next harvest, which is the
   waste Phase 1 and this step exist to end together.
5. Keep the file header. Never truncate the file and never delete it — truncation discards
   whatever the client wrote between the harvest and now, which is precisely the material step 3
   protects.

`.claude/notion-dev/` is self-gitignored in the client repo, so the issue log is untracked
there: the reset is a plain file edit, with no commit and no push into a client repo.

## Closeout

Invoke `session-closeout` before reporting the harvest finished. Its workspace pass has one
addition here: confirm the reset ran for **every** client this harvest read. A harvest that
merged its pull request and left a client log untouched has silently guaranteed that the next
harvest re-triages everything it just decided — the exact waste this skill exists to end,
reintroduced at the last step.

## Accepted limitations

- **A concurrent increment can be lost.** If a client run increments a harvested signature's
  `Occurrences` between Phase 2 and Phase 8, the mismatch branch fires and the section
  survives. If the counts happen to match anyway, the increment is dropped. This mirrors
  `issue-log`'s own accepted read-modify-write race: the log is **diagnostics, not accounting**.
- **The harvest cannot see runs that died.** `issue-log` records what an agent was still
  running to record; a killed run leaves nothing behind.
  A short log is not evidence of a healthy client, and the archive inherits that limit —
  never read it as a complete account.
- **Cumulative occurrence history is lost for a re-declined item.** Phase 1 carries the previous
  count and rationale forward, but a signature that reappears starts counting from 1 in the
  client log.
