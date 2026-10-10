"""Work out which functions an edit changes.

Function-level claims only make sense if we can tell which function a change
lands in. Python is parsed exactly with `ast`. JavaScript and TypeScript use a
best-effort scan for top-level functions, arrow functions and classes. Any
change outside every function is reported as MODULE, which needs a
whole-file claim.
"""

from __future__ import annotations

import ast
import re

from .targets import MODULE

Spans = dict[str, tuple[int, int]]  # name -> (start offset, end offset)


def _line_offsets(text: str) -> list[int]:
    offs = [0]
    for line in text.splitlines(keepends=True):
        offs.append(offs[-1] + len(line))
    return offs


def _python_spans(text: str) -> Spans | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    offs = _line_offsets(text)
    spans: Spans = {}

    def start_of(node) -> int:
        first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        return offs[first - 1]

    def visit(body, prefix=""):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                spans[prefix + node.name] = (start_of(node), offs[node.end_lineno])
            elif isinstance(node, ast.ClassDef):
                # The class gets a span of its own (its body outside the
                # methods), and each method gets a qualified span.
                name = prefix + node.name
                spans[name] = (start_of(node), offs[node.end_lineno])
                visit(node.body, name + ".")

    visit(tree.body)
    return spans


_JS_HEAD = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:"
    r"(?:async\s+)?function\s*\*?\s*(?P<f>[A-Za-z_$][\w$]*)"
    r"|class\s+(?P<c>[A-Za-z_$][\w$]*)"
    r"|(?:const|let|var)\s+(?P<v>[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s+)?"
    r"(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>)"
    r")",
    re.M,
)


def _match_brace(text: str, i: int) -> int:
    """Index just past the brace that closes the one at text[i]."""
    depth = 0
    quote = None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif text.startswith("//", i):
            nl = text.find("\n", i)
            i = len(text) if nl < 0 else nl
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _js_spans(text: str) -> Spans:
    spans: Spans = {}
    pos = 0
    for m in _JS_HEAD.finditer(text):
        if m.start() < pos:
            continue  # nested inside the previous function
        name = m.group("f") or m.group("c") or m.group("v")
        rest = text[m.end():]
        if m.group("v") and not rest.lstrip(" \t").startswith(("{", "function")):
            # Arrow function with an expression body: ends at the line end.
            nl = text.find("\n", m.end())
            end = len(text) if nl < 0 else nl + 1
        else:
            brace = text.find("{", m.end())
            if brace < 0:
                continue
            end = _match_brace(text, brace)
        spans[name] = (m.start(), end)
        pos = end
    return spans


def spans_for(path: str, text: str) -> Spans | None:
    """Function spans, or None when the language isn't understood."""
    if path.endswith((".py", ".pyi")):
        return _python_spans(text)
    if path.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        return _js_spans(text)
    return None


def _outside(text: str, spans: Spans) -> str:
    keep, pos = [], 0
    # Only top-level spans: skip spans nested in another span.
    tops = []
    for s, e in sorted(spans.values()):
        if tops and s < tops[-1][1]:
            continue
        tops.append((s, e))
    for s, e in tops:
        keep.append(text[pos:s])
        pos = e
    keep.append(text[pos:])
    return "".join(keep)


def changed_functions(path: str, old: str, new: str) -> set[str] | None:
    """Names of functions that differ between old and new.

    Returns None when the file's language isn't supported or doesn't parse,
    so callers can fall back to requiring a whole-file claim.
    """
    if old == new:
        return set()
    a = spans_for(path, old)
    b = spans_for(path, new)
    if a is None or b is None:
        return None
    changed: set[str] = set()
    for name in set(a) | set(b):
        if name not in a or name not in b:
            changed.add(name)
            continue
        if old[slice(*a[name])] != new[slice(*b[name])]:
            changed.add(name)
    # A method change also changes its class span; report only the method.
    for name in list(changed):
        if any(other.startswith(name + ".") for other in changed):
            if _class_shell_same(name, a, b, old, new):
                changed.discard(name)
    if _outside(old, a).strip() != _outside(new, b).strip():
        changed.add(MODULE)
    return changed


def _class_shell_same(name: str, a: Spans, b: Spans, old: str, new: str) -> bool:
    if name not in a or name not in b:
        return False

    def shell(text: str, spans: Spans) -> str:
        s, e = spans[name]
        body = text[s:e]
        inner = {k: (x - s, y - s) for k, (x, y) in spans.items() if k.startswith(name + ".")}
        return _outside(body, inner)

    return shell(old, a).strip() == shell(new, b).strip()
