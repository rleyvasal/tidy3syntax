"""Repairs: rewrites of text that is not Python.

Each repair changes only text that is a syntax error, so no valid program
can mean anything else by it, and it runs by the call's name, whoever owns
the call. Each one leaves a cell that parses unchanged, and each is
idempotent; the tests check both on every case and on the standard
library's own source.

Adapted from tidy3's ``masking.py`` (``rewrite_bang_not``,
``rewrite_formula_rules``, ``rewrite_keywords_before_positional``,
``rewrite_backtick_keyword_assigns``), tidy3a's ``jupyter.py``, plot3's
``masking.py`` (facet formulas) and stats3's ``masking.py``
(``quote_formulas``), all MIT.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Sequence

from tidysyntax.dialect import Dialect
from tidysyntax.placeholders import ASSIGN, NAME
from tidysyntax.scanner import (
    Spans,
    apply,
    calls,
    keyword,
    strip_span,
    top_level_tildes,
)

_BACKTICK = re.compile(r"`([^`\n]+)`")
# Placeholders a package's own pass may have left before tidysyntax ran (tidy3, plot3), and tidysyntax's own.
_NAME_CALL = re.compile(r"__(?:r_name|tidy3_bt|plot3_bt)__\((['\"])(.*?)\1\)")


def _union(dialects: Iterable[Dialect], field: str) -> frozenset[str]:
    return frozenset().union(*(getattr(d, field) for d in dialects))


def is_shell_cell(source: str) -> bool:
    """A cell of IPython shell lines (``!cmd``) and comments only; no repair touches it."""
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    return bool(lines) and lines[0].startswith("!") and all(line.startswith(("!", "#")) for line in lines)


def _parses(text: str) -> bool:
    try:
        ast.parse(text.strip(), mode="eval")
    except SyntaxError:
        return False
    return True


# ── formulas ─────────────────────────────────────────────────────────────────


def quote_formulas(source: str, dialects: Sequence[Dialect]) -> str:
    """``lm(y ~ x)`` → ``lm('y ~ x')`` in formula calls; ``facet_wrap(~`my col`)`` → ``facet_wrap('~my col')``.

    A formula with a left side (``y ~ x``, ``. ~ cyl``) is not Python, so it
    is quoted in any formula call. A one-sided formula is quoted here only
    when its text does not parse either (``` ~`my col` ```); ``~x`` is
    bitwise not, and is left for the reinterpretation of unary-formula calls.
    Keyword arguments are formulas only for the dialects' formula keywords.
    """
    binary = _union(dialects, "formula_calls")
    unary = _union(dialects, "unary_formula_calls")
    if "~" not in source or not (binary | unary):
        return source
    spans = Spans.of(source)
    keywords = _union(dialects, "formula_keywords")
    edits = []
    for call in calls(source, binary | unary, spans):
        for a, b in call.arguments:
            named = keyword(source[a:b])
            if named is not None:
                if named[0] not in keywords:
                    continue
                a += named[1]
            a, b = strip_span(source, a, b)
            text = source[a:b]
            tildes = top_level_tildes(text)
            if not tildes:
                continue
            has_left = any(is_binary for _, is_binary in tildes)
            if has_left and call.name not in binary:
                continue
            if not has_left and (call.name not in unary or _parses(text)):
                continue
            edits.append((a, b, repr(formula_text(text, _strips(dialects, call.name)))))
    return _outermost_last(edits, source)


def _strips(dialects: Sequence[Dialect], name: str) -> bool:
    listing = [d for d in dialects if name in d.formula_calls or name in d.unary_formula_calls]
    return bool(listing) and all(d.formula_backticks == "strip" for d in listing)


def formula_text(text: str, strip_backticks: bool) -> str:
    """A formula's text as a string: whitespace collapsed, backtick names kept or stripped."""
    text = _NAME_CALL.sub(lambda m: f"`{m.group(2)}`", text)
    if strip_backticks:
        text = text.replace("`", "")
    return " ".join(text.split())


def rule_pairs(source: str, dialects: Sequence[Dialect]) -> str:
    """``case_when(x > 6 ~ "big")`` → ``case_when((x > 6, "big"))`` in rule calls.

    ``~`` before a value stays negation (``~is_na(x) ~ 0`` is the rule
    ``(~is_na(x), 0)``); keyword arguments and ``*args`` are left alone.
    Raises SyntaxError, naming the function, for a rule that is not exactly
    ``left ~ right``, and for a rule where a rule-after-column call expects
    its column.
    """
    names = _union(dialects, "rule_calls")
    if "~" not in source or not names:
        return source
    after_column = _union(dialects, "rule_after_column")
    return _until_settled(lambda source: _rules_pass(source, names, after_column), source)


def _rules_pass(source: str, names: frozenset[str], after_column: frozenset[str]) -> str:
    spans = Spans.of(source)
    edits = []
    for call in calls(source, names, spans):
        for position, (a, b) in enumerate(call.arguments):
            text = source[a:b]
            if keyword(text) or text.lstrip().startswith("*"):
                continue
            separators = [i for i, is_binary in top_level_tildes(text) if is_binary]
            if not separators:
                continue
            shown = text.strip()
            if position == 0 and call.name in after_column:
                raise SyntaxError(f"{call.name}() takes the column first, then rules: {shown!r} is a rule, not a column")
            if len(separators) > 1:
                raise SyntaxError(
                    f"{call.name}() rule {shown!r} has more than one ~; write one `left ~ right` per rule, "
                    "with parentheses around anything that itself contains ~"
                )
            left, right = text[: separators[0]].strip(), text[separators[0] + 1 :].strip()
            if not left or not right:
                raise SyntaxError(f"{call.name}() rule {shown!r} needs a value on both sides of ~")
            a, b = strip_span(source, a, b)
            edits.append((a, b, f"({left}, {right})"))
    return _outermost_last(edits, source)


# ── negation ─────────────────────────────────────────────────────────────────


def negation(source: str, dialects: Sequence[Dialect]) -> str:
    """``filter(!(x > 1))`` → ``filter(~(x > 1))`` inside negation calls.

    Also at the start of a line inside the call. ``!=``, strings, comments,
    and shell lines outside a call (``!pip install …``, ``x = !ls``) stay.
    """
    names = _union(dialects, "negation_calls")
    if "!" not in source or not names:
        return source
    spans = Spans.of(source)
    inside = [(call.open, call.close) for call in calls(source, names, spans)]
    edits = [
        (i, i + 1, "~")
        for i in spans.code_indices()
        if source[i] == "!" and source[i + 1 : i + 2] != "=" and any(a < i < b for a, b in inside)
    ]
    return apply(source, edits)


# ── assignments in the order written ─────────────────────────────────────────


def backtick_assignments(source: str) -> str:
    """`` `new col` = value `` as a call argument → ``__r_assign__('new col', (value))``.

    A backtick name is not a valid keyword, so the assignment becomes a
    positional placeholder, valid next to other arguments. ``==``, ``<=``,
    ``>=``, ``!=`` and ``=~`` are not assignments.
    """
    if "`" not in source or "=" not in source:
        return source

    def one_pass(source: str) -> str:
        spans = Spans.of(source)
        edits = []
        for match in re.finditer(r"`([^`\n]+)`\s*=(?![=~])", source):
            if match.start() not in spans or not re.search(r"[(,]\s*\Z", source[: match.start()]):
                continue
            end = _value_end(source, match.end(), spans)
            value = source[match.end() : end].strip()
            if end is not None and value:
                edits.append((match.start(), end, f"{ASSIGN}({match.group(1)!r}, ({value}))"))
        return _outermost_last(edits, source)

    return _until_settled(one_pass, source)


def _outermost_last(edits: list[tuple[int, int, str]], source: str) -> str:
    """Apply the edits that overlap no later one; an outer edit around an inner one waits for the next pass."""
    kept: list[tuple[int, int, str]] = []
    for edit in sorted(edits, reverse=True):
        if all(edit[1] <= other[0] or edit[0] >= other[1] for other in kept):
            kept.append(edit)
    return apply(source, kept)


def _until_settled(one_pass, source: str) -> str:
    for _ in range(100):
        rewritten = one_pass(source)
        if rewritten == source:
            return source
        source = rewritten
    return source


def _value_end(source: str, start: int, spans: Spans) -> int | None:
    """Where an argument's value that starts at *start* ends: the next top-level ``,`` or the call's ``)``."""
    depth = 0
    for i in spans.code_indices(start):
        ch = source[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif ch == "," and depth == 0:
            return i
    return None


def keywords_before_positional(source: str, dialects: Sequence[Dialect]) -> str:
    """``group_by(w = bins(t), lat)`` → ``group_by(__r_assign__('w', (bins(t))), lat)`` in ordered calls.

    R takes ``name = value`` before a positional argument and Python does
    not, so each such keyword becomes the ordered placeholder. Keywords
    after the last positional argument, ``*args`` and ``**kwargs``, and the
    dialects' settings are left alone, so valid Python is unchanged.
    """
    names = _union(dialects, "ordered_calls")
    if "=" not in source or not names:
        return source
    settings = _union(dialects, "settings")
    return _until_settled(lambda source: _keywords_pass(source, names, settings), source)


def _keywords_pass(source: str, names: frozenset[str], settings: frozenset[str]) -> str:
    edits = []
    for call in calls(source, names):
        named = [keyword(source[a:b]) for a, b in call.arguments]
        positional = [
            i for i, ((a, b), kw) in enumerate(zip(call.arguments, named))
            if kw is None and not source[a:b].lstrip().startswith("*")
        ]
        if not positional:
            continue
        for (a, b), kw in zip(call.arguments[: positional[-1]], named):
            if kw is None or kw[0] in settings:
                continue
            value = source[a + kw[1] : b].strip()
            a, b = strip_span(source, a, b)
            edits.append((a, b, f"{ASSIGN}({kw[0]!r}, ({value}))"))
    return _outermost_last(edits, source)


# ── backtick names ───────────────────────────────────────────────────────────


def backticks(source: str) -> str:
    """`` `First Name` `` → ``__r_name__('First Name')``, outside strings and comments."""
    if "`" not in source:
        return source
    spans = Spans.of(source)
    edits = [
        (m.start(), m.end(), f"{NAME}({m.group(1)!r})")
        for m in _BACKTICK.finditer(source)
        if m.start() in spans
    ]
    return apply(source, edits)


def repair(source: str, dialects: Sequence[Dialect]) -> str:
    """Every repair, in order: formulas, rules, negation, backtick assignments, the dialects'
    own stages, keywords before positional arguments, then backtick names."""
    if is_shell_cell(source):
        return source
    source = quote_formulas(source, dialects)
    source = rule_pairs(source, dialects)
    source = negation(source, dialects)
    source = backtick_assignments(source)
    for dialect in dialects:
        for stage in dialect.stages:
            source = stage(source)
    source = keywords_before_positional(source, dialects)
    return backticks(source)
