#!/bin/sh
# Block edits outside this builder's folder.
# Use as a PreToolUse hook on Edit|Write. Change the path below per builder.
path=$(jq -r '.tool_input.file_path')
case "$path" in
  */api/refunds/*) exit 0 ;;
  *) echo "Not your folder: $path" >&2
     exit 2 ;;
esac
