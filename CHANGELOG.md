# Changelog

## 0.1.0 — 2026-11-01

First version: phases 1 to 5 of [the design](docs/design.md); tidy3 0.15.1,
tidy3a 0.16.1, plot3 0.8.1 and stats3 0.6.1 use it. The same code was
published the same day as `tidysyntax` 0.1.0, which this name supersedes.

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
- `Dialect.prefixes` says which module prefixes make `prefix.name(...)` one of
  a dialect's calls: any (the default), none (bare calls only), or a set of
  names, such as stats3's `{"stats3"}`.
