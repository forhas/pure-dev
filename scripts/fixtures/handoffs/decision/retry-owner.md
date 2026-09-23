---
title: Retry ownership
status: stable
---
# Retry ownership
The caller owns retries. Rejected historical approach: the shared helper must not retry
because its sibling caller already retries. Both the primary and sibling failure paths
must sanitize sensitive values while preserving the public error code.
