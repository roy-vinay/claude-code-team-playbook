"""Read GitHub's CODEOWNERS file so claims know who owns what.

Follows GitHub's rules closely enough for routing: patterns work like
.gitignore, and the last matching line wins.
"""

from __future__ import annotations

import re
from pathlib import Path

LOCATIONS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")


def _to_regex(pattern: str) -> re.Pattern:
    anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
    pat = pattern.lstrip("/")
    directory = pat.endswith("/")
    pat = pat.rstrip("/")
    out = ""
    i = 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        elif pat[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pat[i])
            i += 1
    prefix = "^" if anchored else "^(?:.*/)?"
    # A pattern also matches everything inside a matching directory.
    suffix = "/.*$" if directory else "(?:/.*)?$"
    return re.compile(prefix + out + suffix)


class CodeOwners:
    def __init__(self, rules: list[tuple[re.Pattern, list[str]]]):
        self.rules = rules

    @classmethod
    def load(cls, root: Path) -> "CodeOwners":
        for loc in LOCATIONS:
            path = root / loc
            if path.exists():
                return cls.parse(path.read_text())
        return cls([])

    @classmethod
    def parse(cls, text: str) -> "CodeOwners":
        rules = []
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            rules.append((_to_regex(parts[0]), parts[1:]))
        return cls(rules)

    def owners(self, path: str) -> list[str]:
        """Owners of a repo-relative path. A folder path ends with '/'."""
        probe = path + "_" if path.endswith("/") else path
        found: list[str] = []
        for rx, owners in self.rules:
            if rx.match(probe):
                found = owners
        return found
