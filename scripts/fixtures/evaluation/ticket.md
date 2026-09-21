# EVAL-1 — Bounded graph walk with a memoized registry

## Background

The walker expands a dependency graph. Downstream callers size their own resources
from the configured concurrency cap, so a walk that exceeds it is a correctness bug
rather than a performance one.

## Prerequisites

- [x] The cap semantics were confirmed with the calling team: the cap is a **global**
  maximum of nodes running at once, not a per-round admission quota.

## Acceptance criteria

- [ ] AC1: A walk never has more than `limit` nodes running at the same time, for any
  graph, including one whose nodes take more than one round to finish.
- [ ] AC2: The registry cache distinguishes two versions of the same name; resolving
  `("parser", "2")` after `("parser", "1")` returns the second version's value.
- [x] AC3: `validate_config` refuses a configuration it cannot honour, including a
  `limit` below 1, and returns a normalized mapping otherwise.
- [ ] AC4: Every reachable node is visited exactly once.

## Notes

Any figure quoted in the pull request body about lookups avoided must be derived from
the fixture workload rather than estimated; an undeclared estimate is a defect.

The `retries` value is part of the accepted configuration surface: a negative value is
invalid and must be refused with the same error type as the other fields.
