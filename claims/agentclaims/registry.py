"""The claims registry: a SQLite file shared by every worktree of a clone.

A ticket proposes a set of targets. The whole proposal is checked inside one
write transaction, so two agents proposing at the same moment can't both win.

  - No overlap with another ticket, and no CODEOWNERS owner to ask:
    accepted at once, with a lease.
  - Overlaps another ticket's claim: a request goes to that ticket's owner.
  - Touches code CODEOWNERS gives to someone else: a request goes to them.
  - A whole-file claim on a hot file: a request goes to the coordinator.

Requests nobody answers within the response window escalate to the
coordinator. Leases expire unless renewed, so an abandoned claim never
blocks anyone for long.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from .codeowners import CodeOwners
from .config import Config
from .targets import Target, covers, overlaps

ACTIVE = ("accepted", "pending")

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
  id INTEGER PRIMARY KEY,
  ticket TEXT NOT NULL,
  owner TEXT NOT NULL,
  status TEXT NOT NULL,          -- pending | accepted | declined | released | expired
  reason TEXT DEFAULT '',
  note TEXT DEFAULT '',
  created REAL NOT NULL,
  updated REAL NOT NULL,
  expires REAL
);
CREATE TABLE IF NOT EXISTS targets (
  proposal_id INTEGER NOT NULL REFERENCES proposals(id),
  target TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY,
  proposal_id INTEGER NOT NULL REFERENCES proposals(id),
  to_handle TEXT NOT NULL,
  kind TEXT NOT NULL,            -- overlap | codeowner | hot-file
  detail TEXT NOT NULL,
  about_proposal INTEGER,        -- the claim this one overlaps, for kind=overlap
  status TEXT NOT NULL,          -- open | granted | declined | closed
  escalated INTEGER DEFAULT 0,
  created REAL NOT NULL,
  resolved REAL,
  resolved_by TEXT,
  note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS grants (
  proposal_id INTEGER NOT NULL,
  other_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  ts REAL NOT NULL,
  ticket TEXT,
  kind TEXT NOT NULL,
  detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS requests_open ON requests(status, to_handle);
"""


class ClaimError(Exception):
    pass


@dataclass
class Result:
    proposal_id: int
    status: str
    ticket: str
    targets: list[str]
    waiting_on: list[dict] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Registry:
    def __init__(self, cfg: Config, now=time.time):
        self.cfg = cfg
        self.now = now
        self.owners = CodeOwners.load(cfg.root)
        path = cfg.db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    # ---------------------------------------------------------------- helpers

    @contextmanager
    def _write(self):
        """One write transaction. BEGIN IMMEDIATE takes the write lock up
        front, so check-then-insert can't interleave with another agent."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _event(self, ticket: str | None, kind: str, detail: str) -> None:
        self.db.execute(
            "INSERT INTO events(ts, ticket, kind, detail) VALUES (?,?,?,?)",
            (self.now(), ticket, kind, detail),
        )

    def _targets(self, proposal_id: int) -> list[Target]:
        rows = self.db.execute("SELECT target FROM targets WHERE proposal_id=?", (proposal_id,))
        return [Target.parse(r["target"]) for r in rows]

    def _granted(self, a: int, b: int) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM grants WHERE (proposal_id=? AND other_id=?) OR (proposal_id=? AND other_id=?)",
            (a, b, b, a),
        ).fetchone()
        return row is not None

    def _owns(self, handle: str, owners: list[str]) -> bool:
        return bool(self.cfg.members(handle) & set(owners))

    def _sweep(self) -> None:
        now = self.now()
        for row in self.db.execute(
            "SELECT id, ticket FROM proposals WHERE status='accepted' AND expires < ?", (now,)
        ).fetchall():
            self.db.execute("UPDATE proposals SET status='expired', updated=? WHERE id=?", (now, row["id"]))
            self._event(row["ticket"], "expired", f"claim #{row['id']} lease ran out")
        if self.cfg.coordinator:
            window = self.cfg.response_window_minutes * 60
            for row in self.db.execute(
                "SELECT r.id, p.ticket, r.to_handle FROM requests r JOIN proposals p ON p.id=r.proposal_id "
                "WHERE r.status='open' AND r.escalated=0 AND r.created < ?",
                (now - window,),
            ).fetchall():
                self.db.execute("UPDATE requests SET escalated=1 WHERE id=?", (row["id"],))
                self._event(
                    row["ticket"], "escalated",
                    f"request #{row['id']} to {row['to_handle']} unanswered, escalated to {self.cfg.coordinator}",
                )

    def sweep(self) -> None:
        with self._write():
            self._sweep()

    # ------------------------------------------------------------- proposing

    def propose(self, ticket: str, owner: str, targets: list[str], reason: str = "") -> Result:
        if not ticket:
            raise ClaimError("a claim needs a ticket id")
        if not owner:
            raise ClaimError("a claim needs an owner handle (use --as or CLAIMS_HANDLE)")
        parsed = sorted({Target.parse(t) for t in targets})
        if not parsed:
            raise ClaimError("a claim needs at least one target")
        for t in parsed:
            if t.func and not self.cfg.is_hot(t.path):
                raise ClaimError(
                    f"{t}: function-level claims are only for hot files. "
                    f"Claim the whole file {t.path} instead, or add it to hot_files in .claims.toml."
                )

        with self._write():
            self._sweep()
            now = self.now()
            cur = self.db.execute(
                "INSERT INTO proposals(ticket, owner, status, reason, created, updated) VALUES (?,?,?,?,?,?)",
                (ticket, owner, "pending", reason, now, now),
            )
            pid = cur.lastrowid
            self.db.executemany(
                "INSERT INTO targets(proposal_id, target) VALUES (?,?)", [(pid, str(t)) for t in parsed]
            )
            requests = self._requests_for(pid, ticket, owner, parsed)
            for req in requests:
                self.db.execute(
                    "INSERT INTO requests(proposal_id, to_handle, kind, detail, about_proposal, status, created) "
                    "VALUES (?,?,?,?,?,'open',?)",
                    (pid, req["to"], req["kind"], req["detail"], req.get("about"), now),
                )
            if requests:
                self._event(ticket, "pending", f"claim #{pid} waits on {', '.join(sorted({r['to'] for r in requests}))}")
                msg = (
                    "Paused. Do not edit these targets yet. "
                    + " ".join(r["detail"] + f" Request sent to {r['to']}." for r in requests)
                )
                return Result(pid, "pending", ticket, [str(t) for t in parsed], requests, msg)
            self._accept(pid, ticket)
            return Result(pid, "accepted", ticket, [str(t) for t in parsed], [], "Accepted. You may edit these targets.")

    def _requests_for(self, pid: int, ticket: str, owner: str, parsed: list[Target]) -> list[dict]:
        out: dict[tuple, dict] = {}
        active = self.db.execute(
            f"SELECT id, ticket, owner, status FROM proposals WHERE status IN {ACTIVE} AND ticket != ? AND id != ?",
            (ticket, pid),
        ).fetchall()
        for t in parsed:
            hit = False
            for other in active:
                for ot in self._targets(other["id"]):
                    if overlaps(t, ot) and not self._granted(pid, other["id"]):
                        hit = True
                        key = ("overlap", other["owner"], other["id"])
                        out.setdefault(key, {
                            "to": other["owner"], "kind": "overlap", "about": other["id"],
                            "detail": (f"{t} is already claimed by {other['ticket']} ({other['status']})." if t == ot
                                       else f"{t} overlaps {ot}, claimed by {other['ticket']} ({other['status']})."),
                        })
            if hit:
                continue
            if t.is_folder is False and t.func is None and self.cfg.is_hot(t.path):
                if self.cfg.coordinator and not self._owns(owner, [self.cfg.coordinator]):
                    out.setdefault(("hot", t.path), {
                        "to": self.cfg.coordinator, "kind": "hot-file",
                        "detail": f"{t} is a hot file; whole-file claims need the coordinator. "
                                  f"Claim single functions as {t.path}::<name> to skip this.",
                    })
                    continue
            owners = self.owners.owners(t.path)
            if owners and not self._owns(owner, owners):
                out.setdefault(("owner", owners[0], t.path), {
                    "to": owners[0], "kind": "codeowner",
                    "detail": f"{t} is owned by {' '.join(owners)} in CODEOWNERS.",
                })
        return list(out.values())

    def _accept(self, pid: int, ticket: str) -> None:
        now = self.now()
        self.db.execute(
            "UPDATE proposals SET status='accepted', updated=?, expires=? WHERE id=?",
            (now, now + self.cfg.lease_minutes * 60, pid),
        )
        self._event(ticket, "accepted", f"claim #{pid}: {', '.join(str(t) for t in self._targets(pid))}")

    # -------------------------------------------------------------- answering

    def _can_answer(self, req, handle: str) -> bool:
        me = self.cfg.members(handle)
        if req["to_handle"] in me:
            return True
        return bool(self.cfg.coordinator) and self.cfg.coordinator in me

    def resolve(self, request_id: int, handle: str, grant: bool, note: str = "") -> dict:
        with self._write():
            self._sweep()
            req = self.db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if req is None:
                raise ClaimError(f"no request #{request_id}")
            if req["status"] != "open":
                raise ClaimError(f"request #{request_id} is already {req['status']}")
            if not self._can_answer(req, handle):
                raise ClaimError(f"{handle} can't answer a request sent to {req['to_handle']}")
            prop = self.db.execute("SELECT * FROM proposals WHERE id=?", (req["proposal_id"],)).fetchone()
            now = self.now()
            self.db.execute(
                "UPDATE requests SET status=?, resolved=?, resolved_by=?, note=? WHERE id=?",
                ("granted" if grant else "declined", now, handle, note, request_id),
            )
            if not grant:
                self.db.execute(
                    "UPDATE proposals SET status='declined', note=?, updated=? WHERE id=?", (note, now, prop["id"])
                )
                self.db.execute(
                    "UPDATE requests SET status='closed' WHERE proposal_id=? AND status='open'", (prop["id"],)
                )
                self._event(prop["ticket"], "declined", f"claim #{prop['id']} declined by {handle}: {note}")
                return {"proposal_id": prop["id"], "status": "declined", "note": note}
            if req["about_proposal"]:
                self.db.execute(
                    "INSERT INTO grants(proposal_id, other_id) VALUES (?,?)", (prop["id"], req["about_proposal"])
                )
            self._event(prop["ticket"], "granted", f"request #{request_id} granted by {handle}")
            still_open = self.db.execute(
                "SELECT COUNT(*) FROM requests WHERE proposal_id=? AND status='open'", (prop["id"],)
            ).fetchone()[0]
            if still_open == 0 and prop["status"] == "pending":
                self._accept(prop["id"], prop["ticket"])
                return {"proposal_id": prop["id"], "status": "accepted", "note": note}
            return {"proposal_id": prop["id"], "status": prop["status"], "note": note}

    # ------------------------------------------------------------- lifecycle

    def release(self, ticket: str) -> int:
        with self._write():
            now = self.now()
            ids = [r["id"] for r in self.db.execute(
                f"SELECT id FROM proposals WHERE ticket=? AND status IN {ACTIVE}", (ticket,)
            )]
            for pid in ids:
                self.db.execute("UPDATE proposals SET status='released', updated=? WHERE id=?", (now, pid))
                self.db.execute("UPDATE requests SET status='closed' WHERE proposal_id=? AND status='open'", (pid,))
            if ids:
                self._event(ticket, "released", f"{len(ids)} claim(s) released")
            return len(ids)

    def renew(self, ticket: str) -> int:
        with self._write():
            self._sweep()
            now = self.now()
            cur = self.db.execute(
                "UPDATE proposals SET expires=?, updated=? WHERE ticket=? AND status='accepted'",
                (now + self.cfg.lease_minutes * 60, now, ticket),
            )
            return cur.rowcount

    # ---------------------------------------------------------------- reading

    def held(self, ticket: str) -> list[Target]:
        rows = self.db.execute(
            "SELECT id FROM proposals WHERE ticket=? AND status='accepted' AND expires >= ?", (ticket, self.now())
        ).fetchall()
        out: list[Target] = []
        for r in rows:
            out.extend(self._targets(r["id"]))
        return sorted(set(out))

    def status(self, ticket: str | None = None) -> list[dict]:
        if ticket:
            rows = self.db.execute("SELECT * FROM proposals WHERE ticket=? ORDER BY id", (ticket,)).fetchall()
        else:
            rows = self.db.execute(
                f"SELECT * FROM proposals WHERE status IN {ACTIVE} ORDER BY id"
            ).fetchall()
        out = []
        for p in rows:
            reqs = self.db.execute("SELECT * FROM requests WHERE proposal_id=? ORDER BY id", (p["id"],)).fetchall()
            out.append({
                "id": p["id"], "ticket": p["ticket"], "owner": p["owner"], "status": p["status"],
                "targets": [str(t) for t in self._targets(p["id"])], "note": p["note"],
                "expires": p["expires"],
                "requests": [
                    {"id": r["id"], "to": self.cfg.coordinator if r["escalated"] and r["status"] == "open" else r["to_handle"],
                     "kind": r["kind"], "detail": r["detail"], "status": r["status"],
                     "escalated": bool(r["escalated"]), "note": r["note"]}
                    for r in reqs
                ],
            })
        return out

    def inbox(self, handle: str) -> list[dict]:
        me = self.cfg.members(handle)
        is_coord = bool(self.cfg.coordinator) and self.cfg.coordinator in me
        rows = self.db.execute(
            "SELECT r.*, p.ticket, p.owner AS requester, p.reason FROM requests r "
            "JOIN proposals p ON p.id=r.proposal_id WHERE r.status='open' ORDER BY r.id"
        ).fetchall()
        return [
            {"id": r["id"], "ticket": r["ticket"], "from": r["requester"], "kind": r["kind"],
             "detail": r["detail"], "reason": r["reason"], "escalated": bool(r["escalated"])}
            for r in rows
            if r["to_handle"] in me or (is_coord and (r["escalated"] or r["to_handle"] == self.cfg.coordinator))
        ]

    def feed(self, limit: int = 30) -> list[dict]:
        rows = self.db.execute("SELECT * FROM events ORDER BY ts DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ----------------------------------------------------------------- checks

    def check_edit(self, ticket: str, path: str, funcs: set[str] | None) -> tuple[bool, str]:
        """Is `ticket` allowed to make this edit right now?

        funcs is the set of changed functions for a hot file, or None when we
        only check at file level.
        """
        with self._write():
            self._sweep()
        held = self.held(ticket)
        if self.cfg.is_hot(path) and funcs is not None:
            missing = sorted(f for f in funcs if not any(covers(c, path, f) for c in held))
            if not missing:
                return True, ""
            names = ", ".join(f"{path}::{f}" for f in missing)
            return False, (
                f"No accepted claim for {names} on {ticket}. "
                f"Run: claims propose {' '.join(f'{path}::{f}' for f in missing if f != '<module>') or path} "
                f"and wait for acceptance."
            )
        if any(covers(c, path) for c in held):
            return True, ""
        expired = self.db.execute(
            "SELECT 1 FROM proposals WHERE ticket=? AND status='expired' LIMIT 1", (ticket,)
        ).fetchone()
        hint = " Your earlier claim expired; run: claims renew" if expired else ""
        return False, f"No accepted claim for {path} on {ticket}. Run: claims propose {path} and wait for acceptance.{hint}"

    def export(self, ticket: str) -> dict:
        return {
            "ticket": ticket,
            "targets": [str(t) for t in self.held(ticket)],
            "hot_files": list(self.cfg.hot_files),
        }

    def dumps(self, obj) -> str:
        return json.dumps(obj, indent=2, default=str)
