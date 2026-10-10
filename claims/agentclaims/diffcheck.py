"""Pull request check: compare what a branch actually changed with its claim.

Works from the registry when it can, or from a manifest written by
`claims export`, so it can run in CI where the registry isn't available.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import Config
from .functions import changed_functions
from .targets import MODULE, Target, covers


def _git(root: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return out.stdout if out.returncode == 0 else ""


def changed_files(root: Path, base: str) -> list[str]:
    out = _git(root, "diff", "--name-only", f"{base}...HEAD")
    return [line for line in out.splitlines() if line.strip()]


def check(cfg: Config, ticket: str, targets: list[Target], base: str) -> list[str]:
    """Return a list of violations; empty means the diff stays inside the claim."""
    problems = []
    merge_base = _git(cfg.root, "merge-base", base, "HEAD").strip()
    for path in changed_files(cfg.root, base):
        if cfg.is_always_allowed(path):
            continue
        if cfg.is_hot(path):
            old = _git(cfg.root, "show", f"{merge_base}:{path}", check=False)
            new = _git(cfg.root, "show", f"HEAD:{path}", check=False)
            funcs = changed_functions(path, old, new)
            if funcs is not None:
                for f in sorted(funcs):
                    if not any(covers(t, path, f) for t in targets):
                        label = "code outside any function" if f == MODULE else f
                        problems.append(f"{path}::{f}  ({label} changed, not in the claim for {ticket})")
                continue
        if not any(covers(t, path) for t in targets):
            problems.append(f"{path}  (changed, not in the claim for {ticket})")
    return problems


def load_manifest(path: Path) -> tuple[str, list[Target]]:
    data = json.loads(path.read_text())
    return data["ticket"], [Target.parse(t) for t in data["targets"]]
