"""A stand-in for the `claude` CLI calls coordinator.py makes. Not a test module.

Driven by a JSON world file named by $NOTION_DEV_FAKE_WORLD:
  sessions      agents entries; each gets "_polls" while working
  calls         every argv this fake received, appended in order
  prefix_lines  printed before any --bg output (auth warnings, ANSI noise)
  settle_after  `agents` calls before a new session goes busy -> idle (default 1)
  settled_state the `state` a settled session reads (default "working": a session
                started with a slash command never reads "done" — spec fact 12)
  rm_noop       true: `rm` leaves the entry listed, so a resume forks
  agents_garbage true: `agents --json` prints non-JSON (an older CLI)
"""
import json
import os
import sys
import uuid

path = os.environ["NOTION_DEV_FAKE_WORLD"]
with open(path, encoding="utf-8") as stream:
    world = json.load(stream)
argv = sys.argv[1:]
world.setdefault("calls", []).append(argv)
sessions = world.setdefault("sessions", [])


def save():
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(world, stream)


def find(short):
    return next((s for s in sessions if s.get("id") == short), None)


def backgrounded(short):
    for line in world.get("prefix_lines", []):
        print(line)
    print("backgrounded · " + short)
    print("  claude attach " + short + "    open in this terminal")
    print("  claude logs " + short + "      show recent output")


def new_session(full):
    entry = {"id": full[:8], "sessionId": full, "kind": "background", "state": "working",
             "status": "busy", "_polls": 0}
    sessions.append(entry)
    return entry


if argv[:1] == ["agents"]:
    if world.get("agents_garbage"):
        save()
        print("oops")
        sys.exit(0)
    for entry in sessions:
        if entry.get("status") == "busy":
            entry["_polls"] = entry.get("_polls", 0) + 1
            if entry["_polls"] >= world.get("settle_after", 1):
                entry.update(status="idle", state=world.get("settled_state", "working"))
    save()
    print(json.dumps([{k: v for k, v in s.items() if not k.startswith("_")} for s in sessions]))
elif argv[:2] == ["--bg", "--resume"]:
    full = argv[2]
    if any(s.get("sessionId") == full for s in sessions):
        full = uuid.uuid4().hex[:8] + full[8:]          # still listed: a forked copy
    entry = new_session(full)
    save()
    backgrounded(entry["id"])
elif argv[:1] == ["--bg"]:
    entry = new_session(str(uuid.uuid4()))
    save()
    backgrounded(entry["id"])
elif argv[:1] == ["stop"]:
    entry = find(argv[1])
    if entry:
        entry.update(state="stopped", status=None, pid=None)
    save()
    print("stopped " + argv[1])
elif argv[:1] == ["rm"]:
    if not world.get("rm_noop"):
        sessions[:] = [s for s in sessions if s.get("id") != argv[1]]
    save()
    print("removed " + argv[1])
else:
    save()
    print("fake claude: unsupported " + repr(argv), file=sys.stderr)
    sys.exit(1)
