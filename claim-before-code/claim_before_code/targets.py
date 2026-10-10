"""What a claim covers: a folder, a file, or one function inside a file.

    src/promotions/                    a folder and everything under it
    src/pricing/calculate.py           a whole file
    src/pricing/calculate.py::calculate_total
                                       one function (or class) in a file
"""

from __future__ import annotations

from dataclasses import dataclass

SEP = "::"
MODULE = "<module>"  # code in a file that sits outside every function


@dataclass(frozen=True, order=True)
class Target:
    path: str
    func: str | None = None

    @classmethod
    def parse(cls, text: str) -> "Target":
        text = text.strip()
        path, _, func = text.partition(SEP)
        path = path.strip().replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        path = path.lstrip("/")
        if not path:
            raise ValueError(f"empty path in claim target {text!r}")
        func = func.strip() or None
        if func and path.endswith("/"):
            raise ValueError(f"a folder can't have a function: {text!r}")
        return cls(path, func)

    @property
    def is_folder(self) -> bool:
        return self.path.endswith("/")

    def __str__(self) -> str:
        return f"{self.path}{SEP}{self.func}" if self.func else self.path


def _func_match(a: str, b: str) -> bool:
    """`Order` covers `Order.total`; equal names match."""
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def overlaps(a: Target, b: Target) -> bool:
    if a.is_folder or b.is_folder:
        return a.path.startswith(b.path) or b.path.startswith(a.path)
    if a.path != b.path:
        return False
    if a.func is None or b.func is None:
        return True
    return _func_match(a.func, b.func)


def covers(claim: Target, path: str, func: str | None = None) -> bool:
    """Does `claim` allow an edit to `path` (and, for hot files, `func`)?"""
    if claim.is_folder:
        return path.startswith(claim.path)
    if claim.path != path:
        return False
    if claim.func is None:
        return True
    if func is None or func == MODULE:
        return False
    return func == claim.func or func.startswith(claim.func + ".")
