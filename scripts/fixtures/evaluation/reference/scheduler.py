"""Reference implementation of the evaluation fixture's scheduler.

Generic and synthetic. It exists so the hidden oracle can be shown to pass against
correct code and fail against the seeded defects, which is the only thing that makes
the fixture evidence rather than decoration.

Deterministic on purpose: a round-based scheduler rather than real threads, so the
concurrency invariant is checked identically on every host and never flakes.
"""


class ConfigError(ValueError):
    """Raised for a configuration that cannot be honoured as written."""


def validate_config(config):
    """Normalize a walker configuration, or refuse it.

    A limit that cannot be enforced is not a limit. Anything below 1 is rejected here
    rather than reinterpreted, because silently promoting it to "unlimited" removes the
    guarantee the caller asked for while reporting success.
    """
    if not isinstance(config, dict):
        raise ConfigError("configuration must be a mapping")
    name = config.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("name must be a non-empty string")
    limit = config.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ConfigError("limit must be an integer")
    if limit < 1:
        raise ConfigError("limit must be at least 1")
    retries = config.get("retries", 0)
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        raise ConfigError("retries must be a non-negative integer")
    return {"name": name.strip(), "limit": limit, "retries": retries}


class Walker:
    """Breadth-first graph walk with a global cap on concurrently running nodes."""

    def __init__(self, graph, limit):
        self.graph = graph
        self.limit = validate_config({"name": "walk", "limit": limit})["limit"]

    def run(self, start):
        pending, in_flight, seen = [start], {}, {start}
        order, peak = [], 0
        while pending or in_flight:
            # Capacity is what is left of the limit, not the limit itself: nodes still
            # running occupy it. Recomputing it as the whole limit each round is the
            # seeded defect, and it is invisible until a node outlives one round.
            capacity = self.limit - len(in_flight)
            while pending and capacity > 0:
                node = pending.pop(0)
                order.append(node)
                in_flight[node] = max(1, self.graph[node].get("cost", 1))
                capacity -= 1
            peak = max(peak, len(in_flight))
            for node in list(in_flight):
                in_flight[node] -= 1
                if in_flight[node] <= 0:
                    del in_flight[node]
                    for child in self.graph[node].get("next", ()):
                        if child not in seen:
                            seen.add(child)
                            pending.append(child)
        return {"order": order, "max_in_flight": peak, "visited": len(order)}


def resolve(name, version, registry, cache):
    """Look a versioned entry up in `registry`, memoized in `cache`.

    The cache key is the whole identity. Keying on the name alone makes two different
    versions the same entry, and the wrong answer is returned from cache rather than
    raised, so nothing downstream can notice.
    """
    key = (name, version)
    if key in cache:
        return cache[key]
    value = registry[key]
    cache[key] = value
    return value


def resolve_all(requests, registry, cache=None):
    """Resolve a request list, reporting how many registry lookups it really took."""
    cache = {} if cache is None else cache
    before = len(cache)
    values = [resolve(name, version, registry, cache) for name, version in requests]
    return {"values": values, "registry_lookups": len(cache) - before,
            "requests": len(requests)}
