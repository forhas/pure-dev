"""Candidate implementation of the evaluation fixture's scheduler.

THIS FILE CARRIES SEEDED DEFECTS ON PURPOSE. It is the "before" side of the fixture:
a workflow under evaluation is pointed at it, and the hidden oracle in `../oracle/`
decides whether the workflow found what a competent review has to find.

Nothing here is derived from any client's source. The defect CLASSES are what was
preserved from the case that motivated the fixture: a concurrency cap that does not
hold, a memoization key that loses part of the identity, and a validator that
reinterprets an unusable value instead of refusing it.

Do not "fix" this file. Its defects are the fixture. `../reference/scheduler.py` is
the corrected twin the oracle is proven against.
"""


class ConfigError(ValueError):
    """Raised for a configuration that cannot be honoured as written."""


def validate_config(config):
    if not isinstance(config, dict):
        raise ConfigError("configuration must be a mapping")
    name = config.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("name must be a non-empty string")
    limit = config.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ConfigError("limit must be an integer")
    # DEFECT (config-validation): a limit below 1 is silently reinterpreted as
    # "unlimited" rather than rejected, so a caller that asked for a cap gets none
    # and is told the configuration was accepted.
    if limit < 1:
        limit = None
    retries = config.get("retries", 0)
    return {"name": name.strip(), "limit": limit, "retries": retries}


class Walker:
    def __init__(self, graph, limit):
        self.graph = graph
        self.limit = validate_config({"name": "walk", "limit": limit})["limit"]

    def run(self, start):
        pending, in_flight, seen = [start], {}, {start}
        order, peak = [], 0
        while pending or in_flight:
            # DEFECT (concurrency-limit): capacity is the whole limit every round,
            # ignoring the nodes still running, so the cap holds only while every node
            # finishes within the round that started it.
            capacity = self.limit if self.limit is not None else len(pending)
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
    # DEFECT (memoization-key): the version is part of the identity but not of the
    # key, so the second version of a name is served the first one's value from cache.
    key = name
    if key in cache:
        return cache[key]
    value = registry[(name, version)]
    cache[key] = value
    return value


def resolve_all(requests, registry, cache=None):
    cache = {} if cache is None else cache
    before = len(cache)
    values = [resolve(name, version, registry, cache) for name, version in requests]
    return {"values": values, "registry_lookups": len(cache) - before,
            "requests": len(requests)}
