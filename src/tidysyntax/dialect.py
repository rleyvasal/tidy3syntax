"""A package's R syntax, described as data."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal


def _names(values: Iterable[str]) -> frozenset[str]:
    if isinstance(values, str):
        raise TypeError(f"expected a collection of names, not the string {values!r}")
    return frozenset(values)


@dataclass(frozen=True)
class Dialect:
    """Which calls of one package take which piece of R syntax.

    Fields under *repairs* name calls whose arguments may hold text that is
    not Python; tidysyntax rewrites those by the call's name, whoever owns
    the call. Fields under *reinterpretations* name calls whose arguments
    may hold valid Python that the package reads differently; tidysyntax
    rewrites those only in calls the package owns (see ``ownership``).
    Names are the functions' names, without a module prefix.
    """

    package: str
    # repairs
    negation_calls: frozenset[str] = frozenset()  # !x -> ~x
    ordered_calls: frozenset[str] = frozenset()  # name = value before a positional argument
    settings: frozenset[str] = frozenset()  # keywords of ordered calls that are never moved
    rule_calls: frozenset[str] = frozenset()  # left ~ right -> (left, right)
    rule_after_column: frozenset[str] = frozenset()  # rule calls whose first argument is a column
    formula_calls: frozenset[str] = frozenset()  # y ~ x -> "y ~ x"
    formula_keywords: frozenset[str] = frozenset()  # keywords whose value may be a formula (facets=)
    formula_backticks: Literal["keep", "strip"] = "keep"  # backtick names inside a quoted formula
    stages: tuple[Callable[[str], str], ...] = ()  # the package's own repairs, run after the shared ones
    # reinterpretations
    power_calls: frozenset[str] = frozenset()  # ^ -> **
    unary_formula_calls: frozenset[str] = frozenset()  # ~x -> "~x"
    # The names the package exports; None reads the package's __all__ when first needed.
    exports: frozenset[str] | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        for name in (
            "negation_calls", "ordered_calls", "settings", "rule_calls", "rule_after_column",
            "formula_calls", "formula_keywords", "power_calls", "unary_formula_calls",
        ):
            object.__setattr__(self, name, _names(getattr(self, name)))
        if self.exports is not None:
            object.__setattr__(self, "exports", _names(self.exports))
        if not self.rule_after_column <= self.rule_calls:
            raise ValueError("rule_after_column must be a subset of rule_calls")
        if self.formula_backticks not in ("keep", "strip"):
            raise ValueError('formula_backticks is "keep" or "strip"')
        if not self.package or "." in self.package:
            raise ValueError("package is a top-level module name, such as 'tidy3a'")

    def exported(self) -> frozenset[str]:
        """The package's public names: ``exports``, or its ``__all__``."""
        if self.exports is not None:
            return self.exports
        try:
            module = importlib.import_module(self.package)
        except Exception:
            names: frozenset[str] = frozenset()
        else:
            names = frozenset(getattr(module, "__all__", ()) or (n for n in dir(module) if not n.startswith("_")))
        object.__setattr__(self, "exports", names)
        return names

    def owns_module(self, module: str | None) -> bool:
        """Whether a dotted module path belongs to this package."""
        return module is not None and (module == self.package or module.startswith(self.package + "."))

    @property
    def reinterprets(self) -> bool:
        return bool(self.power_calls or self.unary_formula_calls)
