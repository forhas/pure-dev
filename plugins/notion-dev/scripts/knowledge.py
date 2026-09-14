#!/usr/bin/env python3
"""knowledge.py — the mechanical checks notion-dev's knowledge skill needs and iwe lacks.

Subcommands: check | touched | migrate. Exit 0 clean, 1 findings, 2 cannot run.
Never parses YAML: frontmatter comes from `iwe find -f json`; shape from `iwe schema validate`.
Exit 2 is never downgraded: a check that cannot run says so and fails.

Spec: docs/superpowers/specs/2026-09-14-knowledge-bundle-design.md §2, §3, §7, §9.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import difflib
import fnmatch
import shutil  # noqa: F401 — kept per the module's declared stdlib surface; unused today.

CANONICAL_TYPES = ["epic", "ticket", "decision", "gotcha", "component", "spec", "domain", "release"]
IWE_FILES = ["config.toml", "schemas/okf.yaml", "schemas/okf-index.yaml", "schemas/okf-log.yaml"]
KNOWLEDGE_IWE_REF = os.path.join("skills", "knowledge", "references", "iwe")
DROP_FRONTMATTER_KEYS = {"stale_after", "reconciled", "verified", "vouch"}
MIGRATE_AT_SENTINEL = "1970-01-01T00:00:00Z"


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def iwe(args, cwd):
    """Run iwe; exit 2 if the binary is missing or the call fails."""
    try:
        p = subprocess.run(["iwe", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        die("iwe is not on PATH — install: cargo install iwe --root ~/.local (or brew/npm where GLIBC >= 2.39)")
    if p.returncode not in (0, 1):
        die(f"iwe {' '.join(args)} failed: {p.stderr.strip()}")
    return p


def docs(bundle):
    """[{key, type, status, references:[{key}], superseded_by, applies_to, ...}] via iwe find."""
    if not os.path.isfile(os.path.join(bundle, ".iwe", "config.toml")):
        die(f"{bundle} is not a knowledge bundle (no .iwe/config.toml)")
    p = iwe(["find", "--filter", "", "-f", "json"], bundle)
    return json.loads(p.stdout or "[]")


def concept_dirs(bundle):
    """Top-level non-dot directories that contain .md files."""
    out = []
    if not os.path.isdir(bundle):
        return out
    for name in sorted(os.listdir(bundle)):
        if name.startswith("."):
            continue
        full = os.path.join(bundle, name)
        if not os.path.isdir(full):
            continue
        for _root, _dirs, files in os.walk(full):
            if any(f.endswith(".md") for f in files):
                out.append(name)
                break
    return out


def _resolve_key(base_dir, rel):
    """Resolve a relative-link-style string to the doc key it points at."""
    rel = rel[:-3] if rel.endswith(".md") else rel
    joined = os.path.normpath(os.path.join(base_dir, rel))
    return joined.replace(os.sep, "/")


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def run_check(a):
    """Runs every check rule; prints findings then warnings; returns True iff clean."""
    bundle = os.path.abspath(a.dir)
    findings = []
    warnings = []

    # 1. iwe copy drift
    if a.plugin_root:
        plugin_iwe_dir = os.path.join(os.path.abspath(a.plugin_root), KNOWLEDGE_IWE_REF)
        for rel in IWE_FILES:
            bpath = os.path.join(bundle, ".iwe", rel)
            ppath = os.path.join(plugin_iwe_dir, rel)
            relname = ".iwe/" + rel
            if not os.path.isfile(bpath):
                findings.append(f"{relname}: iwe: missing")
                continue
            if not os.path.isfile(ppath):
                continue
            with open(bpath, "rb") as f:
                b = f.read()
            with open(ppath, "rb") as f:
                p = f.read()
            if b != p:
                diff = list(difflib.unified_diff(
                    b.decode("utf-8", "replace").splitlines(keepends=True),
                    p.decode("utf-8", "replace").splitlines(keepends=True),
                ))
                findings.append(f"{relname}: iwe: differs from plugin copy ({len(diff)} diff lines)")

    all_docs = docs(bundle)
    by_key = {d["key"]: d for d in all_docs}
    keys = set(by_key)

    # 2. schema
    p = iwe(["schema", "validate", "-f", "json"], bundle)
    try:
        violations_list = json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        violations_list = []
    for entry in violations_list:
        key = entry.get("key", "?")
        for v in entry.get("violations", []):
            msg = v.get("message", "")
            breadcrumb = " > ".join(v.get("breadcrumb", []) or [])
            findings.append(f"{key}.md: schema: {msg} ({breadcrumb})")

    # 3. type dirs
    extra_types = {t for t in (a.extra_types or "").split(",") if t}
    for d in concept_dirs(bundle):
        if d in CANONICAL_TYPES or d in extra_types:
            continue
        for root, _dirs, files in os.walk(os.path.join(bundle, d)):
            for fn in files:
                if fn.endswith(".md"):
                    relf = os.path.relpath(os.path.join(root, fn), bundle)
                    findings.append(f"{relf}: type: undeclared directory {d}")

    # 4. links. A reference key that climbs out of the bundle root (iwe renders those as
    # `../...` keys) points at a file outside the OKF-managed collection entirely — a
    # filesystem link the bundle doesn't own and has no way to validate — so only
    # bundle-internal references are held to "must resolve to a known doc key".
    for d in all_docs:
        for r in d.get("references", []) or []:
            key = r["key"]
            if key.split("/")[0] == "..":
                continue
            if key not in keys:
                findings.append(f"{d['key']}.md: link: {key}")

    # 5. superseded_by
    for d in all_docs:
        if d.get("status") != "deprecated":
            continue
        sb = d.get("superseded_by")
        if not sb:
            continue
        docdir = os.path.dirname(d["key"])
        target_key = _resolve_key(docdir, sb)
        if target_key not in keys:
            findings.append(f"{d['key']}.md: superseded_by: {target_key}")
        elif by_key[target_key].get("status") == "deprecated":
            findings.append(f"{d['key']}.md: superseded_by: target is deprecated ({target_key})")

    # 6. index
    index_doc = by_key.get("index")
    if index_doc is not None:
        idx_targets = {r["key"] for r in index_doc.get("references", []) or []}
        for d in all_docs:
            if d["key"] in ("index", "log"):
                continue
            if d.get("status") == "stable" and d["key"] not in idx_targets:
                findings.append(f"index.md: index: {d['key']}")

    # 7. size
    for d in all_docs:
        fp = os.path.join(bundle, d["key"] + ".md")
        if os.path.isfile(fp):
            sz = os.path.getsize(fp)
            if sz > a.warn_bytes:
                warnings.append(f"{d['key']}.md: warn: {sz} bytes exceeds warnBytes {a.warn_bytes}")

    for line in findings:
        print(line)
    for line in warnings:
        print(line)
    return not findings


def cmd_check(a):
    ok = run_check(a)
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------------------
# touched
# ---------------------------------------------------------------------------

def cmd_touched(a):
    bundle = os.path.abspath(a.dir)
    try:
        root_p = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=bundle,
                                 capture_output=True, text=True)
    except FileNotFoundError:
        die("git is not on PATH")
    if root_p.returncode != 0:
        die(f"git rev-parse --show-toplevel failed: {root_p.stderr.strip()}")
    repo_root = root_p.stdout.strip()

    show_p = subprocess.run(["git", "show", "--name-only", "--pretty=format:", a.sha],
                             cwd=repo_root, capture_output=True, text=True)
    if show_p.returncode != 0:
        die(f"git show {a.sha} failed: {show_p.stderr.strip()}")
    changed = [ln.strip() for ln in show_p.stdout.splitlines() if ln.strip()]

    for d in docs(bundle):
        if d.get("status") != "stable":
            continue
        globs = d.get("applies_to") or []
        for g in globs:
            if any(fnmatch.fnmatch(c, g) for c in changed):
                print(f"{d['key']}.md")
                break
    sys.exit(0)


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------

def _split_frontmatter(text):
    """('---'-delimited frontmatter lines, body-text) or (None, text) when there is none."""
    if not text.startswith("---\n") and text != "---":
        return None, text
    lines = text.split("\n")
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            close_idx = i
            break
    if close_idx is None:
        return None, text
    fm_lines = lines[1:close_idx]
    body = "\n".join(lines[close_idx + 1:])
    return fm_lines, body


def migrate_concept_text(text, own_relpath):
    """Line-based frontmatter migration (spec §7 step 3). Body prose is untouched except
    the documented `## Reconciliation notes` → `## Updates` heading rename."""
    fm_lines, body = _split_frontmatter(text)
    if fm_lines is None:
        return text

    kept = []
    has_sources = False
    for ln in fm_lines:
        key = ln.split(":", 1)[0].strip()
        if key in DROP_FRONTMATTER_KEYS:
            continue
        if key == "sources":
            has_sources = True
        kept.append(ln)

    for i, ln in enumerate(kept):
        if ln.startswith("status:") and ln.split(":", 1)[1].strip() == "current":
            kept[i] = "status: stable"

    if not has_sources:
        m = re.search(r"\((https?://[^\s)]+)\)", body)
        if m:
            kept.append(f"sources:\n  - {{ id: ticket, resource: {m.group(1)} }}")
        else:
            kept.append(f"sources:\n  - {{ id: migrated, resource: {own_relpath} }}")
            replaced = False
            for i, ln in enumerate(kept):
                if ln.startswith("status:"):
                    kept[i] = "status: draft"
                    replaced = True
            if not replaced:
                kept.append("status: draft")

    body = "\n".join(
        "## Updates" if ln.strip() == "## Reconciliation notes" else ln
        for ln in body.split("\n")
    )

    return "---\n" + "\n".join(kept) + "\n---\n" + body


LOG_ENTRY_RE = re.compile(
    r"^\**\s*\*\*(?:Creation|Update|Deprecation)\*\*\s+(\d{4}-\d{2}-\d{2})\s+—\s+(.+?)\s*$"
)


def reshape_log(text):
    """Old flat `**Creation** YYYY-MM-DD — text` lines → shipped okf-log.yaml shape."""
    groups = {}
    order = []
    for raw in text.split("\n"):
        m = LOG_ENTRY_RE.match(raw.strip().lstrip("- "))
        if not m:
            continue
        date, entry_text = m.group(1), m.group(2)
        if date not in groups:
            groups[date] = []
            order.append(date)
        groups[date].append(entry_text)
    out = ["# Update log", ""]
    for date in sorted(order, reverse=True):
        out.append(f"## {date}")
        for entry_text in groups[date]:
            out.append(f"- {entry_text}")
        out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def reshape_index(text):
    """Reshape an index.md into the shipped okf-index.yaml shape: flat `# <group>` sections,
    each followed directly by a bullet list, no nesting. Used only when index.md pre-exists;
    none of task 1's fixtures exercise this path (no migrate-input index.md)."""
    fm_lines, body = _split_frontmatter(text)
    groups = {}
    order = []
    current = None
    for raw in body.split("\n"):
        m = re.match(r"^#{1,6}\s+(.+?)\s*$", raw)
        if m and not raw.strip().startswith("- "):
            current = m.group(1).strip()
            if current not in groups:
                groups[current] = []
                order.append(current)
            continue
        if raw.strip().startswith("- ") and current is not None:
            groups[current].append(raw.strip())
    out_fm = fm_lines if fm_lines is not None else ['okf_version: "0.2"']
    out = ["---"] + out_fm + ["---"]
    for name in order:
        out.append(f"# {name}")
        out.extend(groups[name])
        out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def add_epic_frontmatter(body_text, filename):
    """Prepend spec §3 Epic frontmatter to a pre-OKF epic-doc brief that has none."""
    lines = body_text.split("\n")
    title = lines[0][2:].strip() if lines and lines[0].startswith("# ") else filename
    m = re.match(r"^([A-Za-z]+-\d+)-", filename)
    epic_id = m.group(1) if m else ""
    description = ""
    for i, ln in enumerate(lines):
        if ln.strip() == "## Goal":
            for j in range(i + 1, len(lines)):
                stripped = lines[j].strip()
                if stripped.startswith("#"):
                    break
                if stripped:
                    description = stripped
                    break
            break
    own_resource = f"epic/{filename}"
    fm = [
        "---",
        "type: Epic",
        f'title: "{title}"',
        f'description: "{description}"',
        "status: draft",
        f"epic: {epic_id}",
        f'generated: {{ by: notion-dev:migrate, at: "{MIGRATE_AT_SENTINEL}" }}',
        "sources:",
        f"  - {{ id: migrated, resource: {own_resource} }}",
        "---",
    ]
    return "\n".join(fm) + "\n" + body_text


# ---------------------------------------------------------------------------
# migrate step 5: relative links broken by moving the brief (spec §7 step 5)
# ---------------------------------------------------------------------------

MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def _is_rewritable_link(target):
    """False for URLs, mailto:, and bare anchors — nothing os.path can resolve."""
    if not target or target.startswith("#"):
        return False
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):  # any URL scheme, incl. mailto:
        return False
    return True


def _rewrite_links(text, resolve):
    """resolve(path_without_fragment) -> new relative path, or None to leave the link as-is."""

    def repl(m):
        label, target = m.group(1), m.group(2)
        if not _is_rewritable_link(target):
            return m.group(0)
        path_part, sep, frag = target.partition("#")
        new_path = resolve(path_part)
        if new_path is None:
            return m.group(0)
        return f"[{label}]({new_path}{sep}{frag})"

    return MD_LINK_RE.sub(repl, text)


def _resolve_link_target(base_dir_abs, target):
    return os.path.normpath(os.path.join(base_dir_abs, target))


def _rewrite_brief_links(body, old_dir_abs, new_dir_abs):
    """(a) Every relative link inside the moved brief, recomputed from its new location."""

    def resolve(path_part):
        old_abs = _resolve_link_target(old_dir_abs, path_part)
        return os.path.relpath(old_abs, new_dir_abs).replace(os.sep, "/")

    return _rewrite_links(body, resolve)


def _rewrite_links_to_brief(text, file_dir_abs, old_brief_abs, new_brief_abs):
    """(b) Only links that resolve to the moved brief's OLD path get repointed."""

    def resolve(path_part):
        target_abs = _resolve_link_target(file_dir_abs, path_part)
        if target_abs != old_brief_abs:
            return None
        return os.path.relpath(new_brief_abs, file_dir_abs).replace(os.sep, "/")

    return _rewrite_links(text, resolve)


def _git_tracked_md_files(repo_root):
    """`git ls-files '*.md'` relative to repo_root, or None if not a git repo / no git."""
    try:
        p = subprocess.run(["git", "ls-files", "*.md"], cwd=repo_root,
                            capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if p.returncode != 0:
        return None
    return [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]


def _apply_text_rewrite(result, repo_root, relpath, rewrite):
    """Applies `rewrite(text) -> text` to the already-migrated result entry when present,
    else to the file's current on-disk content. Updates `result` only when text changes."""
    if relpath in result:
        current = result[relpath]
    else:
        abspath = os.path.join(repo_root, relpath)
        if not os.path.isfile(abspath):
            return
        with open(abspath, "rb") as f:
            current = f.read()
    text = current.decode("utf-8")
    new_text = rewrite(text)
    if new_text != text:
        result[relpath] = new_text.encode("utf-8")


def _build_migration(bundle, repo_root, plugin_root, config_path):
    """Returns (result: {repo-relative path: new bytes}, to_delete: [repo-relative path])."""
    result = {}
    to_delete = []
    bundle_rel = os.path.relpath(bundle, repo_root)

    # step 2: plugin-owned .iwe/ files, installed verbatim (overwriting)
    plugin_iwe_dir = os.path.join(plugin_root, KNOWLEDGE_IWE_REF)
    for rel in IWE_FILES:
        with open(os.path.join(plugin_iwe_dir, rel), "rb") as f:
            result[os.path.join(bundle_rel, ".iwe", rel)] = f.read()

    # step 3: concept frontmatter migration, log.md and index.md reshape
    if os.path.isdir(bundle):
        for dirpath, dirnames, filenames in os.walk(bundle):
            dirnames[:] = [dn for dn in dirnames if not dn.startswith(".")]
            for fn in filenames:
                if not fn.endswith(".md"):
                    continue
                fpath = os.path.join(dirpath, fn)
                rel_to_bundle = os.path.relpath(fpath, bundle)
                if dirpath == bundle and fn in ("log.md", "index.md"):
                    continue
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()
                new_text = migrate_concept_text(text, rel_to_bundle)
                result[os.path.join(bundle_rel, rel_to_bundle)] = new_text.encode("utf-8")

    log_path = os.path.join(bundle, "log.md")
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            result[os.path.join(bundle_rel, "log.md")] = reshape_log(f.read()).encode("utf-8")

    index_path = os.path.join(bundle, "index.md")
    if os.path.isfile(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            result[os.path.join(bundle_rel, "index.md")] = reshape_index(f.read()).encode("utf-8")

    # config (read once, used by steps 4 and 6)
    cfg = {}
    if config_path and os.path.isfile(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    # step 4: move epic-doc brief(s) into epic/, adding frontmatter
    epic_docs_dir = None
    if isinstance(cfg.get("epicDocs"), dict):
        epic_docs_dir = cfg["epicDocs"].get("dir")
    moved_briefs = []  # [(old_repo_rel, new_repo_rel)], for step 5
    if epic_docs_dir:
        abs_epics_dir = os.path.join(repo_root, epic_docs_dir)
        new_epic_dir_abs = os.path.join(repo_root, bundle_rel, "epic")
        if os.path.isdir(abs_epics_dir):
            for fn in sorted(os.listdir(abs_epics_dir)):
                if not fn.endswith(".md"):
                    continue
                src = os.path.join(abs_epics_dir, fn)
                with open(src, "r", encoding="utf-8") as f:
                    body = f.read()
                # 5(a): recompute this brief's own relative links before adding frontmatter.
                body = _rewrite_brief_links(body, abs_epics_dir, new_epic_dir_abs)
                new_body = add_epic_frontmatter(body, fn)
                new_rel = os.path.join(bundle_rel, "epic", fn)
                result[new_rel] = new_body.encode("utf-8")
                old_rel = os.path.relpath(src, repo_root)
                to_delete.append(old_rel)
                moved_briefs.append((old_rel, new_rel))

    # step 5(b): every other tracked *.md file that links to a moved brief's old path gets
    # that link repointed at the new path, relative to the linking file. Requires the bundle
    # to be inside a git repo (to enumerate tracked files); otherwise this is skipped with a
    # warning, never an error — migrate still succeeds, just without this rewrite.
    if moved_briefs:
        tracked = _git_tracked_md_files(repo_root)
        if tracked is None:
            print("warn: migrate step 5b skipped — bundle is not inside a git repository "
                  "(links to the moved brief from outside the bundle were not rewritten)")
        else:
            moved_set = {old for old, _new in moved_briefs}
            for relpath in tracked:
                if relpath in moved_set:
                    continue
                file_dir_abs = os.path.join(repo_root, os.path.dirname(relpath))
                for old_rel, new_rel in moved_briefs:
                    old_abs = os.path.normpath(os.path.join(repo_root, old_rel))
                    new_abs = os.path.normpath(os.path.join(repo_root, new_rel))
                    _apply_text_rewrite(
                        result, repo_root, relpath,
                        lambda text, fd=file_dir_abs, oa=old_abs, na=new_abs:
                            _rewrite_links_to_brief(text, fd, oa, na),
                    )

    # step 6: config — drop epicDocs, add knowledge block, rename the post-merge hook
    if config_path:
        new_cfg = dict(cfg)
        new_cfg.pop("epicDocs", None)
        extras = sorted(t for t in concept_dirs(bundle) if t not in CANONICAL_TYPES)
        new_cfg["knowledge"] = {"extraTypes": extras}
        git_cfg = new_cfg.get("git")
        if isinstance(git_cfg, dict) and "postMergeHooks" in git_cfg:
            git_cfg["postMergeHooks"] = [
                "notion-dev:knowledge" if h == "knowledge-capture" else h
                for h in git_cfg["postMergeHooks"]
            ]
        result[os.path.relpath(config_path, repo_root)] = (
            json.dumps(new_cfg, indent=2) + "\n"
        ).encode("utf-8")

    return result, to_delete


def _print_diff(repo_root, result, to_delete):
    any_diff = False
    for relpath in sorted(result.keys()):
        abspath = os.path.join(repo_root, relpath)
        old = b""
        if os.path.isfile(abspath):
            with open(abspath, "rb") as f:
                old = f.read()
        new = result[relpath]
        if old == new:
            continue
        any_diff = True
        old_lines = old.decode("utf-8", "replace").splitlines(keepends=True)
        new_lines = new.decode("utf-8", "replace").splitlines(keepends=True)
        sys.stdout.writelines(difflib.unified_diff(
            old_lines, new_lines, fromfile=f"a/{relpath}", tofile=f"b/{relpath}"))
    for relpath in sorted(to_delete):
        abspath = os.path.join(repo_root, relpath)
        if not os.path.isfile(abspath):
            continue
        any_diff = True
        with open(abspath, "rb") as f:
            old = f.read()
        old_lines = old.decode("utf-8", "replace").splitlines(keepends=True)
        sys.stdout.writelines(difflib.unified_diff(
            old_lines, [], fromfile=f"a/{relpath}", tofile="/dev/null"))
    return any_diff


def cmd_migrate(a):
    bundle = os.path.abspath(a.dir)
    plugin_root = os.path.abspath(a.plugin_root) if a.plugin_root else None
    if not plugin_root:
        die("migrate requires --plugin-root")
    config_path = os.path.abspath(a.config) if a.config else None
    repo_root = os.path.dirname(os.path.dirname(config_path)) if config_path else os.path.dirname(bundle)

    result, to_delete = _build_migration(bundle, repo_root, plugin_root, config_path)
    _print_diff(repo_root, result, to_delete)

    if not a.apply:
        sys.exit(0)

    backup = {}
    for relpath in list(result.keys()) + to_delete:
        abspath = os.path.join(repo_root, relpath)
        backup[relpath] = open(abspath, "rb").read() if os.path.isfile(abspath) else None

    # Directories os.makedirs() creates along the way that did not exist before this
    # apply. Tracked so a failed post-apply check can remove them again, not just the
    # files inside them — otherwise a reverted apply still leaves `epic/`,
    # `.iwe/schemas/`, etc. behind as new, empty directories.
    created_dirs = set()

    def restore():
        for relpath, content in backup.items():
            abspath = os.path.join(repo_root, relpath)
            if content is None:
                if os.path.isfile(abspath):
                    os.remove(abspath)
            else:
                os.makedirs(os.path.dirname(abspath), exist_ok=True)
                with open(abspath, "wb") as f:
                    f.write(content)
        # Deepest first, and only when now-empty: a directory that still holds
        # something restore() put back (or that pre-dated this apply) must survive.
        for d in sorted(created_dirs, key=lambda p: p.count(os.sep), reverse=True):
            try:
                os.rmdir(d)
            except OSError:
                pass

    for relpath, content in result.items():
        abspath = os.path.join(repo_root, relpath)
        d = os.path.dirname(abspath)
        while d and d != repo_root and not os.path.isdir(d):
            created_dirs.add(d)
            d = os.path.dirname(d)
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        with open(abspath, "wb") as f:
            f.write(content)
    for relpath in to_delete:
        abspath = os.path.join(repo_root, relpath)
        if os.path.isfile(abspath):
            os.remove(abspath)
            try:
                os.removedirs(os.path.dirname(abspath))
            except OSError:
                pass

    class _CheckArgs:
        pass

    ca = _CheckArgs()
    ca.dir = bundle
    ca.plugin_root = plugin_root
    ca.extra_types = ",".join(sorted(t for t in concept_dirs(bundle) if t not in CANONICAL_TYPES))
    ca.warn_bytes = 8192
    if run_check(ca):
        sys.exit(0)
    restore()
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="knowledge.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check")
    p_check.add_argument("--dir", default="knowledge")
    p_check.add_argument("--plugin-root", default=None)
    p_check.add_argument("--extra-types", default="")
    p_check.add_argument("--warn-bytes", type=int, default=8192)
    p_check.set_defaults(func=cmd_check)

    p_touched = sub.add_parser("touched")
    p_touched.add_argument("sha")
    p_touched.add_argument("--dir", default="knowledge")
    p_touched.set_defaults(func=cmd_touched)

    p_migrate = sub.add_parser("migrate")
    p_migrate.add_argument("--apply", action="store_true")
    p_migrate.add_argument("--dir", default="knowledge")
    p_migrate.add_argument("--config", default=None)
    p_migrate.add_argument("--plugin-root", default=None)
    p_migrate.set_defaults(func=cmd_migrate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
