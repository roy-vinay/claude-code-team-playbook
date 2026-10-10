"""Command line: `claims <command>`. Run `claims -h` for the list."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import Config, current_handle, current_ticket
from .registry import ClaimError, Registry


def _ticket(cfg: Config, args) -> str:
    t = getattr(args, "ticket", None) or current_ticket(cfg)
    if not t:
        raise ClaimError("no ticket: pass --ticket, set CLAIMS_TICKET, or use a feat/<TICKET>-name branch")
    return t


def _handle(cfg: Config, args) -> str:
    h = current_handle(getattr(args, "as_handle", None), cfg.root)
    if not h:
        raise ClaimError("who are you? pass --as @handle, set CLAIMS_HANDLE, or run: git config claims.handle @you")
    return h


def _ago(ts: float | None) -> str:
    if not ts:
        return ""
    mins = int((ts - time.time()) / 60)
    return f"lease {mins} min left" if mins >= 0 else "lease expired"


def _print_status(rows: list[dict]) -> None:
    if not rows:
        print("No claims.")
        return
    for p in rows:
        extra = _ago(p["expires"]) if p["status"] == "accepted" else ""
        print(f"#{p['id']}  {p['ticket']}  {p['owner']}  {p['status'].upper()}  {extra}".rstrip())
        for t in p["targets"]:
            print(f"      {t}")
        for r in p["requests"]:
            esc = " (escalated)" if r["escalated"] else ""
            print(f"      request #{r['id']} to {r['to']}{esc}: {r['status']}. {r['detail']}")
            if r["note"]:
                print(f"         note: {r['note']}")
        if p["note"] and not any(r["note"] == p["note"] for r in p["requests"]):
            print(f"      note: {p['note']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="claims", description="Claim code before your agent edits it.")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("propose", help="claim targets for a ticket")
    p.add_argument("targets", nargs="+", help="folder/, file, or hot/file.py::function")
    p.add_argument("--ticket")
    p.add_argument("--as", dest="as_handle")
    p.add_argument("--reason", default="")

    for name, helptext in [("status", "show a ticket's claims"), ("renew", "extend leases"),
                           ("release", "release claims after merge"), ("export", "write the claim manifest for CI")]:
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--ticket")
        if name == "status":
            s.add_argument("--all", action="store_true", help="every active claim")
        if name == "export":
            s.add_argument("-o", "--output", help="file to write (default: stdout)")

    s = sub.add_parser("inbox", help="requests waiting on you")
    s.add_argument("--as", dest="as_handle")

    for name in ("grant", "decline"):
        s = sub.add_parser(name, help=f"{name} a request")
        s.add_argument("request", type=int)
        s.add_argument("--as", dest="as_handle")
        s.add_argument("--note", default="")

    s = sub.add_parser("feed", help="recent activity")
    s.add_argument("-n", type=int, default=30)

    sub.add_parser("sweep", help="expire leases and escalate stale requests")
    sub.add_parser("hook", help="Claude Code PreToolUse hook (reads stdin)")
    sub.add_parser("mcp", help="run the stdio MCP server")

    s = sub.add_parser("check-diff", help="fail if the branch changed code outside its claim")
    s.add_argument("--ticket")
    s.add_argument("--base", default="origin/main")
    s.add_argument("--manifest", help="claim manifest from `claims export` (for CI)")

    args = ap.parse_args(argv)

    if args.cmd == "hook":
        from .hook import main as hook_main
        return hook_main()
    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main
        return mcp_main()

    try:
        cfg = Config.load()
        if args.cmd == "check-diff":
            from .diffcheck import check, load_manifest
            if args.manifest:
                ticket, targets = load_manifest(Path(args.manifest))
            else:
                ticket = _ticket(cfg, args)
                targets = Registry(cfg).held(ticket)
            problems = check(cfg, ticket, targets, args.base)
            if args.json:
                print(json.dumps({"ticket": ticket, "violations": problems}, indent=2))
            elif problems:
                print(f"{ticket} changed code outside its accepted claim:")
                for line in problems:
                    print(f"  {line}")
                print("Amend the claim (claims propose ...) or move these changes to the right ticket.")
            else:
                print(f"{ticket}: every change is inside the accepted claim.")
            return 1 if problems else 0

        reg = Registry(cfg)
        out = None
        if args.cmd == "propose":
            res = reg.propose(_ticket(cfg, args), _handle(cfg, args), args.targets, args.reason)
            out = res.to_dict()
            if not args.json:
                print(f"#{res.proposal_id} {res.status.upper()}: {res.message}")
                return 0 if res.status == "accepted" else 3
        elif args.cmd == "status":
            out = reg.status(None if args.all else _ticket(cfg, args))
            if not args.json:
                _print_status(out)
                return 0
        elif args.cmd == "inbox":
            out = reg.inbox(_handle(cfg, args))
            if not args.json:
                if not out:
                    print("Nothing waiting on you.")
                for r in out:
                    esc = " [escalated]" if r["escalated"] else ""
                    print(f"request #{r['id']}{esc}  {r['ticket']} ({r['from']}): {r['detail']}")
                    if r["reason"]:
                        print(f"    why: {r['reason']}")
                    print(f"    answer: claims grant {r['id']}  |  claims decline {r['id']} --note \"...\"")
                return 0
        elif args.cmd in ("grant", "decline"):
            out = reg.resolve(args.request, _handle(cfg, args), args.cmd == "grant", args.note)
            if not args.json:
                print(f"Request #{args.request} {'granted' if args.cmd == 'grant' else 'declined'}. Claim #{out['proposal_id']} is now {out['status']}.")
                return 0
        elif args.cmd == "renew":
            n = reg.renew(_ticket(cfg, args))
            out = {"renewed": n}
        elif args.cmd == "release":
            n = reg.release(_ticket(cfg, args))
            out = {"released": n}
        elif args.cmd == "export":
            out = reg.export(_ticket(cfg, args))
            if args.output:
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output).write_text(json.dumps(out, indent=2) + "\n")
                print(f"Wrote {args.output}")
                return 0
        elif args.cmd == "feed":
            out = reg.feed(args.n)
            if not args.json:
                for e in out:
                    stamp = time.strftime("%H:%M", time.localtime(e["ts"]))
                    print(f"{stamp}  {e['ticket'] or '-':10}  {e['kind']:9}  {e['detail']}")
                return 0
        elif args.cmd == "sweep":
            reg.sweep()
            out = {"ok": True}
        print(json.dumps(out, indent=2, default=str))
        return 0
    except (ClaimError, ValueError, RuntimeError) as e:
        print(f"claims: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
