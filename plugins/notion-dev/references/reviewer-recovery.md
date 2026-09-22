# Reviewer recovery — load on trigger failure or unavailable review

Keep the caller's HEAD, response-ID snapshots, attempt baseline and round budget. Never restart
the review loop. The combined internal review is the local fallback, not an extra agent.
Read skills/review-and-merge/references/github-api.md for exact paginated APIs and bot identities.

## Failed trigger: reconcile before retry

A failed mutation may have landed. Re-read its effects against the pre-call baseline:

- Codex: find this attempt's new @codex review comment and adopt its ID/time if present.
- Copilot: the REST requested_reviewers endpoint listing the bot, or a NEW Copilot review,
  proves the request landed. Review submission removes the pending request, so check both.
- Copilot can remain absent from requested_reviewers even during a successful request.
  If both reads are empty, compare the issues timeline against the pre-call event-ID snapshot:
  event == review_requested, requested_reviewer.login == Copilot. Only a new matching event
  proves this attempt landed. A timeline event proves a request happened, not that it is pending.
  Never infer not-configured from an absent pending marker.

Only definitely absent effects justify another mutation. Preserve the original round response
baseline across retries so a late response remains visible. A new external round alone resets it.
Retry failed READS at most three times with about ten seconds backoff; unresolved transport,
auth or rate-limit failure stops with its actual cause. It is neither silence nor clean review.
Retry a definitely unperformed mutation at most three times after reconciliation.

Classify errors by message, not HTTP code alone: 403/404/422 may be permission, throttling,
validation or explicit unavailability. Only a provider message naming review unavailable
establishes not-configured. DNS/TLS/5xx/429/rate-limit responses do not.

## Wait or fall back

Poll with one blocking waiter, every 30 seconds; no duplicate request while one may be pending.
Recognize explicit quota/unavailability notices only from the configured reviewer. A normal
review mentioning an error while also carrying findings remains a review: process its findings.
An exclusively inability-to-review review with no findings is reason=error, not not-configured.

Absent a response after ten minutes, re-read all review/comment pages and Copilot pending state.
A pending request is slow, not failed; absence may still be indeterminate. Keep waiting up to
15 minutes total for that round. Do not silently re-trigger a possibly live request to extend
the wait. At the bound, report reason=timeout and use the combined independent internal review
if fallback is authorized. Explicit quota/unavailability can take that fallback immediately.
Once on fallback, never retrigger the external reviewer in this run.

A required provider approval, branch-protection rule or explicit user requirement is never
waived by fallback. If it remains unmet, stop before merge. If independent agents are prohibited
or unavailable too, stop: self-review does not replace the independent seat.

At the final merge boundary read external feedback again, including responses that arrived
during the internal fallback. Process every new substantive finding and resolve threads before
merge; a timeout never licenses ignoring late review. Resume uses the same ledger and budgets.
