"""The placeholders repairs leave in the text, and their values at run time.

A repair runs by the call's name, so its output must not depend on which
package owns the call. Where the reading does depend on the owner, the
repair leaves a neutral placeholder, and the owner's AST pass decides what
it means inside the owner's calls. Where no AST pass claims one, its
run-time value below is what Python sees.
"""

from __future__ import annotations

from typing import Any

NAME = "__r_name__"  # `First Name` -> __r_name__("First Name")
ASSIGN = "__r_assign__"  # name = value before a positional argument -> __r_assign__("name", value)


class RName(str):
    """A name written in backticks: a column name that need not be a Python identifier."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"{NAME}({str.__repr__(self)})"


class RAssign:
    """An assignment in the order written: ``target`` is a name, or a list of names; ``value`` is anything."""

    __slots__ = ("target", "value")

    def __init__(self, target: Any, value: Any):
        self.target = target
        self.value = value

    def __repr__(self) -> str:
        return f"{ASSIGN}({self.target!r}, {self.value!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RAssign) and (self.target, self.value) == (other.target, other.value)

    __hash__ = None  # type: ignore[assignment]


def runtime_values() -> dict[str, Any]:
    """The placeholders' values, for a namespace that runs rewritten cells."""
    return {NAME: RName, ASSIGN: RAssign}
