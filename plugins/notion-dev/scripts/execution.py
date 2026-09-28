"""Portable local execution boundaries; no provider calls or implicit pushes."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from runtime import atomic_json, digest, git, read_json, require, revision


def json_file(value, output):
    """Immutable UTF-8 artifact, not a locale-sensitive stdout pipe."""
    path = Path(output).resolve()
    if path.exists():
        require(read_json(path) == value, "output already contains different data; choose a new file")
    else:
        atomic_json(path, value)
    return {"file": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def followup_file(packet, output, recipe=None):
    from recording import followup_body
    rendered = followup_body(read_json(packet))
    if recipe:
        # The adapter supplies live schema/association/approval decisions. Only the
        # title/content slots are filled here; no inferred provider properties.
        value = read_json(recipe)
        require(isinstance(value, dict) and set(value) == {"name", "target", "tool", "input", "title_property"},
                "recipe requires name/target/tool/input/title_property")
        require(value["tool"] == "mcp__notion__notion-create-pages", "follow-up recipe requires notion-create-pages")
        title = value.pop("title_property")
        args = value["input"]
        require(isinstance(title, str) and title and isinstance(args, dict)
                and isinstance(args.get("parent"), dict) and args["parent"]
                and isinstance(args.get("pages"), list) and len(args["pages"]) == 1,
                "declare one follow-up page and its actual parent")
        page = args["pages"][0]
        require(isinstance(page, dict) and isinstance(page.get("properties"), dict)
                and title not in page["properties"] and "content" not in page,
                "title/content are builder-owned; do not supply a second copy")
        page["properties"][title] = rendered["title"]
        page["content"] = rendered["body"]
        rendered = [value]
    return {**json_file(rendered, output), "instruction":
            "Use this UTF-8 file directly. A recipe output is ready for record-children --writes. "
            "Read data.host_call from record-next --begin and dispatch unchanged; never decode through a shell pipe."}


def tree_digest(directory):
    root = Path(directory).resolve()
    values = []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "knowledge check/commit refuses symlinks")
        if path.is_file(): values.append((path.relative_to(root).as_posix(), digest(path)))
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()


def knowledge_commit(project, branch, run, message):
    """Check and commit in one process; filtering stdout cannot authorize a commit.

    Caller still owns the existing primary lock, initial clean-bundle assertion,
    merge ancestry and push/convergence contract. No rollback or push here.
    """
    from workflow import primary, local_dir
    root = primary(project)
    require(Path(project).resolve() == root, "knowledge commit requires primary checkout")
    config_path = root / ".claude/notion-dev.config.json"
    config = read_json(config_path)
    directory = (root / config.get("knowledge", {}).get("dir", "knowledge")).resolve()
    require(directory != root and root in directory.parents and directory.is_dir(),
            "knowledge.dir must be an existing directory inside the primary checkout")
    relative = directory.relative_to(root).as_posix()
    require(relative.split("/")[0] not in {".git", ".claude"}, "unsafe knowledge directory")
    require(branch and git(root, "branch", "--show-current") == branch, "knowledge branch changed")
    owner = local_dir(root) / "locks/primary/owner"
    require(run and owner.is_file() and ("run: " + run) in owner.read_text(encoding="utf-8").splitlines(),
            "hold the existing primary writer lock under --run before check/commit")
    require(message.strip(), "commit message required")
    before_head, before = git(root, "rev-parse", "HEAD"), tree_digest(directory)
    # One immutable log per attempt: a retry must not rewrite evidence already receipted.
    log = local_dir(root) / ("knowledge-check-" + before + "-" + os.urandom(6).hex() + ".log")
    command = [sys.executable, str(Path(__file__).with_name("knowledge.py")), "check",
               "--config", str(config_path), "--dir", str(directory)]
    with log.open("xb") as stream:
        proc = subprocess.run(command, cwd=str(root), stdout=stream, stderr=subprocess.STDOUT,
                              env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    receipt = {"passed": False, "exit_code": proc.returncode, "log": str(log),
               "log_sha256": digest(log), "checked_tree": before, "head": before_head}
    if proc.returncode: return receipt
    require(tree_digest(directory) == before and git(root, "rev-parse", "HEAD") == before_head
            and git(root, "branch", "--show-current") == branch
            and owner.is_file() and ("run: " + run) in owner.read_text(encoding="utf-8").splitlines(),
            "knowledge/head/branch/lock changed during validation; do not commit")
    if not git(root, "status", "--porcelain", "--", relative):
        return {**receipt, "passed": True, "commit": None}
    git(root, "add", "--", relative)
    git(root, "commit", "--only", "-m", message, "--", relative)
    require(tree_digest(directory) == before, "commit hook changed validated knowledge; do not push; inspect and recheck")
    require(not git(root, "status", "--porcelain", "--", relative), "knowledge changed during commit; do not push")
    return {**receipt, "passed": True, "commit": git(root, "rev-parse", "HEAD"),
            "instruction": "Push only through the existing owned epic write-path after its branch/ancestry checks."}


def mutation_baseline(worktree):
    """No restore operation: refuse unsafe mutation of uncommitted implementation."""
    current = revision(worktree)
    require(current["clean"], "commit implementation or use an isolated copy before mutation testing")
    return {"passed": True, "revision": current,
            "instruction": "Mutate only explicitly named fixture/source paths in this clean baseline or an isolated copy. "
                           "Confirm the intended check fails, restore only your mutations, then verify the baseline again. "
                           "Never restore a directory or unrelated edits; recheck HEAD/status before restoration."}


def await_worker(state, worker, seconds=60):
    from runtime import Runtime
    rt = Runtime(state)
    result = rt.wait(worker, seconds)
    if result["result_available"] and result["status"] in {"result_ready", "consumed"}:
        return {"action": "judge-result", "passed": True, **rt.consume(worker, summary=True)}
    return {**result, "passed": False,
            "action": "answer-question" if result["status"] == "needs_input" else "continue-existing-worker",
            "instruction": "Pending is not failure. If this call is backgrounded, await THAT host task once; "
                           "do not poll its output file, nest grep/sleep loops or start a second waiter. "
                           "After the task finishes, inspect the worker for a late result before another bounded wait. "
                           "Host-return publication waits for the same agent's final response instead. "
                           "Timeout never authorizes cancellation, replacement or acceptance."}


GUIDES = {
    "intake": {"runtime.md": ["Requirements and evidence"], "boundaries.md": ["Actual host captures"]},
    "dispatch": {"runtime.md": ["Dispatch contract", "Wait and questions", "Publication, acceptance and cancellation"]},
    "review": {"runtime.md": ["Independent review and deltas"],
               "boundaries.md": ["One factual owner; freeze author-written ticket narrative", "Compact delta publication"]},
    "merge": {"runtime.md": ["Fresh authoritative ticket at the merge boundary"]},
    "record": {"boundaries.md": ["Canonical recording and execution", "Measurement"]},
}


def guide(stage):
    """Route existing authoritative sections without copying their contracts."""
    require(stage in GUIDES, "unknown stage")
    root = Path(__file__).resolve().parent.parent / "references"
    parts = ["# notion-dev " + stage + " contract\n\nUse configured knowledge.python. "
             "Preserve the invocation, evidence, ownership and budgets. Load other stages only when reached."]
    for name, headings in GUIDES[stage].items():
        text = (root / name).read_text(encoding="utf-8")
        matches = list(re.finditer(r"^## (.+)$", text, re.M))
        for heading in headings:
            indexes = [i for i, m in enumerate(matches) if m[1] == heading]
            require(len(indexes) == 1, "stage guide heading missing or ambiguous: " + name + ":" + heading)
            i = indexes[0]
            parts.append("Source: references/" + name + "\n\n" + text[matches[i].start():
                matches[i + 1].start() if i + 1 < len(matches) else len(text)].rstrip())
    return "\n\n".join(parts) + "\n"
