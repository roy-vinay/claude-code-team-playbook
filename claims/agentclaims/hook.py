"""Claude Code PreToolUse hook: block edits that no accepted claim covers.

Register it on Edit|Write|MultiEdit. Exit code 2 stops the edit and shows
the message to the agent. This is best-effort, since an agent can still
change files through the shell; the pull request check is the backstop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import Config, current_ticket
from .functions import changed_functions
from .registry import Registry


def _apply_edit(text: str, old: str, new: str, replace_all: bool = False) -> str:
    if old == "":
        return new if text == "" else text + new
    return text.replace(old, new) if replace_all else text.replace(old, new, 1)


def proposed_content(tool: str, inp: dict, current: str) -> str | None:
    if tool == "Write":
        return inp.get("content", "")
    if tool == "Edit":
        return _apply_edit(current, inp.get("old_string", ""), inp.get("new_string", ""), inp.get("replace_all", False))
    if tool == "MultiEdit":
        text = current
        for e in inp.get("edits", []):
            text = _apply_edit(text, e.get("old_string", ""), e.get("new_string", ""), e.get("replace_all", False))
        return text
    return None


def evaluate(payload: dict, cfg: Config | None = None, registry: Registry | None = None) -> tuple[int, str]:
    """Returns (exit_code, message). 0 allows the edit, 2 blocks it."""
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}
    raw_path = inp.get("file_path") or inp.get("notebook_path")
    if tool not in ("Edit", "Write", "MultiEdit") or not raw_path:
        return 0, ""
    cfg = cfg or Config.load(payload.get("cwd"))
    rel = cfg.relpath(raw_path)
    if rel is None or rel.startswith(".git/") or cfg.is_always_allowed(rel):
        return 0, ""
    ticket = current_ticket(cfg, payload.get("cwd"))
    if not ticket:
        return 2, (
            "No ticket for this session, so edits are blocked. Start work with /start <TICKET>, "
            "or work on a branch named like feat/<TICKET>-short-name."
        )
    reg = registry or Registry(cfg)
    funcs = None
    if cfg.is_hot(rel):
        full = cfg.root / rel
        current = full.read_text() if full.exists() else ""
        new = proposed_content(tool, inp, current)
        if new is not None:
            funcs = changed_functions(rel, current, new)
    ok, msg = reg.check_edit(ticket, rel, funcs)
    return (0, "") if ok else (2, msg)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("claims hook: could not read hook input", file=sys.stderr)
        return 0
    code, msg = evaluate(payload)
    if msg:
        print(msg, file=sys.stderr)
    return code
