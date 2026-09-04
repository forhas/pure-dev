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
