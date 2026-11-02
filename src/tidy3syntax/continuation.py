"""Continuation lines: a line that starts with an operator continues the statement above.

R chains a pipe or a plot over lines with the operator first::

    tidy(cars)                      ggplot(df, aes(x = wt, y = mpg))
    >> filter(mpg > 20)             + geom_point()
    >> select(mpg, wt)              + theme_bw()

To Python each such line is a statement of its own. A line that starts with
``>>`` is a syntax error, so joining it is a repair, by the dialects'
``pipe_operators``. So is a ``+`` line indented more than the statement it
continues (an unexpected indent). An unindented ``+ geom_point()`` line is
valid Python, a unary plus, so joining it is a reinterpretation: it joins
only when the call after ``+`` is one of a dialect's ``layer_calls`` owned
by that dialect's package, and the statement above starts with such a call
(``ggplot(...)``), or ends a pipe whose last step is one
(``df >> ggplot(...)``), or starts with a variable not known to hold
something else (a plot made earlier). After ``x = 2`` nothing joins.

Joined lines get parentheses on the lines as typed, so line numbers in
errors match the cell. A pipe Python still cannot parse once joined (a
missing argument, an unclosed bracket) is joined with backslashes instead,
so Python reports the real error rather than an unexpected indent.

Adapted from tidy3's ``partial_run.py`` (``_wrap_pipe_statements``,
``join_broken_pipe``) and plot3's ``join_layer_lines`` (MIT).
"""

from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from tidy3syntax.dialect import Dialect
from tidy3syntax.ownership import Owners, module_of

_OPENERS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = set(_OPENERS.values())
_SKIP = {
    tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER,
}
# Statements that start a block or leave one: never the head a continuation line joins.
_KEYWORDS = frozenset({
    "if", "elif", "else", "for", "while", "with", "def", "class", "try", "except", "finally",
    "return", "import", "from", "async", "await", "match", "case", "raise", "del", "pass",
    "break", "continue", "global", "nonlocal", "assert", "yield", "lambda",
})


@dataclass
class _Statement:
    """One logical line: its first and last physical rows, and its tokens (of the re-indented text)."""

    first: int
    last: int
    tokens: list[tokenize.TokenInfo] = field(default_factory=list)


def _line_starts(lines: list[str]) -> list[tuple[int, bool]]:
    """Bracket depth, and whether a string is open, where each line starts: a
    light scan (comments, quotes, triple quotes, escapes), enough to tell
    which lines start a statement before the cell can be tokenized."""
    starts: list[tuple[int, bool]] = []
    depth, quote = 0, ""
    for line in lines:
        starts.append((depth, bool(quote)))
        i = 0
        while i < len(line):
            if quote:
                if line[i] == "\\":
                    i += 2
                elif line.startswith(quote, i):
                    i += len(quote)
                    quote = ""
                else:
                    i += 1
                continue
            ch = line[i]
            if ch == "#":
                break
            if ch in "\"'":
                quote = line[i : i + 3] if line[i : i + 3] in ('"""', "'''") else ch
                i += len(quote)
                continue
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(depth - 1, 0)
            i += 1
        if quote in ('"', "'"):  # an unclosed one-line string ends here
            quote = ""
    return starts


def _leads(stripped: str, operators: Collection[str]) -> bool:
    return any(stripped.startswith(op) for op in operators)


def _continuation_indents(lines: list[str], operators: Collection[str]) -> list[int | None]:
    """For each line that may continue a statement (it starts with one of
    *operators* outside brackets and strings), the indentation of the
    statement it continues; ``None`` for other lines. That is 0 at the top
    of a cell and the block's indentation inside a function or loop."""
    out: list[int | None] = []
    anchor = 0
    for line, (depth, in_string) in zip(lines, _line_starts(lines)):
        stripped = line.lstrip()
        if depth or in_string or not stripped or stripped.startswith("#"):
            out.append(None)
            continue
        if _leads(stripped, operators):
            out.append(anchor)
            continue
        anchor = len(line) - len(stripped)
        out.append(None)
    return out


def _statements(lines: list[str], indents: list[int | None], operators: Collection[str]) -> list[_Statement] | None:
    """The logical lines of the cell, with continuation lines re-indented to
    the statement they continue (or to column 0 inside brackets), so they
    never trip indentation checks; ``None`` if the cell cannot be tokenized."""
    analysed = "\n".join(
        (" " * indent + line.lstrip()) if indent is not None
        else (line.lstrip() if _leads(line.lstrip(), operators) else line)
        for line, indent in zip(lines, indents)
    )
    statements: list[_Statement] = []
    current: _Statement | None = None
    try:
        for token in tokenize.generate_tokens(io.StringIO(analysed).readline):
            if token.type in _SKIP:
                if token.type == tokenize.NEWLINE and current is not None:
                    statements.append(current)
                    current = None
                continue
            if current is None:
                current = _Statement(token.start[0], token.end[0])
            current.last = token.end[0]
            current.tokens.append(token)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    if current is not None:
        statements.append(current)
    return statements


def _top_level(tokens: list[tokenize.TokenInfo], string: str) -> list[int]:
    """Indexes of *string* tokens outside brackets."""
    found, depth = [], 0
    for index, token in enumerate(tokens):
        if token.string in _OPENERS:
            depth += 1
        elif token.string in _CLOSERS:
            depth -= 1
        elif depth == 0 and token.type == tokenize.OP and token.string == string:
            found.append(index)
    return found


def _value_start(tokens: list[tokenize.TokenInfo]) -> int:
    """Index of the first token of the value: after a top-level ``=``, else 0."""
    equals = _top_level(tokens, "=")
    return equals[0] + 1 if equals and equals[0] + 1 < len(tokens) else 0


def _unwrapped(tokens: list[tokenize.TokenInfo]) -> list[tokenize.TokenInfo]:
    """*tokens* without parentheses that wrap all of them: ``(df >> ggplot())`` is ``df >> ggplot()``."""
    while len(tokens) > 2 and tokens[0].string == "(" and tokens[-1].string == ")":
        depth = 0
        for index, token in enumerate(tokens):
            if token.string in _OPENERS:
                depth += 1
            elif token.string in _CLOSERS:
                depth -= 1
                if depth == 0:
                    break
        if index != len(tokens) - 1:
            break
        tokens = tokens[1:-1]
    return tokens


def _assigned_value(tokens: list[tokenize.TokenInfo]) -> tuple[int, int]:
    """Where the statement's value starts: after a top-level ``=``, else the statement's start."""
    return tokens[_value_start(tokens)].start


class _Layers:
    """Whether an unindented ``+ name(...)`` line may join the statement above it (see the module's docstring)."""

    def __init__(
        self,
        source: str,
        lines: list[str],
        indents: list[int | None],
        dialects: Sequence[Dialect],
        context: Mapping[str, Any] | None,
        always: Collection[str],
    ):
        self.dialects = [d for d in dialects if d.layer_calls]
        self.always = always
        # For ownership, the cell as separate statements: '+' lines at their anchor, '>>' lines joined by
        # then. A cell that still does not parse gets no reinterpretation.
        dedented = "\n".join(
            (" " * indent + line.lstrip()) if indent is not None else line for line, indent in zip(lines, indents)
        )
        try:
            tree = ast.parse(dedented)
        except (SyntaxError, ValueError):
            self.owners = None
        else:
            self.owners = Owners(tree, context, self.dialects)

    def _module(self, name: str, row: int) -> str | None:
        return self.owners.module(name, (row, 0)) if self.owners is not None else None

    def _owned(self, name: str, row: int, dialect: Dialect) -> bool:
        if dialect.package in self.always:
            return True
        return self.owners is not None and dialect.owns_module(self._module(name, row))

    def operand(self, tokens: list[tokenize.TokenInfo]) -> Dialect | None:
        """The dialect whose layer the ``+`` line adds, if its call is that dialect's and owned."""
        if len(tokens) < 2 or tokens[1].type != tokenize.NAME:
            return None
        name, row = tokens[1].string, tokens[1].start[0]
        for dialect in self.dialects:
            if name in dialect.layer_calls and self._owned(name, row, dialect):
                return dialect
        return None

    def head(self, tokens: list[tokenize.TokenInfo], dialect: Dialect) -> bool:
        """Whether the statement above can take *dialect*'s layers."""
        value = _unwrapped(tokens[_value_start(tokens) :])
        pipes = _top_level(value, ">>")
        rest = value[pipes[-1] + 1 :] if pipes else value
        while rest and rest[0].string == "(":
            rest = rest[1:]
        if not rest or rest[0].type != tokenize.NAME or rest[0].string in _KEYWORDS:
            return False
        name, row = rest[0].string, rest[0].start[0]
        if len(rest) > 1 and rest[1].string in ("(", "."):
            return self._owned(name, row, dialect)  # ggplot(...), p3.ggplot(...), df >> ggplot(...)
        if dialect.package in self.always:
            return True
        if self.owners is None:
            return False
        # A variable: refused only when its value is known not to be the dialect's.
        bound = [module for end, module in self.owners.bindings.get(name, ()) if end <= (row, 0)]
        if bound:
            return bound[-1] is None or dialect.owns_module(bound[-1])
        context = self.owners.context
        if context is not None and name in context:
            return dialect.owns_module(module_of(context[name]))
        return True


def join(
    source: str,
    dialects: Sequence[Dialect],
    context: Mapping[str, Any] | None = None,
    always: Collection[str] = (),
) -> str:
    """*source* with each statement and its continuation lines in one pair of
    parentheses; unchanged when nothing joins or the result would not parse.

    Pipes are joined first, a repair that needs no parse; then ``+`` lines,
    whose ownership is read from the cell with its pipes already joined.
    """
    pipes = frozenset().union(*(d.pipe_operators for d in dialects))
    source = _join(source, dialects, pipes, False, context, always)
    if any(d.layer_calls for d in dialects):
        source = _join(source, dialects, pipes, True, context, always)
    return source


def _join(
    source: str,
    dialects: Sequence[Dialect],
    pipes: frozenset[str],
    layers: bool,
    context: Mapping[str, Any] | None,
    always: Collection[str],
) -> str:
    operators = pipes | ({"+"} if layers else set())
    if not operators or not any(op in source for op in operators):
        return source
    stripped = source.lstrip()
    if stripped.startswith(("%", "!", "?")):
        return source
    lines = source.split("\n")
    if not any(_leads(line.lstrip(), operators) for line in lines):
        return source
    indents = _continuation_indents(lines, operators)
    statements = _statements(lines, indents, operators)
    if not statements:
        return source
    plus = _Layers(source, lines, indents, dialects, context, always) if layers else None

    groups: list[list[_Statement]] = []
    for statement in statements:
        lead = statement.tokens[0]
        previous = groups[-1] if groups else None
        joins = False
        if previous is not None and lead.type == tokenize.OP and previous[0].tokens[0].start[1] == lead.start[1]:
            row = lead.start[0]
            given = len(lines[row - 1]) - len(lines[row - 1].lstrip())
            indented = indents[row - 1] is not None and given > indents[row - 1]
            if lead.string in pipes and not layers:
                joins = True
            elif lead.string == "+" and plus is not None:
                dialect = plus.operand(statement.tokens) if not indented else next(
                    (d for d in dialects if len(statement.tokens) > 1 and statement.tokens[1].string in d.layer_calls),
                    None,
                )
                head = [t for s in previous for t in s.tokens]
                joins = dialect is not None and (indented or plus.head(head, dialect))
        if joins:
            previous.append(statement)
        else:
            groups.append([statement])

    def column(row: int, col: int) -> int:
        """A column of the re-indented text, in the line as typed."""
        line = lines[row - 1]
        stripped = line.lstrip()
        if not _leads(stripped, operators):
            return col
        given = len(line) - len(stripped)
        return col - (indents[row - 1] or 0) + given

    edits: list[tuple[int, int, str]] = []  # (row, column, text), 1-based rows
    for group in groups:
        if len(group) == 1:
            continue
        head = group[0].tokens
        if head[0].string in operators or head[0].string in _KEYWORDS:
            continue
        opening = _assigned_value(head)
        closing = group[-1].tokens[-1].end
        edits.append((opening[0], column(*opening), "("))
        edits.append((closing[0], column(*closing), ")"))
    if not edits:
        return source
    out = list(lines)
    for row, col, piece in sorted(edits, reverse=True):
        line = out[row - 1]
        out[row - 1] = line[:col] + piece + line[col:]
    rewritten = "\n".join(out)
    try:
        ast.parse(rewritten)
    except SyntaxError:
        return source
    return rewritten


def join_broken(source: str, dialects: Sequence[Dialect]) -> str:
    """A pipe that does not parse even once joined, joined with backslashes instead.

    Python would otherwise stop at the first indented ``>>`` with an
    unexpected indent; joined, the pipe reaches Python as one statement and
    the error names the real line and column. Comments on the joined lines
    are dropped, since nothing may follow a backslash; line numbers are
    unchanged. *source* is returned unchanged when it parses or holds no pipe.
    """
    pipes = frozenset().union(*(d.pipe_operators for d in dialects))
    if not pipes or not any(op in source for op in pipes):
        return source
    text = source.strip("\n")
    if text.lstrip().startswith(("%", "!", "?")):
        return source
    try:
        ast.parse(text)
        return source
    except SyntaxError:
        pass
    operators = pipes | {"+"}
    lines = text.split("\n")
    shift = [len(line) - len(line.lstrip()) if _leads(line.lstrip(), operators) else 0 for line in lines]
    analysed = "\n".join(line[cut:] for line, cut in zip(lines, shift))
    # Per 0-based row: bracket depth after the row, and where its comment starts.
    end_depth: dict[int, int] = {}
    comment: dict[int, int] = {}
    in_string: set[int] = set()
    depth = 0
    try:
        for token in tokenize.generate_tokens(io.StringIO(analysed).readline):
            row = token.start[0] - 1
            if token.string in _OPENERS:
                depth += 1
            elif token.string in _CLOSERS:
                depth = max(depth - 1, 0)
            elif token.type == tokenize.COMMENT:
                comment[row] = token.start[1] + shift[row]
            in_string.update(range(row, token.end[0] - 1))
            end_depth[token.end[0] - 1] = depth
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass

    joins: list[int] = []
    previous: int | None = None
    top = piped = False
    start_depth = 0
    for row, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        continues = start_depth == 0 and (_leads(stripped, pipes) or (stripped.startswith("+") and piped))
        if continues and top and previous is not None:
            joins.extend(range(previous, row))
        elif start_depth == 0 and not continues:
            top, piped = True, False
        piped = piped or any(op in line for op in pipes)
        if row not in end_depth or row in in_string:
            break
        previous, start_depth = row, end_depth[row]
    # A rewrite can run twice (IPython's cleanup and post lists): skip rows already joined.
    joins = [row for row in joins if not lines[row][: comment.get(row, len(lines[row]))].rstrip().endswith("\\")]
    if not joins:
        return source
    for row in joins:
        line = lines[row]
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            lines[row] = "\\"
        else:
            lines[row] = line[: comment.get(row, len(line))].rstrip() + " \\"
    leading = source[: len(source) - len(source.lstrip("\n"))]
    return leading + "\n".join(lines) + "\n"
