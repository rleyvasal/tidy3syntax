"""Reading cells that are not yet Python: strings, comments, calls, arguments.

Every rewrite acts on text Python cannot parse yet (that is why it is
needed), so the scanner works on characters, not on ``tokenize`` or
``ast``. It knows string literals (single, triple, with any prefix),
comments, and backtick names, and finds calls by name and their top-level
arguments outside them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass


def string_end(source: str, i: int) -> int:
    """The index just past the string literal whose opening quote is at ``source[i]``."""
    quote = source[i]
    if source.startswith(quote * 3, i):
        j = i + 3
        while j < len(source):
            if source[j] == "\\":
                j += 2
                continue
            if source.startswith(quote * 3, j):
                return j + 3
            j += 1
        return len(source)
    j = i + 1
    while j < len(source) and source[j] not in (quote, "\n"):
        j += 2 if source[j] == "\\" else 1
    return min(j + 1, len(source))


@dataclass(frozen=True)
class Spans:
    """Where a cell's code is: everything outside string literals and comments.

    Backtick names count as code, so rewrites can find them, but a backtick
    never opens a string: ```a b``` is one name, and a quote inside it ends
    nothing.
    """

    code: tuple[tuple[int, int], ...]

    @classmethod
    def of(cls, source: str) -> Spans:
        spans: list[tuple[int, int]] = []
        start = i = 0
        n = len(source)
        while i < n:
            ch = source[i]
            if ch in "'\"":
                spans.append((start, i))
                i = start = string_end(source, i)
            elif ch == "#":
                spans.append((start, i))
                newline = source.find("\n", i)
                i = start = n if newline < 0 else newline
            elif ch == "`":
                close = source.find("`", i + 1)
                newline = source.find("\n", i + 1)
                i = n if close < 0 else close + 1 if newline < 0 or close < newline else i + 1
            else:
                i += 1
        spans.append((start, n))
        return cls(tuple((a, b) for a, b in spans if b > a))

    def __contains__(self, index: int) -> bool:
        return any(a <= index < b for a, b in self.code)

    def code_indices(self, start: int = 0, end: int | None = None) -> Iterable[int]:
        for a, b in self.code:
            lo, hi = max(a, start), b if end is None else min(b, end)
            yield from range(lo, hi)


@dataclass(frozen=True)
class Call:
    """A call found by name: ``name`` as written (with any ``module.`` prefix), and where its parentheses are."""

    name: str
    prefix: str | None
    name_end: int  # just past the function name
    open: int  # index of "("
    close: int  # index of ")"
    arguments: tuple[tuple[int, int], ...]  # top-level argument spans, between the parentheses


def calls(source: str, names: Iterable[str], spans: Spans | None = None) -> list[Call]:
    """Calls to any of *names*, bare or prefixed (``ta.filter(``), outside strings and comments.

    A call whose closing parenthesis is missing is left out. Calls nested in
    another call's arguments are found too, in source order.
    """
    wanted = sorted(set(names), key=len, reverse=True)
    if not wanted:
        return []
    spans = spans or Spans.of(source)
    pattern = re.compile(r"(?<![\w.])(?:([A-Za-z_]\w*)\s*\.\s*)?(" + "|".join(map(re.escape, wanted)) + r")\s*\(")
    found = []
    for match in pattern.finditer(source):
        if match.start() not in spans:
            continue
        open_at = match.end() - 1
        parsed = arguments(source, open_at, spans)
        if parsed is None:
            continue
        close, args = parsed
        found.append(Call(match.group(2), match.group(1), match.end(2), open_at, close, tuple(args)))
    return found


def arguments(source: str, open_at: int, spans: Spans | None = None) -> tuple[int, list[tuple[int, int]]] | None:
    """The index of the ``)`` matching ``source[open_at]``, and the top-level argument spans between them.

    An empty call has no arguments; a trailing comma adds none.
    """
    spans = spans or Spans.of(source)
    depth = 0
    start = open_at + 1
    found: list[tuple[int, int]] = []
    in_name = False  # inside a backtick name, where brackets and commas are text
    for i in spans.code_indices(open_at):
        ch = source[i]
        if ch == "`":
            in_name = not in_name
        elif in_name:
            continue
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                if source[start:i].strip():
                    found.append((start, i))
                return i, found
        elif ch == "," and depth == 1:
            found.append((start, i))
            start = i + 1
    return None


# Words after which a "~" is unary ("a and ~b"), not a formula's separator.
_OPERATOR_WORDS = frozenset(
    {"and", "or", "not", "in", "is", "if", "else", "lambda", "return", "yield", "await", "for"}
)


def top_level_tildes(text: str) -> list[tuple[int, bool]]:
    """Each ``~`` at the top level of *text*, and whether it is binary.

    Python's ``~`` is unary only, so a ``~`` after an operand (a name, a
    number, a string, a backtick name, a closing bracket, or R's ``.``) can
    only be a formula's separator: ``y ~ x``, ``. ~ cyl``. ``~x`` and
    ``a and ~b`` are unary. Adapted from tidy3's ``_binary_tildes``.
    """
    found: list[tuple[int, bool]] = []
    depth = 0
    after_operand = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in "'\"":
            i = string_end(text, i)
            after_operand = True
            continue
        if c == "`":
            close = text.find("`", i + 1)
            i = n if close < 0 else close + 1
            after_operand = True
            continue
        if c == "#":
            newline = text.find("\n", i)
            i = n if newline < 0 else newline
            continue
        if c.isalnum() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_."):
                j += 1
            after_operand = text[i:j] not in _OPERATOR_WORDS
            i = j
            continue
        if c == ".":
            after_operand = True  # R's "." in ". ~ cyl"
        elif c in "([{":
            depth += 1
            after_operand = False
        elif c in ")]}":
            depth -= 1
            after_operand = True
        elif c == "~":
            if depth == 0:
                found.append((i, after_operand))
            after_operand = False
        elif not c.isspace():
            after_operand = False
        i += 1
    return found


def keyword(text: str) -> tuple[str, int] | None:
    """``(name, index after "=")`` when an argument's text is ``name = value``; ``None`` otherwise."""
    match = re.match(r"\s*([A-Za-z_]\w*)\s*=(?!=)", text)
    return (match.group(1), match.end()) if match else None


def strip_span(source: str, a: int, b: int) -> tuple[int, int]:
    """*a*..*b* without its leading and trailing whitespace."""
    text = source[a:b]
    return a + len(text) - len(text.lstrip()), b - (len(text) - len(text.rstrip()))


def apply(source: str, edits: Iterable[tuple[int, int, str]]) -> str:
    """Replace each ``(start, end, text)`` span; the spans must not overlap."""
    for start, end, text in sorted(edits, reverse=True):
        source = source[:start] + text + source[end:]
    return source
