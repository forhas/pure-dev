#!/usr/bin/env python3
"""Read-only dependency diagnostics. Live host skill names are authoritative.

The caller supplies the current host's catalog, never one reconstructed from config.
Settings explain absence; this helper neither installs nor enables plugins. Exit 0:
available, 1: required skills absent, 2: invalid/unreadable evidence.
"""
import argparse
import json
import os
from pathlib import Path
import sys


REQUIRED = {
    "superpowers": ("superpowers", ["superpowers:writing-plans",
                    "superpowers:subagent-driven-development", "superpowers:receiving-code-review"]),
    "featureDev": ("feature-dev", ["feature-dev:feature-dev"]),
}


def read_object(path):
    path = Path(path)
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object: " + str(path))
    return value


def check(project, live_skills, mode="ticket", settings=None):
    if not isinstance(live_skills, list) or not all(isinstance(s, str) and s for s in live_skills):
        raise ValueError("live skills must be an array of actual host skill names")
    if mode not in {"lean", "ticket", "review"}:
        raise ValueError("mode must be lean, ticket or review")
    # Lean needs neither build-flow plugin, so it must not be gated on evidence about
    # them. Reading the config and settings first meant a malformed or legacy
    # `dependencies`/`enabledPlugins` entry — irrelevant to this path — raised and exited
    # 2, blocking the new DEFAULT workflow for a reason that has nothing to do with it.
    # The result is the one the per-key loop already produced for lean: no plugins, and
    # `passed` true over an empty set.
    if mode == "lean":
        return {"passed": True, "plugins": {}, "settings_are_diagnostic": True,
                "authority": "current host skills; file settings do not model managed or session overrides"}
    project = Path(project).resolve()
    cache = read_object(project / ".claude/notion-dev.config.json").get("dependencies", {})
    if not isinstance(cache, dict):
        raise ValueError("dependencies must be an object")
    if settings is None:
        config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
        settings = [config_dir / "settings.json", project / ".claude/settings.json",
                    project / ".claude/settings.local.json"]
    effective = {}
    for path in settings:
        path = Path(path).resolve()
        values = read_object(path).get("enabledPlugins", {})
        if not isinstance(values, dict):
            raise ValueError("enabledPlugins must be an object: " + str(path))
        for plugin, enabled in values.items():
            if plugin.split("@", 1)[0] not in {"superpowers", "feature-dev"}:
                continue
            if not isinstance(enabled, bool):
                raise ValueError("enabledPlugins value must be boolean: " + str(path) + " / " + plugin)
            effective[plugin] = {"plugin": plugin, "enabled": enabled, "path": str(path)}
    plugins = {}
    for key, (name, skills) in REQUIRED.items():
        if mode == "review":
            if key != "superpowers":
                continue
            skills = ["superpowers:receiving-code-review"]
        missing = [skill for skill in skills if skill not in live_skills]
        entries = [entry for identifier, entry in effective.items() if identifier.split("@", 1)[0] == name]
        disabled = bool(entries) and all(not entry["enabled"] for entry in entries)
        available = not missing
        status = "available" if available else "disabled" if disabled else "unavailable"
        remedy = "none"
        if disabled:
            remedy = ("Ask the user to enable the intended plugin in the listed settings source; "
                      "reload plugins and re-check the live catalog. Do not reinstall over a false override.")
        elif missing:
            remedy = ("Inspect /plugin installed status and load errors; reload an installed plugin. "
                      "Install only when confirmed not installed. Check local/project enabledPlugins and managed policy.")
        plugins[key] = {"status": status, "available": available, "missing_skills": missing,
                        "cached": cache.get(key), "cache_mismatch": cache.get(key) is not available,
                        "settings": entries, "settings_mismatch": available and disabled,
                        "remedy": remedy}
    return {"passed": all(row["available"] for row in plugins.values()), "plugins": plugins,
            "settings_are_diagnostic": True,
            "authority": "current host skills; file settings do not model managed or session overrides"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--live-skills", required=True)
    parser.add_argument("--mode", choices=["lean", "ticket", "review"], default="ticket")
    parser.add_argument("--settings", action="append", help="actual settings files, in low-to-high precedence order")
    args = parser.parse_args()
    live = json.loads(Path(args.live_skills).read_text(encoding="utf-8-sig"))
    result = check(args.project, live, args.mode, args.settings)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
