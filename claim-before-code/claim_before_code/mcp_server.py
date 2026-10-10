"""A stdio MCP server, so any MCP client (Claude Code, Codex, Cursor) can
propose and check claims. Standard library only: newline-delimited JSON-RPC.
"""

from __future__ import annotations

import json
import sys

from . import __version__
from .config import Config, current_handle, current_ticket
from .registry import ClaimError, Registry

PROTOCOL = "2025-06-18"

TOOLS = [
    {
        "name": "cbc_propose",
        "description": (
            "Claim the folders, files, or hot-file functions you are about to change, BEFORE editing. "
            "If the result is 'pending', do not edit those targets; tell the user who was asked and wait."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "targets": {"type": "array", "items": {"type": "string"},
                            "description": "e.g. ['src/promotions/', 'src/pricing/calculate.py::apply_discount']"},
                "reason": {"type": "string", "description": "One line on why you need these."},
                "ticket": {"type": "string", "description": "Ticket id. Defaults to the branch's ticket."},
            },
            "required": ["targets"],
        },
    },
    {
        "name": "cbc_status",
        "description": "Show this ticket's claims, or every active claim if all=true.",
        "inputSchema": {"type": "object", "properties": {
            "ticket": {"type": "string"}, "all": {"type": "boolean"}}},
    },
    {
        "name": "cbc_check_file",
        "description": "Check whether this ticket may edit a file (file-level check).",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string"}, "ticket": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "cbc_renew",
        "description": "Extend the lease on this ticket's accepted claims.",
        "inputSchema": {"type": "object", "properties": {"ticket": {"type": "string"}}},
    },
    {
        "name": "cbc_release",
        "description": "Release this ticket's claims once its work is merged or abandoned.",
        "inputSchema": {"type": "object", "properties": {"ticket": {"type": "string"}}},
    },
    {
        "name": "cbc_inbox",
        "description": "List open requests waiting on a person (the code owner or coordinator).",
        "inputSchema": {"type": "object", "properties": {"handle": {"type": "string"}}},
    },
]


class Server:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config.load()
        self.reg = Registry(self.cfg)

    def _ticket(self, args: dict) -> str:
        t = args.get("ticket") or current_ticket(self.cfg)
        if not t:
            raise ClaimError("no ticket: pass ticket, set CBC_TICKET, or use a feat/<TICKET>-name branch")
        return t

    def call(self, name: str, args: dict):
        if name == "cbc_propose":
            handle = current_handle(cwd=self.cfg.root)
            return self.reg.propose(self._ticket(args), handle, args["targets"], args.get("reason", "")).to_dict()
        if name == "cbc_status":
            return self.reg.status(None if args.get("all") else self._ticket(args))
        if name == "cbc_check_file":
            rel = self.cfg.relpath(args["path"]) or args["path"]
            ok, msg = self.reg.check_edit(self._ticket(args), rel, None)
            return {"allowed": ok, "message": msg}
        if name == "cbc_renew":
            return {"renewed": self.reg.renew(self._ticket(args))}
        if name == "cbc_release":
            return {"released": self.reg.release(self._ticket(args))}
        if name == "cbc_inbox":
            handle = args.get("handle") or current_handle(cwd=self.cfg.root)
            return self.reg.inbox(handle)
        raise ClaimError(f"unknown tool {name}")

    def handle(self, msg: dict) -> dict | None:
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            return None  # notification
        if method == "initialize":
            result = {
                "protocolVersion": msg.get("params", {}).get("protocolVersion", PROTOCOL),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "claim-before-code", "version": __version__},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            p = msg.get("params", {})
            try:
                out = self.call(p.get("name"), p.get("arguments") or {})
                result = {"content": [{"type": "text", "text": json.dumps(out, indent=2, default=str)}]}
            except (ClaimError, ValueError, KeyError) as e:
                result = {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
        elif method == "ping":
            result = {}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> int:
    server = Server()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = server.handle(json.loads(line))
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0
