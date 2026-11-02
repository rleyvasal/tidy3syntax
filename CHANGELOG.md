# Changelog

## Unreleased

Phase 6a of [the design](docs/design.md): continuation lines and the coordinator.

- Continuation lines. A line starting with one of a dialect's
  `pipe_operators` (tidy3's `>>`) continues the statement above, a repair; a
  pipe that still does not parse is joined with backslashes, so Python
  reports its real error. A `+ name(...)` line, for a dialect's
  `layer_calls` (plot3's layers), joins by name when indented and, when not,
  only if the call is the package's own and the statement above is one of
  its plots (`ggplot(...)`, a pipe ending in one, or a variable not known to
  hold something else). Joined lines keep their line numbers.
- `tidy3syntax.ipython`, the coordinator: `register(shell, dialect,
  ast_transformer=...)` puts every package's syntax in one input
  transformer, whatever the load order, kept first before each cell;
  `unregister`, `enable` and `registered` go with it. A cell that imports a
  package with a `tidy3syntax.dialects` entry point gets that package's
  syntax in the same cell. `%%tidy3syntax <package>` reinterprets one cell
  whoever owns its calls, and `reinterpret="always"` does so for the session.
- The integration test: tidy3, tidy3a, plot3 and stats3 in one notebook in
  all 24 load orders, in CI on pull requests, weekly, and before a release.

## 0.1.1 — 2026-11-01

The first release as `tidy3syntax`, the tidy3 family's name; tidy3 0.15.1,
tidy3a 0.16.1, plot3 0.8.1 and stats3 0.6.1 use it. The code is 0.1.0's.
0.1.0 was published as `tidysyntax`, which this name supersedes.

## 0.1.0 — 2026-11-01

First version, published as `tidysyntax`: phases 1 to 5 of
[the design](docs/design.md).

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
