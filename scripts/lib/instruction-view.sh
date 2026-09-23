# Test-only views of split instruction owners. Never loaded by the plugin/host.
# Existing region/uniqueness assertions still check every moved guard; routing and
# bounded read sets are tested separately in test_handoffs.py.
INSTRUCTION_VIEW_DIR=$(mktemp -d) || exit 1
trap 'rm -f -- "$INSTRUCTION_VIEW_DIR"/*.md; rmdir -- "$INSTRUCTION_VIEW_DIR"' EXIT
instruction_view() {
  local kind=$1 out="$INSTRUCTION_VIEW_DIR/$1.md" root=plugins/notion-dev/skills
  case "$kind" in
    knowledge)
      cat "$root/knowledge/references/common.md" "$root/knowledge/references/retrieve.md" \
          "$root/knowledge/references/capture.md" "$root/knowledge/references/curate.md" \
          "$root/knowledge/references/migrate.md" > "$out" ;;
    epic-doc)
      cat "$root/epic-doc/references/format.md" "$root/epic-doc/references/read.md" \
          "$root/epic-doc/references/bootstrap.md" "$root/epic-doc/references/refresh.md" \
          "$root/epic-doc/references/write-path.md" "$root/epic-doc/references/record.md" \
          "$root/epic-doc/references/output.md" "$root/epic-doc/references/note.md" > "$out" ;;
    ticket-system)
      cat "$root/ticket-system/references/operations.md" > "$out"
      sed -n '/^## ID normalization/,$p' "$root/ticket-system/SKILL.md" >> "$out" ;;
    ticket-reads)
      cat "$root/ticket-system/references/query.md" "$root/ticket-system/references/fetch-ticket.md" \
          "$root/ticket-system/references/find-epics.md" "$root/ticket-system/references/epic-context.md" \
          "$root/ticket-system/references/list-children.md" > "$out" ;;
    *) return 1 ;;
  esac
  printf '%s\n' "$out"
}
