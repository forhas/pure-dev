"""Publish one notion-dev tag after CI; standard library, Python 3.8+.

CI owns authorization (main push + all required jobs). This helper binds the
version to the tested SHA, never the current tip of main. No force pushes.
"""
import argparse
import json
import re
import subprocess


MANIFEST = "plugins/notion-dev/.claude-plugin/plugin.json"


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True,
                          encoding="utf-8").stdout.strip()


def version(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("expected a full commit SHA")
    data = json.loads(git("show", sha + ":" + MANIFEST))
    value = data.get("version", "")
    if data.get("name") != "notion-dev" or not isinstance(value, str) or not re.fullmatch(
            r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value):
        raise ValueError("expected notion-dev with a numeric major.minor.patch version")
    return value


def remote_target(tag):
    ref = "refs/tags/" + tag
    refs = dict(line.split()[::-1] for line in
                git("ls-remote", "--tags", "origin", ref, ref + "^{}").splitlines())
    return refs.get(ref + "^{}", refs.get(ref))


def publish(sha, before):
    current, previous = version(sha), version(before)
    git("merge-base", "--is-ancestor", before, sha)
    if git("rev-parse", "HEAD") != sha:
        raise ValueError("checkout must be the exact tested commit")
    if current == previous:
        if git("diff", "--name-only", before, sha, "--", "plugins/notion-dev"):
            raise ValueError("notion-dev changed without a version bump")
        return "No notion-dev version change; nothing to tag."
    if tuple(map(int, current.split("."))) <= tuple(map(int, previous.split("."))):
        raise ValueError("release version must increase")
    tag = "notion-dev-v" + current
    existing = remote_target(tag)
    if existing is not None:
        if existing != sha:
            raise ValueError(tag + " already points elsewhere; refusing to move it")
        return tag + " already points to " + sha
    # A failed push can leave a local tag. Reuse only an exact match on retry.
    local = git("tag", "--list", tag)
    if local:
        if git("rev-parse", "refs/tags/" + tag + "^{commit}") != sha:
            raise ValueError("conflicting local tag: " + tag)
    else:
        git("-c", "user.name=github-actions[bot]", "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "tag", "-a", tag, sha, "-m", "notion-dev " + current)
    try:
        git("push", "--no-follow-tags", "origin", "refs/tags/" + tag + ":refs/tags/" + tag)
    except subprocess.CalledProcessError:
        # A concurrent retry may have published the same tag. Anything else fails.
        if remote_target(tag) != sha:
            raise
    if remote_target(tag) != sha:
        raise ValueError("published tag did not resolve to the tested commit")
    return "Published " + tag + " at " + sha


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--before", required=True)
    args = parser.parse_args()
    try:
        print(publish(args.sha, args.before))
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, "Release tagging failed: %s\n" % exc)
