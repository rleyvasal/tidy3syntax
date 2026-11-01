"""The rewrite of one cell: repairs, then ownership, then reinterpretations.

Phase A runs every repair by name. Phase B parses the result and reads who
owns each call that a reinterpretation would touch; a cell that does not
parse keeps Python's meaning. Phase C applies the reinterpretations whose
calls the dialect's package owns, and those of packages the caller listed in
``always`` (an explicit scope the user turned on).
"""

from __future__ import annotations

import ast
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from tidysyntax.dialect import Dialect
from tidysyntax.ownership import owned_calls
from tidysyntax.repairs import formula_text, is_shell_cell, repair
from tidysyntax.scanner import (
    Call,
    Spans,
    apply,
    calls,
    keyword,
    strip_span,
    top_level_tildes,
)


def rewrite(
    source: str,
    dialects: Sequence[Dialect],
    context: Mapping[str, Any] | None = None,
    always: Collection[str] = (),
) -> str:
    """The cell *source* as Python, with every dialect's R syntax rewritten.

    *context* answers who owns a name the cell does not bind: an IPython
    namespace, or ``imported_names(...)`` of earlier cells. *always* lists
    packages whose reinterpretations apply whoever owns the call.
    """
    if is_shell_cell(source):
        return source
    source = repair(source, dialects)
    return reinterpret(source, dialects, context, always)


def reinterpret(
    source: str,
    dialects: Sequence[Dialect],
    context: Mapping[str, Any] | None = None,
    always: Collection[str] = (),
) -> str:
    """Phases B and C on text the repairs have already run on."""
    active = [d for d in dialects if d.reinterprets]
    if not active or ("^" not in source and "~" not in source):
        return source
    names = frozenset().union(*(d.power_calls | d.unary_formula_calls for d in active))
    spans = Spans.of(source)
    found = calls(source, names, spans)
    if not found:
        return source
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        owned: dict[int, str] = {}
    else:
        owned = owned_calls(source, tree, active, context, names)

    def applies(call: Call, field: str) -> bool:
        for dialect in active:
            if call.name in getattr(dialect, field) and (
                owned.get(call.name_end) == dialect.package or dialect.package in always
            ):
                return True
        return False

    edits = _powers(source, spans, found, lambda call: applies(call, "power_calls"))
    edits += _unary_formulas(source, active, found, lambda call: applies(call, "unary_formula_calls"))
    return apply(source, edits)


def _powers(source: str, spans: Spans, found: list[Call], applies) -> list[tuple[int, int, str]]:
    """``^`` → ``**`` where the nearest enclosing power call applies."""
    edits = []
    candidates = [call for call in found if "^" in source[call.open : call.close]]
    for i in spans.code_indices():
        if source[i] != "^" or source[i + 1 : i + 2] == "=":
            continue
        enclosing = [call for call in candidates if call.open < i < call.close]
        if enclosing and applies(max(enclosing, key=lambda call: call.open)):
            edits.append((i, i + 1, "**"))
    return edits


def _unary_formulas(source: str, dialects: Sequence[Dialect], found: list[Call], applies) -> list[tuple[int, int, str]]:
    """``facet_wrap(~cyl)`` → ``facet_wrap('~cyl')`` in unary-formula calls that apply."""
    keywords = frozenset().union(*(d.formula_keywords for d in dialects))
    edits = []
    for call in found:
        if not applies(call):
            continue
        strip = all(
            d.formula_backticks == "strip" for d in dialects if call.name in d.unary_formula_calls
        )
        for a, b in call.arguments:
            named = keyword(source[a:b])
            if named is not None:
                if named[0] not in keywords:
                    continue
                a += named[1]
            a, b = strip_span(source, a, b)
            tildes = top_level_tildes(source[a:b])
            if tildes and not any(is_binary for _, is_binary in tildes):
                edits.append((a, b, repr(formula_text(source[a:b], strip))))
    return edits
