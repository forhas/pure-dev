#!/usr/bin/env python3
"""knowledge.py — the mechanical checks notion-dev's knowledge skill needs and iwe lacks.

Subcommands: check | touched | migrate. Exit 0 clean, 1 findings, 2 cannot run.
Never parses YAML: frontmatter comes from `iwe find -f json`; shape from `iwe schema validate`.
Exit 2 is never downgraded: a check that cannot run says so and fails. An iwe call that
exits non-zero for any reason other than reported violations, or whose JSON does not parse,
is exit 2 — never an empty result standing in for a clean bundle.

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

CANONICAL_TYPES = ["epic", "ticket", "decision", "gotcha", "component", "spec", "domain", "release"]
IWE_FILES = ["config.toml", "schemas/okf.yaml", "schemas/okf-index.yaml", "schemas/okf-log.yaml"]
KNOWLEDGE_IWE_REF = os.path.join("skills", "knowledge", "references", "iwe")
DROP_FRONTMATTER_KEYS = {"stale_after", "reconciled", "verified", "vouch"}
MIGRATE_AT_SENTINEL = "1970-01-01T00:00:00Z"
MIGRATE_SEED_DATE = "1970-01-01"
DEFAULT_EPIC_DOCS_DIR = "docs/epics"


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def iwe(args, cwd, violations_exit=()):
    """Run iwe; exit 2 if the binary is missing or the call fails.

    `violations_exit` names the exit codes this subcommand uses to *report violations* —
    `iwe schema validate` exits 1 with a violation list. Every other non-zero exit is a
    call that could not run, and is exit 2: accepting it and reading `"" or "[]"` as an
    empty result is a check that passes because it never ran.
    """
    try:
        p = subprocess.run(["iwe", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        die("iwe is not on PATH — install: cargo install iwe --root ~/.local (or brew/npm where GLIBC >= 2.39)")
    if p.returncode != 0 and p.returncode not in violations_exit:
        die(f"iwe {' '.join(args)} failed (exit {p.returncode}): {p.stderr.strip()}")
    return p


def iwe_json(args, cwd, violations_exit=()):
    """iwe() plus the JSON parse; unparseable output is exit 2, never an empty list."""
    p = iwe(args, cwd, violations_exit)
    out = p.stdout.strip()
    if not out:
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        die(f"iwe {' '.join(args)} produced unparseable JSON: {exc}")


def docs(bundle):
    """[{key, type, status, references:[{key}], superseded_by, applies_to, ...}] via iwe find."""
    if not os.path.isfile(os.path.join(bundle, ".iwe", "config.toml")):
        die(f"{bundle} is not a knowledge bundle (no .iwe/config.toml)")
    return iwe_json(["find", "--filter", "", "-f", "json"], bundle)


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


DEFAULT_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_REL = os.path.join(".claude", "notion-dev.config.json")


def _git_toplevel(start):
    """The git work-tree root containing `start`, or None."""
    try:
        p = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                           capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if p.returncode != 0:
        return None
    return p.stdout.strip() or None


def load_config(config_path):
    """The parsed config, or {} when there is none. Malformed JSON is exit 2, not {} —
    a config that cannot be read must not silently become the defaults it was written
    to override."""
    if not config_path or not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        die(f"{config_path} could not be read: {exc}")


def resolve_check_args(a):
    """Fills `check`'s optional flags from `.claude/notion-dev.config.json` (spec §9).

    The client CI one-liner of spec §13 passes no per-repo flags, so every one of them
    has to come from the config when it is absent: `--config` defaults to the file at the
    git top level, and `dir`, `extraTypes` and `warnBytes` come from its `knowledge` block.
    An explicit flag always wins over the config.
    """
    cwd = os.getcwd()
    config_path = os.path.abspath(a.config) if a.config else None
    if config_path is None:
        top = _git_toplevel(cwd)
        if top:
            candidate = os.path.join(top, DEFAULT_CONFIG_REL)
            if os.path.isfile(candidate):
                config_path = candidate
    cfg = load_config(config_path)
    kn = cfg.get("knowledge") if isinstance(cfg.get("knowledge"), dict) else {}
    base = os.path.dirname(os.path.dirname(config_path)) if config_path else cwd

    if a.dir is None:
        a.dir = os.path.join(base, kn.get("dir") or "knowledge")
    if a.extra_types is None:
        extras = kn.get("extraTypes")
        a.extra_types = ",".join(extras) if isinstance(extras, list) else ""
    if a.warn_bytes is None:
        wb = kn.get("warnBytes")
        a.warn_bytes = wb if isinstance(wb, int) else 8192
    if a.plugin_root is None:
        a.plugin_root = DEFAULT_PLUGIN_ROOT
    return a


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def run_check(a):
    """Runs every check rule; prints findings then warnings; returns True iff clean."""
    bundle = os.path.abspath(a.dir)
    findings = []
    warnings = []

    # 1. iwe copy drift. `--plugin-root` defaults to this script's own plugin directory
    # (spec §9); when the shipped reference copy is not there the rule cannot run at all,
    # and a drift rule that silently skips is exactly what lets a client loosen the schema
    # it is checked against — so that is exit 2, never a pass.
    plugin_iwe_dir = os.path.join(os.path.abspath(a.plugin_root or DEFAULT_PLUGIN_ROOT),
                                  KNOWLEDGE_IWE_REF)
    if not os.path.isdir(plugin_iwe_dir):
        die(f"--plugin-root {a.plugin_root}: no {KNOWLEDGE_IWE_REF}/ — the .iwe drift rule cannot run")
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

    # 2. schema. Exit 1 is how `iwe schema validate` reports violations; anything else,
    # or output that does not parse, is a validation that did not happen (F10).
    violations_list = iwe_json(["schema", "validate", "-f", "json"], bundle,
                               violations_exit=(1,))
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
    # `../...` keys — every key iwe emits is bundle-root-relative, so a link resolved against
    # its own file and re-expressed against the bundle root lands outside it) points at a file
    # the OKF-managed collection doesn't own. It still has to exist: silently skipping it would
    # be a check that passes when it cannot actually verify anything — the "checks that pass
    # when they cannot run" failure mode CLAUDE.md and spec decision 9 both forbid — so it is
    # resolved on disk instead of against a doc key (bundle root + key, with `.md` appended
    # when the key carries no extension, since iwe strips it from in-bundle keys too).
    for d in all_docs:
        for r in d.get("references", []) or []:
            key = r["key"]
            if key.split("/")[0] == "..":
                disk_rel = key if os.path.splitext(key)[1] else key + ".md"
                disk_path = os.path.normpath(os.path.join(bundle, disk_rel))
                if not os.path.isfile(disk_path):
                    findings.append(f"{d['key']}.md: link: {key} (outside bundle, not on disk)")
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
        # Spec §3: a bundle key (`gotcha/new-trap`) or a path. Resolved against the bundle
        # root first, then against the concept's own directory, `.md` appended when absent —
        # both clients' existing spellings validate, and neither needs a rewrite.
        root_key = _resolve_key("", sb)
        own_key = _resolve_key(os.path.dirname(d["key"]), sb)
        target_key = root_key if root_key in keys else own_key
        if target_key not in keys:
            findings.append(f"{d['key']}.md: superseded_by: {target_key}")
        elif by_key[target_key].get("status") == "deprecated":
            findings.append(f"{d['key']}.md: superseded_by: target is deprecated ({target_key})")

    # 6. index and log. A bundle missing either is a finding, never a skipped rule: an
    # absent catalog made rule 6 vacuous and an absent log was never schema-checked at all,
    # so a bundle holding nothing but `.iwe/` used to exit 0 (F9, spec §9).
    for required in ("index", "log"):
        if not os.path.isfile(os.path.join(bundle, required + ".md")):
            findings.append(f"{required}.md: missing: the bundle has no {required}.md")
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
    ok = run_check(resolve_check_args(a))
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

    # Diff against the FIRST PARENT, never `git show`: for a two-parent merge commit
    # (`git.mergeStrategy: merge`) plain `git show` emits no changed paths at all, so every
    # `applies_to` concept would be silently skipped. `<sha>^1..<sha>` is the PR's landed diff
    # for a merge and the ordinary diff for a squash; a root commit has no `^1`, so fall back
    # to the commit's own tree there.
    show_p = subprocess.run(["git", "diff", "--name-only", f"{a.sha}^1", a.sha],
                             cwd=repo_root, capture_output=True, text=True)
    if show_p.returncode != 0:
        show_p = subprocess.run(["git", "show", "--name-only", "--pretty=format:", a.sha],
                                 cwd=repo_root, capture_output=True, text=True)
        if show_p.returncode != 0:
            die(f"git diff {a.sha}^1 {a.sha} failed: {show_p.stderr.strip()}")
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

def normalise_text(text):
    """Strip a UTF-8 BOM and fold CRLF to LF.

    Spec §9: migrate writes `\n` regardless of host. One client's bundle lives on a
    Windows drive under WSL and 76 of its 132 concepts are CRLF; without this every one
    of them failed the `---\n` opener below and was returned unmigrated, silently.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


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


FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\s*:")


def frontmatter_blocks(fm_lines):
    """[(key | None, [lines])] — each frontmatter key with the lines that belong to it.

    A key opens at column 0; every following line that is indented, blank, or otherwise
    does not open a key of its own is that key's continuation. Real concepts wrap flow
    mappings (`reconciled: { at: …,\n              against: [...] }`) and nest block
    sequences (`sources:\n  - id: …`), and dropping a key one physical line at a time
    left the orphaned continuation behind — which destroys the whole frontmatter (F4).
    """
    blocks = []
    for ln in fm_lines:
        m = FM_KEY_RE.match(ln)
        if m and not ln[:1].isspace():
            blocks.append((m.group(1), [ln]))
        elif blocks:
            blocks[-1][1].append(ln)
        else:
            blocks.append((None, [ln]))
    return blocks


def concept_frontmatter_value(text, key):
    """The scalar value of a top-level frontmatter key, or None. Reads the migrated text
    the script itself just produced, so the catalog never needs a second iwe pass."""
    fm_lines, _ = _split_frontmatter(text)
    if fm_lines is None:
        return None
    for k, lines in frontmatter_blocks(fm_lines):
        if k == key:
            return lines[0].split(":", 1)[1].strip().strip('"').strip("'")
    return None


def migrate_concept_text(text, own_relpath, bundle_name=None):
    """Frontmatter migration (spec §7 step 3), key block by key block, never line by line.
    Body prose is untouched except the documented `## Reconciliation notes` → `## Updates`
    heading rename."""
    text = normalise_text(text)
    fm_lines, body = _split_frontmatter(text)
    if fm_lines is None:
        return text
    blocks = frontmatter_blocks(fm_lines)

    kept = []
    has_sources = False
    for key, lines in blocks:
        if key in DROP_FRONTMATTER_KEYS:
            continue                      # the key AND its continuation lines
        if key == "sources":
            has_sources = True
        if key == "status" and lines[0].split(":", 1)[1].strip() == "current":
            lines = ["status: stable"] + lines[1:]
        if key == "superseded_by":
            # Normalise the one spelling spec §3 does not resolve: a value written from the
            # REPO root, carrying the bundle directory itself (`knowledge/spec/x.md`). One
            # client stores it that way; `check` resolves bundle-root-first, so strip the
            # prefix here rather than teach the check a third base.
            value = lines[0].split(":", 1)[1].strip()
            if bundle_name and value.startswith(bundle_name + "/"):
                lines = [f"superseded_by: {value[len(bundle_name) + 1:]}"] + lines[1:]
        kept.append((key, list(lines)))

    if not has_sources:
        m = re.search(r"\((https?://[^\s)]+)\)", body)
        if m:
            kept.append(("sources", ["sources:", f"  - {{ id: ticket, resource: {m.group(1)} }}"]))
        else:
            kept.append(("sources", ["sources:", f"  - {{ id: migrated, resource: {own_relpath} }}"]))
            replaced = False
            for i, (key, lines) in enumerate(kept):
                if key == "status":
                    kept[i] = (key, ["status: draft"] + lines[1:])
                    replaced = True
            if not replaced:
                kept.append(("status", ["status: draft"]))

    out_fm = [ln for _key, lines in kept for ln in lines]

    body = "\n".join(
        "## Updates" if ln.strip() == "## Reconciliation notes" else ln
        for ln in body.split("\n")
    )

    return "---\n" + "\n".join(out_fm) + "\n---\n" + body


LOG_ENTRY_RE = re.compile(
    r"^\**\s*\*\*(?:Creation|Update|Deprecation)\*\*\s+(\d{4}-\d{2}-\d{2})\s+—\s+(.+?)\s*$"
)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
BULLET_RE = re.compile(r"^[-*+](?:\s|$)")


def _blocks(lines):
    """Group a run of markdown lines into top-level blocks: ('bullet'|'heading'|'para', lines).

    A bullet's continuation is every following line that is indented or blank-then-indented,
    so a hard-wrapped bullet — which is what both clients' logs are made of — stays one block
    instead of being truncated at the first line break (F5).
    """
    out = []
    pending_blank = []
    for ln in lines:
        if not ln.strip():
            pending_blank.append(ln)
            continue
        indented = ln[:1].isspace()
        if HEADING_RE.match(ln) and not indented:
            out.append(["heading", [ln]])
        elif BULLET_RE.match(ln) and not indented:
            out.append(["bullet", [ln]])
        elif out and (indented or not pending_blank):
            # An indented line continues the block above it; so does an unindented one
            # with no blank line between, which is how markdown hard-wraps a paragraph —
            # both clients' logs wrap at column 0, and treating each wrapped line as its
            # own entry is the same loss as truncating it, only noisier.
            out[-1][1].extend(pending_blank)
            out[-1][1].append(ln)
        else:
            out.append(["para", [ln]])
        pending_blank = []
    for kind, blk in out:
        while blk and not blk[-1].strip():
            blk.pop()
    return [(k, b) for k, b in out if b]


def _as_bullet(kind, blk):
    """One block rendered as one bullet, with every line of it carried over.

    Nothing is dropped: a paragraph becomes the bullet's first line with its wrapped
    remainder indented under it, and a sub-heading becomes a bold bullet. `okf-log.yaml`
    wants bullets under each date and `maxDepth: 2` forbids the `###` sub-sections both
    clients' logs use, so this is the reshape that loses no text.
    """
    if kind == "bullet":
        # A hard-wrapped bullet whose continuation sits at column 0 is still one bullet;
        # left unindented it reads as loose text after the list and stops being part of it.
        return [blk[0]] + [ln if (ln[:1].isspace() or not ln.strip()) else "  " + ln
                           for ln in blk[1:]]
    if kind == "heading":
        text = HEADING_RE.match(blk[0]).group(2)
        rest = blk[1:]
        head = [f"- **{text}**"] if text else ["- **(section)**"]
        return head + [ln if ln[:1].isspace() else "  " + ln for ln in rest]
    first, rest = blk[0], blk[1:]
    return [f"- {first.strip()}"] + [ln if ln[:1].isspace() else "  " + ln for ln in rest]


def reshape_log(text):
    """Reshape a flat or prose update log to the shipped `okf-log.yaml` form: one title
    section, `## YYYY-MM-DD` groups newest first, bullets only (spec §7 step 3).

    Reshape, never delete. Every line of the input reaches the output: a `## <date> — <title>`
    heading keeps its title as the group's first bullet, `###` sub-sections and paragraphs
    become bullets of their own, and a wrapped bullet keeps its continuation lines. A log
    with no dated content at all is returned untouched rather than emitted empty — losing
    79 KB of history to a reshape is worse than a check finding saying the shape is wrong.
    """
    text = normalise_text(text)
    lines = text.split("\n")

    title = "Update log"
    start = 0
    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln)
        if m and len(m.group(1)) == 1:
            title = m.group(2) or title
            start = i + 1
            break

    groups = []          # [(date, [content lines])], in document order
    order = {}           # date -> index of its first group
    current = None
    preamble = []

    def open_group(date, seed_lines):
        nonlocal current
        if date in order:
            current = groups[order[date]][1]
        else:
            order[date] = len(groups)
            groups.append((date, []))
            current = groups[-1][1]
        current.extend(seed_lines)

    for raw in lines[start:]:
        m = HEADING_RE.match(raw)
        if m and len(m.group(1)) == 2:
            dm = DATE_RE.search(m.group(2))
            if dm:
                remainder = m.group(2).replace(dm.group(1), "", 1).strip(" —–-:·")
                open_group(dm.group(1), [f"- **{remainder}**"] if remainder else [])
                if preamble:
                    current[:0] = preamble
                    preamble = []
                continue
        entry = LOG_ENTRY_RE.match(raw.strip().lstrip("- "))
        if entry:
            open_group(entry.group(1), [f"- {entry.group(2)}"])
            if preamble:
                current[:0] = preamble
                preamble = []
            continue
        (current if current is not None else preamble).append(raw)

    if not groups:
        return text
    if preamble and any(ln.strip() for ln in preamble):
        groups[-1][1].extend(preamble)

    out = [f"# {title}", ""]
    for date, content in sorted(groups, key=lambda g: g[0], reverse=True):
        out.append(f"## {date}")
        bullets = [ln for kind, blk in _blocks(content) for ln in _as_bullet(kind, blk)]
        if not bullets:
            bullets = [f"- {date}: no entry recorded"]
        out.extend(bullets)
        out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def seed_log(date=MIGRATE_SEED_DATE):
    """The one-entry `log.md` a bundle starts from. `okf-log.yaml` requires at least one
    `## YYYY-MM-DD` group holding a bullet, so an empty log is not a valid log — a bundle
    that has never been written to still has to pass its own check (F3)."""
    return f"# Update log\n\n## {date}\n- bundle created\n"


def index_bullet(key, title, note=""):
    """One catalog bullet: `- [<title>](<key>.md) — <note>`, bundle-root-relative."""
    line = f"- [{title or key}]({key}.md)"
    return f"{line} — {note}" if note else line


def reshape_index(text, catalog=None):
    """Reshape an index.md into the shipped `okf-index.yaml` shape: flat `# <group>`
    sections, each carrying a bullet list, no nesting (`maxDepth: 1`).

    Two fixes over the line-based original: a heading whose section ends up with no
    bullets is dropped rather than emitted as a section the shipped schema rejects (F7),
    and every `stable` concept `catalog` names that no surviving bullet links gets one —
    `check` rule 6 requires exactly that, and a catalog the reshape leaves incomplete is a
    migration that cannot pass its own gate. An index with nothing to say is seeded rather
    than emitted empty.
    """
    text = normalise_text(text) if text is not None else ""
    fm_lines, body = _split_frontmatter(text)
    groups = {}
    order = []
    current = None
    section_lines = []

    def flush():
        if current is None:
            return
        # Bullet blocks only — the index is a catalog of link bullets (spec §7 step 3) —
        # but a bullet keeps every continuation and nested line it had, so a wrapped entry
        # is not cut at the wrap point the way `log.md`'s were.
        for kind, blk in _blocks(section_lines):
            if kind == "bullet":
                groups[current].extend(blk)

    for raw in body.split("\n"):
        m = HEADING_RE.match(raw)
        if m and not BULLET_RE.match(raw.strip()):
            flush()
            section_lines = []
            current = m.group(2).strip()
            if current not in groups:
                groups[current] = []
                order.append(current)
            continue
        section_lines.append(raw)
    flush()

    order = [name for name in order if groups[name]]

    linked = set()
    for name in order:
        for bullet in groups[name]:
            for _label, target in MD_LINK_RE.findall(bullet):
                path = target.split("#", 1)[0]
                if path and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", path):
                    linked.add(_resolve_key("", path))

    for key, title, note in (catalog or []):
        if key in linked:
            continue
        group = (key.split("/", 1)[0] + "/") if "/" in key else "Concepts"
        if group not in groups:
            groups[group] = []
            order.append(group)
        groups[group].append(index_bullet(key, title, note))
        linked.add(key)

    if not order:
        order = ["Index"]
        groups["Index"] = [index_bullet("log", "Update log", "this bundle's history")]

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
    """Prepend spec §3 Epic frontmatter to a pre-OKF epic-doc brief that has none.

    The migrated root is `status: stable` and cites the Notion epic URL from its own
    `Epic:` header line (spec §7 step 3). `retrieve` seeds on this document under
    `--filter 'status: stable'`, so a `draft` root is a root the retrieve cannot return —
    and `epic-doc`'s own template says `stable` too (F18).
    """
    body_text = normalise_text(body_text)
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
    notion_url = ""
    for ln in lines:
        m = re.match(r"^Epic:\s+(\S+)", ln.strip())
        if m:
            notion_url = m.group(1)
            break
    # json.dumps yields a double-quoted YAML scalar with `"` and `\` escaped — a title or
    # Goal sentence carrying either would otherwise break the frontmatter and fail the
    # post-apply schema gate, rolling back an otherwise valid migration.
    q_title, q_desc, q_url = json.dumps(title), json.dumps(description), json.dumps(notion_url or "")
    if notion_url:
        source = f'  - {{ id: epic, resource: {q_url}, title: {q_title} }}'
    else:
        source = f"  - {{ id: migrated, resource: epic/{filename} }}"
    fm = [
        "---",
        "type: Epic",
        f'title: {q_title}',
        f'description: {q_desc}',
        "status: stable",
        f"epic: {epic_id}",
        f'generated: {{ by: notion-dev:migrate, at: "{MIGRATE_AT_SENTINEL}" }}',
        "sources:",
        source,
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

    # step 3: concept frontmatter migration, log.md and index.md reshape. The catalog is
    # built from the text this step just produced — every `stable` concept needs an
    # `index.md` bullet for check rule 6, and the reshape below is the only place that can
    # add one without a second pass over the bundle.
    catalog = []
    if os.path.isdir(bundle):
        for dirpath, dirnames, filenames in os.walk(bundle):
            dirnames[:] = [dn for dn in dirnames if not dn.startswith(".")]
            for fn in sorted(filenames):
                if not fn.endswith(".md"):
                    continue
                fpath = os.path.join(dirpath, fn)
                rel_to_bundle = os.path.relpath(fpath, bundle)
                if dirpath == bundle and fn in ("log.md", "index.md"):
                    continue
                with open(fpath, "r", encoding="utf-8-sig") as f:
                    text = f.read()
                new_text = migrate_concept_text(text, rel_to_bundle,
                                                bundle_name=os.path.basename(bundle))
                result[os.path.join(bundle_rel, rel_to_bundle)] = new_text.encode("utf-8")
                key = rel_to_bundle[:-3].replace(os.sep, "/")
                if concept_frontmatter_value(new_text, "status") == "stable":
                    catalog.append((key, concept_frontmatter_value(new_text, "title") or key,
                                    concept_frontmatter_value(new_text, "description") or ""))

    log_path = os.path.join(bundle, "log.md")
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8-sig") as f:
            log_text = reshape_log(f.read())
    else:
        log_text = seed_log()
    result[os.path.join(bundle_rel, "log.md")] = log_text.encode("utf-8")

    index_path = os.path.join(bundle, "index.md")
    index_src = None
    if os.path.isfile(index_path):
        with open(index_path, "r", encoding="utf-8-sig") as f:
            index_src = f.read()

    # config (read once, used by steps 4 and 6)
    cfg = {}
    if config_path and os.path.isfile(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    # step 4: move epic-doc brief(s) into epic/, adding frontmatter. `epicDocs.dir` is
    # optional and both clients relied on the documented default, so an absent key means
    # `docs/epics`, not "skip the step" (F16, spec §7 step 4).
    epic_docs_dir = None
    if isinstance(cfg.get("epicDocs"), dict):
        epic_docs_dir = cfg["epicDocs"].get("dir")
    epic_docs_dir = epic_docs_dir or DEFAULT_EPIC_DOCS_DIR
    moved_briefs = []  # [(old_repo_rel, new_repo_rel)], for step 5
    abs_epics_dir = os.path.join(repo_root, epic_docs_dir)
    briefs = sorted(fn for fn in os.listdir(abs_epics_dir)
                    if fn.endswith(".md")) if os.path.isdir(abs_epics_dir) else []
    if not briefs:
        print(f"note: migrate step 4 moved no brief — {epic_docs_dir}/ "
              f"{'holds no .md file' if os.path.isdir(abs_epics_dir) else 'does not exist'}")
    if briefs:
        new_epic_dir_abs = os.path.join(repo_root, bundle_rel, "epic")
        # A brief whose destination already exists is a collision, never an overwrite: the
        # existing epic concept may carry knowledge the legacy brief does not, and a silent
        # replacement can still pass the post-apply check. Refuse before writing anything —
        # in the dry run as well — and tell the user to merge the two by hand.
        collisions = [fn for fn in briefs if os.path.exists(os.path.join(new_epic_dir_abs, fn))]
        if collisions:
            for fn in collisions:
                print(f"{bundle_rel}/epic/{fn}: migrate: collides with "
                      f"{os.path.relpath(os.path.join(abs_epics_dir, fn), repo_root)} — "
                      f"merge the two by hand, then re-run")
            sys.exit(1)
        for fn in briefs:
            src = os.path.join(abs_epics_dir, fn)
            with open(src, "r", encoding="utf-8-sig") as f:
                body = f.read()
            # 5(a): recompute this brief's own relative links before adding frontmatter.
            body = _rewrite_brief_links(body, abs_epics_dir, new_epic_dir_abs)
            new_body = add_epic_frontmatter(body, fn)
            new_rel = os.path.join(bundle_rel, "epic", fn)
            result[new_rel] = new_body.encode("utf-8")
            old_rel = os.path.relpath(src, repo_root)
            to_delete.append(old_rel)
            moved_briefs.append((old_rel, new_rel))
            # The brief is the bundle's root concept and `status: stable`, so it needs its
            # index bullet like any other — and it only exists after this step, which is why
            # the catalog is completed here and the index written below it.
            catalog.append(("epic/" + fn[:-3],
                            concept_frontmatter_value(new_body, "title") or fn[:-3],
                            concept_frontmatter_value(new_body, "description") or ""))

    result[os.path.join(bundle_rel, "index.md")] = (
        reshape_index(index_src, catalog).encode("utf-8"))

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
        # `dir` is written too (spec §7 step 6): without it a client whose bundle is not at
        # the default gets a config that silently points `check` at `knowledge/` (F17). Any
        # knowledge key the client already set — `retrieveBudget`, `warnBytes` — is carried
        # through: this step adds a block, it does not replace a hand-tuned one.
        kn_block = dict(new_cfg["knowledge"]) if isinstance(new_cfg.get("knowledge"), dict) else {}
        kn_block["dir"] = bundle_rel.replace(os.sep, "/")
        kn_block["extraTypes"] = extras
        new_cfg["knowledge"] = kn_block
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


def _config_warn_bytes(config_path):
    kn = load_config(config_path).get("knowledge")
    wb = kn.get("warnBytes") if isinstance(kn, dict) else None
    return wb if isinstance(wb, int) else 8192


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
    plugin_root = os.path.abspath(a.plugin_root or DEFAULT_PLUGIN_ROOT)
    if not os.path.isdir(os.path.join(plugin_root, KNOWLEDGE_IWE_REF)):
        die(f"--plugin-root {plugin_root}: no {KNOWLEDGE_IWE_REF}/ — migrate has nothing to install")
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
    # The client's own `warnBytes` — a migration is the one run that used to ignore it (F25).
    ca.warn_bytes = a.warn_bytes if a.warn_bytes is not None else _config_warn_bytes(config_path)
    # `run_check` reaches `die()` (SystemExit 2) when iwe fails or returns malformed JSON;
    # that path must restore the backup too, or a check that could not run leaves rewritten
    # concepts, installed `.iwe/` files and deleted briefs in place behind a non-zero exit.
    try:
        ok = run_check(ca)
    except SystemExit as e:
        restore()
        raise e
    except BaseException:
        restore()
        raise
    if ok:
        sys.exit(0)
    restore()
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="knowledge.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser(
        "check", help="check the bundle against the shipped OKF schemas and this script's rules")
    p_check.add_argument("--dir", default=None,
                         help="bundle root (default: knowledge.dir from --config, else knowledge)")
    p_check.add_argument("--plugin-root", default=None,
                         help="the notion-dev plugin directory the .iwe/ copy is compared against "
                              "(default: this script's own plugin)")
    p_check.add_argument("--extra-types", default=None,
                         help="comma-separated client type directories to accept beyond the "
                              "canonical set (default: knowledge.extraTypes from --config)")
    p_check.add_argument("--warn-bytes", type=int, default=None,
                         help="per-concept size above which check warns, never fails "
                              "(default: knowledge.warnBytes from --config, else 8192)")
    p_check.add_argument("--config", default=None,
                         help="notion-dev config to read dir/extraTypes/warnBytes from "
                              "(default: .claude/notion-dev.config.json at the git top level)")
    p_check.set_defaults(func=cmd_check)

    p_touched = sub.add_parser(
        "touched", help="list stable concepts whose applies_to globs the given commit touched")
    p_touched.add_argument("sha", help="the merge commit to intersect against")
    p_touched.add_argument("--dir", default="knowledge", help="bundle root (default: knowledge)")
    p_touched.set_defaults(func=cmd_touched)

    p_migrate = sub.add_parser(
        "migrate", help="move an existing client bundle onto this schema (spec §7 steps 2-7)")
    p_migrate.add_argument("--apply", action="store_true",
                           help="write the changes; without it the diff is printed and "
                                "nothing is written")
    p_migrate.add_argument("--dir", default="knowledge", help="bundle root (default: knowledge)")
    p_migrate.add_argument("--config", default=None,
                           help="path to .claude/notion-dev.config.json — step 6 rewrites it")
    p_migrate.add_argument("--plugin-root", default=None,
                           help="the notion-dev plugin directory the .iwe/ files are copied from "
                                "(default: this script's own plugin)")
    p_migrate.add_argument("--warn-bytes", type=int, default=None,
                           help="warnBytes for the post-apply check "
                                "(default: knowledge.warnBytes from --config, else 8192)")
    p_migrate.set_defaults(func=cmd_migrate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
