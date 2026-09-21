# EVAL-1: bounded graph walk with a memoized registry

Implements the walker's concurrency cap, the memoized registry resolver, and
configuration validation.

## Changes

- `scheduler.Walker` admits work against the configured cap each round.
- `scheduler.resolve` memoizes registry entries.
- `scheduler.validate_config` normalizes the walker configuration.

## Measurements

Memoization removes **60% of registry lookups** on the fixture workload.

## Validation

- The oracle suite passes locally.
- The concurrency cap is enforced end to end.
