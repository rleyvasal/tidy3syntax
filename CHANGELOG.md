# Changelog

## Unreleased

First version: phase 1 of [the design](docs/design.md).

- `Dialect` describes one package's R syntax as data: which calls take `!`,
  `name = value` before a positional argument, `left ~ right` rules (tidy3's
  tuples), `y ~ x` formulas (plot3's and stats3's strings), `^` as power and
  one-sided formulas, and a package's own repair stages.
- `repair()` rewrites text that is not Python, by the call's name: formulas,
  rules, negation, backtick assignments, keywords before positional
  arguments, and backtick names, which become the neutral placeholders
  `__r_name__` and `__r_assign__`.
- `rewrite()` adds the reinterpretations, `^` → `**` and `~x` → `"~x"`, only in
  calls the dialect's package owns, by tidy3's rule (the latest binding in the
  cell, then the context), or in packages listed in `always=`.
- `imported_names()` builds a context from earlier cells' imports, for exports
  that have no live namespace.
