"""Repo discovery and the .cbc.toml config file."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULTS = {
    "coordinator": "",
    "response_window_minutes": 60,
    "lease_minutes": 240,
    "hot_files": [],
    "always_allowed": ["specs/", "rework-log.md", ".claims/"],
    "ticket_pattern": r"(?:^|/)([A-Z][A-Z0-9]+-\d+)",
    "teams": {},
}


def _git(args: list[str], cwd: Path) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"git {' '.join(args)} failed")
    return out.stdout.strip()


def find_root(start: str | os.PathLike | None = None) -> Path:
    start = Path(start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    return Path(_git(["rev-parse", "--show-toplevel"], start))


@dataclass
class Config:
    root: Path
    coordinator: str = ""
    response_window_minutes: int = 60
    lease_minutes: int = 240
    hot_files: list[str] = field(default_factory=list)
    always_allowed: list[str] = field(default_factory=list)
    ticket_pattern: str = DEFAULTS["ticket_pattern"]
    teams: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: str | os.PathLike | None = None) -> "Config":
        root = find_root(root)
        data = dict(DEFAULTS)
        path = root / ".cbc.toml"
        if path.exists():
            data.update(tomllib.loads(path.read_text()))
        known = {k: data[k] for k in DEFAULTS}
        return cls(root=root, **known)

    @property
    def db_path(self) -> Path:
        """One database per clone, shared by every worktree of that clone."""
        env = os.environ.get("CBC_DB")
        if env:
            return Path(env)
        common = Path(_git(["rev-parse", "--git-common-dir"], self.root))
        if not common.is_absolute():
            common = (self.root / common).resolve()
        return common / "cbc.db"

    def is_hot(self, path: str) -> bool:
        return any(fnmatch.fnmatchcase(path, pat) for pat in self.hot_files)

    def is_always_allowed(self, path: str) -> bool:
        for pat in self.always_allowed:
            if pat.endswith("/") and path.startswith(pat):
                return True
            if fnmatch.fnmatchcase(path, pat):
                return True
        return False

    def members(self, handle: str) -> set[str]:
        """A handle plus every team it belongs to."""
        out = {handle}
        for team, people in self.teams.items():
            if handle in people:
                out.add(team)
        return out

    def ticket_from(self, text: str) -> str | None:
        m = re.search(self.ticket_pattern, text or "")
        return m.group(1) if m else None

    def relpath(self, path: str) -> str | None:
        """Repo-relative POSIX path, or None if the path is outside the repo."""
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        try:
            return p.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return None


def current_ticket(cfg: Config, cwd: str | None = None) -> str | None:
    """CBC_TICKET wins; otherwise read it from the branch name."""
    env = os.environ.get("CBC_TICKET")
    if env:
        return env
    try:
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], Path(cwd or cfg.root))
    except RuntimeError:
        return None
    return cfg.ticket_from(branch)


def current_handle(explicit: str | None = None, cwd: Path | None = None) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get("CBC_HANDLE")
    if env:
        return env
    try:
        return _git(["config", "cbc.handle"], cwd or Path.cwd()) or None
    except RuntimeError:
        return None
