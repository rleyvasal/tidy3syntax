# A shared package for R syntax in notebooks

Status: accepted 2026-11-01; phases 1 to 6 (§8) implemented and released (tidy3syntax 0.1.2, tidy3 0.16.0, tidy3a 0.17.0, plot3 0.9.0, stats3 0.7.0); phase 7 implemented, not released.

tidy3, tidy3a, plot3 and stats3 each let notebook cells use R syntax that Python
cannot parse: bare column names, `` `odd names` ``, `!` for negation, `name =
value` before a positional argument, `~` rules and formulas, and pipes or layers
that continue onto the next line. Each package carries its own copy of the code
that does this, and each copy has to know the others' internals. This document
moves the syntax-only part into one small package the four depend on,
`tidy3syntax`, and keeps in each package what is really its own.

## 1. The problem

### 1.1 Four copies of the same rewrites

| | tidy3 0.14.1 | tidy3a 0.15.0 | plot3 0.7.0 | stats3 0.5.1 |
|---|---|---|---|---|
| Notebook modules | `masking.py` 1,582 lines, `jupyter.py` 578 | `jupyter.py` 524 | `masking.py` 810, `jupyter.py` 549 | `masking.py` 217, `jupyter.py` 77 |
| Scanner that skips strings and comments | `_call_arguments`, and the loop in `rewrite_bang_not` | `_split_arguments`, `_in_string_or_comment` | `_string_end`, `_code_spans`; `tokenize` for `^` | `tokenize` |
| `!` → `~` inside verbs | yes (0.12.9 fixed line-leading `!`) | yes, ported 2026-11-01 | no | no |
| `` `name` `` | → `__tidy3_bt__("name")`, a column | no | → `__plot3_bt__("name")`, a string | kept inside quoted formulas |
| `name = value` before a positional argument | yes (0.12.7) | yes, ported 2026-11-01 | no | no |
| `~` | `case_when` rules → tuples (0.12.8) | no | facet formulas → strings | `y ~ x` in its model and test functions → strings |
| `^` as power | no | no | inside `geom_function` | no |
| `[x, y, z] = value` | no | inside `mutate` | no | no |
| Lines that continue a pipe or layer | `>>`, joined in `partial_run.py` | no; needs parentheses | `+ geom_…`, joined by `join_layer_lines` | no |
| Ownership of a call | statement order of the cell's imports, then the live namespace | last import wins, then the live namespace | none: any call named `aes`, `facet_wrap`, … | the function's name, or a `stats3.` prefix |

stats3 shares only the formula part: `t_test(body_mass_g ~ sex)` becomes
`t_test('body_mass_g ~ sex')`, the same repair plot3 makes for
`facet_grid(drv ~ cyl)`. tidy3 makes the same text into a tuple instead
(`case_when(x > 6 ~ "big")` → `(x > 6, "big")`), so a dialect says which of
the two a call takes (§4.3).

Each improvement has to be found in one package and ported by hand to the others,
and the ports drift: tidy3a went a week without tidy3's `!` and keyword fixes, and
its import rule still differs from the one tidy3 settled on in `3d36859`.

### 1.2 The packages know each other's internals

Each rewrite emits a placeholder the package's own AST pass resolves, and each
package names its placeholders after itself. When two packages share a notebook,
whichever source pass runs first rewrites both packages' calls, so every package
has grown code for the others' placeholders and hooks:

- **tidy3 knows plot3.** `_plot3_masking_for_importing_cell` imports
  `plot3.masking.Plot3MaskTransformer` to mask a cell that imports plot3, and
  finds plot3's transformer by class name. `export.py` imports plot3's
  `join_layer_lines` and `Plot3MaskTransformer` for `nb_export`.
- **plot3 knows tidy3.** It treats `__tidy3_bt__` like its own `__plot3_bt__`,
  and when it sees tidy3's backtick preparser it runs only its formula rewrites,
  after tidy3's.
- **tidy3a knows tidy3.** Since 2026-11-01 its AST pass turns `__tidy3_assign__`
  into `__tidy3a_assign__` in tidy3a calls, and the reverse in tidy3 calls.
- **stats3 knows tidy3.** It inserts its formula pass at the front so it runs
  before tidy3's pipe rewriting, and relies on tidy3's bare-name rewrite also
  making columns when tidy3 gets to a name first.

With four packages that is up to twelve one-way dependencies, each a special case
that a change to the other package can break without a failing test of its own.
The order of IPython's `input_transformers_cleanup` decides which package's pass
runs first. tidy3 inserts its passes at the front, plot3 inserts at the front or
right after tidy3's backtick pass, and tidy3a appends, so the result depends on
load order.

### 1.3 Some rewrites change what valid Python means

Most of these rewrites act on text that is a syntax error, so no program can mean
anything else by it. Three of plot3's do not. They act on valid Python and change
its meaning, and they decide by the call's name alone. With plot3 loaded in IPython
(checked 2026-11-01: the `^` and `+` rows against plot3 0.7.0, the facet row
against unreleased work in plot3's working tree), a notebook's own functions
behave like this:

| Cell | Python's result | Result with plot3 loaded |
|---|---|---|
| `def geom_function(fun): return fun(3)` then `geom_function(lambda x: x ^ 2)` | `1` (XOR) | `9`: `^` became `**` |
| `def facet_wrap(v): return v` then `facet_wrap(~5)` | `-6` | `'~5'`: the argument became a formula string |
| `x = 2` then a line `+ geom_point()`, with the notebook's own `geom_point` | `x == 2`, then a separate unary-plus statement | `x == 3`: the line was joined onto `x = 2` |

An AST pass that checks ownership cannot undo these, because by the time it runs
the text has already been changed. plot3's working tree now fixes all three
(uncommitted, 2026-11-01) with the rule of §4.6, ahead of `tidy3syntax`. §4.2 makes the difference between the two
kinds of rewrite part of the contract.

### 1.4 What is not the problem

The packages differ for good reasons in what a bare name means. In tidy3 the data
wins over a notebook variable; tidy3a raises an error when both have the name; in
plot3, a name inside `aes()` is a column-name string. They also differ in which
verbs take names and in what each verb does with them. None of that should be
shared.

## 2. Goals and non-goals

Goals:

1. One implementation of each piece of R syntax, fixed once and picked up by all four.
2. Neutral placeholders, so no package reads another package's internal names.
3. One deterministic order of source rewrites in a notebook, whatever the load order.
4. The same rewrites outside IPython, for tidy3's `nb_export`, partial runs and CRAFT, and plot3's CRAFT.
5. No dependency between tidy3, tidy3a, plot3 and stats3, and none from the shared package on any of them.
6. Never change the meaning of valid Python in code that no registered package owns, unless the user turned that on explicitly.

Non-goals:

- Name resolution (what a bare name means). That stays in each package's AST pass.
- Verb semantics, verb lists, and each package's runtime objects.
- plot3's LaTeX input, tidy3's CRAFT routing and display, and other notebook features that only one package has.
- Plain `.py` files. They stay plain Python, as they are now.

## 3. What moves and what stays

| Moves to `tidy3syntax` | Stays in each package |
|---|---|
| Scanner: code, string, comment and backtick spans; finding calls by name; splitting top-level arguments | The AST pass that resolves bare names (`Tidy3MaskTransformer`, `Tidy3aMaskTransformer`, `Plot3MaskTransformer`) |
| Rewrites: repairs (`` ` ``, `!`, keyword before positional, binary `~`, `>>` continuation lines) and reinterpretations gated by ownership (`^` power, unary `~` formulas, `+` continuation lines) | Verb lists, settings keywords, and which functions take rules or formulas, given to `tidy3syntax` as a dialect (§4.3) |
| The neutral placeholders and their runtime fallbacks | What a placeholder means inside the package's own calls |
| The ownership check: which package a call's function belongs to, from the cell's imports in statement order and then the live namespace | The package's own extension: magics, display, injecting its API |
| One coordinating IPython input transformer, and the masking of the importing cell | Package-only source passes such as tidy3a's `[x, y, z] = …`, registered at a stage (§4.4) |

## 4. Design

### 4.1 Scanner

The input to every rewrite is, by definition, not valid Python, so the scanner
works on characters rather than `tokenize` or `ast`. It returns the spans of code,
string literals (single, triple, prefixed and f-strings), comments and backtick
names, and offers two operations every rewrite needs:

- `calls(source, names)`: the calls to any of `names`, bare or prefixed (`ta.filter(`, `t3.select(`), outside strings and comments, with the offset of the `(`.
- `arguments(source, open_at)`: the top-level argument spans of that call and the offset of its `)`.

The current scanners disagree on edge cases: triple quotes, escaped quotes,
backticks inside strings, and `#` inside strings. One scanner with one test corpus
settles them once.

### 4.2 Two kinds of rewrite

Every rewrite is one of two kinds, and its kind decides what it needs before it may run.

**A repair** changes only text that is a syntax error in Python, so no valid
program can mean anything else by it. A repair turns R syntax into the Python a
package expects, and it runs by the call's name, with no ownership check. If the
call belongs to another package or to the notebook, nothing is lost, because the
text had no Python meaning to keep. Where the right reading depends on the owner,
the repair emits a neutral placeholder (§4.5) that only the owner's AST pass
gives a meaning.

**A reinterpretation** changes text that is already valid Python and gives it a
different meaning. It runs only where §4.6 finds the call is owned by the
dialect's package, or inside a scope the user turned on explicitly (§4.6). When
ownership cannot be decided, Python's meaning stays.

| Rewrite | Kind | Why |
|---|---|---|
| `` `First Name` `` → `__r_name__("First Name")` | repair | a backtick is not a Python token |
| `!x` → `~x` inside a call | repair | `!` is valid only in `!=`, in f-string conversions such as `{x!r}` (inside a string, which the scanner skips) and in IPython shell lines, and none of these is rewritten |
| `name = value` before a positional argument → `__r_assign__("name", value)` | repair | Python rejects a positional argument after a keyword one; `*args` after a keyword is valid, so it does not count as positional |
| `left ~ right` (binary `~`) → a rule or formula | repair | `~` is unary only in Python |
| `[x, y, z] = value` as a call argument → `__r_assign__([x, y, z], value)` | repair | not a valid argument |
| a line starting with `>>` joined onto the line above | repair | `>>` has no unary form |
| a line starting with an indented `+` joined onto the line above | repair | an unexpected indent |
| `^` → `**` inside a formula call | reinterpretation | `^` is XOR |
| `~x` (unary `~`) → a formula string inside a facet call | reinterpretation | `~x` is bitwise not |
| a line starting with an unindented `+` joined onto the line above | reinterpretation | a separate unary-plus statement |

The kind is a property of each occurrence, not of the rewrite's name.
plot3's facet formulas are a repair for `drv ~ cyl` and for `` ~`my col` ``,
neither of which is Python, and a reinterpretation for `~cyl`. The test is
whether the argument parses as a Python expression on its own. A new rewrite declares its
kind and justifies it in this table. A repair whose justification depends on
IPython must leave IPython's own syntax alone: `!cmd` and `x = !cmd` lines,
`%magic` lines and `name?`. IPython handles those after the cleanup transformers
have run.

### 4.3 Dialects

A package describes its syntax in one declarative object, with repairs and
reinterpretations in separate fields:

```python
DIALECT = tidy3syntax.Dialect(
    "plot3",
    # repairs: run by name
    formula_calls={"facet_wrap", "facet_grid"},     # y ~ x -> "y ~ x"
    formula_keywords={"facets"},                    # facets = drv ~ .
    formula_backticks="strip",                      # ~`my col` -> "~my col"
    # reinterpretations: run only where plot3 owns the call, or in an enabled scope
    power_calls={"geom_function", "geom_vector_field"},  # ^ is power
    unary_formula_calls={"facet_wrap", "facet_grid"},    # ~cyl -> "~cyl"
)
```

The repair fields are `negation_calls` (`!x` → `~x`), `ordered_calls` and
`settings` (`name = value` before a positional argument), `rule_calls` and
`rule_after_column` (`left ~ right` → `(left, right)`, tidy3's form),
`formula_calls`, `formula_keywords` and `formula_backticks` (`y ~ x` →
`"y ~ x"`, plot3's and stats3's form), and `stages`, a package's own repairs
such as tidy3a's `[x, y, z] = …`. The reinterpretation fields are
`power_calls` and `unary_formula_calls`. `exports` lists the package's public
names, or is read from its `__all__` when first needed; ownership uses it for
star imports and for names the context lacks.

tidy3's dialect lists its verbs and `case_when` and its relatives. tidy3a's
lists its verbs and its vector stage. stats3's lists its model and test
functions as formula calls. All three are repairs only. plot3's is the only
dialect today with reinterpretations. Continuation lines (`>>` for tidy3, `+`
for plot3) get fields when phase 6 moves them (§8).

Packages expose their dialect through an entry point, so `tidy3syntax` can find a
package's dialect and AST pass without importing the package:

```toml
[project.entry-points."tidy3syntax.dialects"]
plot3 = "plot3.masking:DIALECT"
```

### 4.4 Rewrite pipeline

`tidy3syntax.rewrite(source, dialects, context)` is a pure function of its inputs.
`context` answers ownership questions: the IPython namespace, or for
`nb_export` the imports of the cells before this one, in notebook order. It runs
in three phases:

**Phase A, repairs**, by name, in this order:

1. Shell guard: a cell made only of `!` lines and comments is returned unchanged.
2. Backticks.
3. Negation, inside negation calls.
4. Binary `~` rules and formulas, in rule calls.
5. Package stages that are repairs, such as tidy3a's `[x, y, z] = …`.
6. Keywords before positional arguments, in ordered calls, except settings.
7. Continuation lines that are repairs: lines starting with `>>`, and indented `+` lines.

**Phase B, ownership.** Parse the result of phase A. Reinterpretation
candidates are valid Python by definition, so they do not stop the parse. If the
cell does not parse, phase C is skipped and Python reports the
error: a cell whose ownership cannot be read keeps Python's meaning. Otherwise,
for each reinterpretation candidate found by the scanner, map its offset to a
node in the tree and ask `owner()` (§4.6) about the call that decides it:

- `^`: the nearest enclosing call whose name is one of the dialect's power calls must be owned by the dialect's package. In `geom_function(lambda x: f(x^2))`, that is `geom_function`, not `f`.
- unary `~`: it must stand at the top level of an argument of a unary-formula call owned by the dialect's package.
- `+` continuation: the call after `+` must be owned by the dialect's package. The head of the statement above, the start of its value, must be a call owned by that package (`ggplot(...)` in `p = ggplot(df) …`), or a variable not known to hold something else. A variable bound earlier in the same cell counts as unknown, since its value does not exist yet. `x = 2` and `x = n` with `n == 2` in the session have no such head, so nothing is joined onto them.

**Phase C, reinterpretations.** Apply the candidates that phase B accepted, plus
those inside an enabled scope (§4.6), from right to left.

Each phase must be idempotent, and the pipeline as a whole must be too:
`rewrite(rewrite(s)) == rewrite(s)`. Without a `context`, as in a plain call from
a test or an export that tracks no earlier cells, step 3 of §4.6 is skipped: the
cell's own bindings still decide, and a name it does not bind is the dialect
package's when that package exports it.

Phase B needs every repair done first, including other packages'. While each
package installs its own transformer, a cell can reach plot3's pass with
another package's syntax still unrepaired: tidy3a's `!` in the same cell, with
tidy3a loaded after plot3. That cell does not parse, so plot3 skips its
reinterpretations and `^` stays XOR. A cell mixing two packages' R syntax
is uncommon, and the single coordinator of §4.7, which runs all repairs before
any parse, removes the case.

### 4.5 Neutral placeholders

| Placeholder | Made by | Meaning |
|---|---|---|
| `__r_name__("name")` | backticks | a name that is not a Python identifier |
| `__r_assign__(target, value)` | keywords before positional arguments, vector assignments | an assignment in the order written; `target` is a string or a list of names |

Each package's AST pass interprets them inside its own calls. tidy3 makes a
column expression or a `NamedAssign`, tidy3a an `assign()`, and plot3 a string.
Where a placeholder escapes into code no AST pass owns, `tidy3syntax` defines its
runtime value, `RName` (a `str` subclass) and `RAssign(target, value)`, which it
puts in the namespace. Packages accept these where they now accept their own
carriers. Bare-name placeholders such as `__tidy3_name__` and
`__tidy3a_name__` are made by each package's AST pass, not by a source rewrite,
and stay package-specific.

Neutral placeholders make repairs safe to run on any call. They do nothing for
reinterpretations, whose output is ordinary Python (`**`, a string, a joined
expression) with no marker an AST pass could recognise and undo. That is why
§4.4 checks ownership before a reinterpretation runs.

### 4.6 Ownership and explicit scopes

`tidy3syntax.owner(func_node, tree, context, packages)` returns the package a
call's function belongs to, or `None`:

1. a local variable of an enclosing function, lambda or comprehension: `None`;
2. the latest top-level binding of the name in the cell before the call, in statement order: an import (star imports through the package's `__all__`) gives that package; any other binding (`def geom_function`, `geom_function = …`) gives `None`;
3. the context: in IPython, the package of the live value's `__module__`; for `nb_export`, the earlier cells' imports;
4. a name the context does not have: the dialect's package, when that package exports the name. Such a cell fails with a `NameError` whatever the rewrite does, so the choice changes no result and keeps error messages as they were.

A prefixed call such as `p3.geom_function(...)` is owned when the prefix is the
package's module. A value wrapped so that its `__module__` is not the package's,
such as `functools.partial(geom_function)`, is not owned. The failure goes the
safe way: Python's meaning is kept.

This is tidy3's rule since `3d36859`. The same function decides phase B and every
package's AST pass, so a call's source rewrite and its bare-name masking always
agree. tidy3a moves from last-import-wins to it, which changes only cells that
import the same verb from two packages and call it in between. plot3 moves from
matching the call's name alone to it, which fixes the three cases in §1.3 and
stops plot3 rewriting a notebook's own `aes` or `slider`.

**Explicit scopes** let a user ask for a reinterpretation where ownership does not
hold, for instance when calling a wrapper of plot3's functions:

- for one cell, `%%tidy3syntax plot3` as the cell's first line;
- for the session, `tidy3syntax.ipython.register(ipython, "plot3", reinterpret="always")`.

The default is `reinterpret="owned"`. A scope widens reinterpretations only.
Repairs never need one, and bare-name masking stays with each package's AST pass.

### 4.7 Coordinator

`tidy3syntax.ipython.register(ipython, package)` is what each package's
`load_ipython_extension` calls. The first call installs one input transformer on
`input_transformers_cleanup` and marks it, so later calls only add their dialect.
The transformer runs `rewrite` with every registered dialect and the live
namespace as its context. The packages' AST transformers stay separate. Their
order no longer matters, since each touches only the calls it owns and the
placeholders are neutral.

The coordinator also handles the importing cell. When a cell imports a package
whose dialect is installed as an entry point but not registered, the coordinator
applies that package's dialect to the cell, both its repairs and its
reinterpretations, which phase B finds owned through the cell's own import. It
also applies the package's AST pass and registers the package for later cells.
That replaces tidy3's plot3-specific hook. tidy3's switch for R syntax
(`enable_r_style` / `disable_r_style`) becomes a per-dialect switch in the
coordinator.

Unloading removes the package's dialect and its AST pass. The coordinator's own
transformer leaves when no dialect is left.

## 5. Compatibility

- **Exported files.** `nb_export` writes `from tidy3.masking import make_named_assign as __tidy3_assign__` into `.py` files. tidy3 keeps that import working, and its AST pass accepts `__tidy3_assign__` and `__tidy3_bt__` beside the neutral names, for at least two minor releases after the switch. plot3 keeps `__plot3_bt__` for the same period, and tidy3a keeps `__tidy3a_assign__`. New exports write the neutral names.
- **Error messages.** A placeholder can appear in a traceback for the rewritten cell. The neutral names are shorter and no worse than today's. Each package keeps its own error text.
- **Behaviour changes**, listed in each package's CHANGELOG when it switches:
  - tidy3a's import rule changes (§4.6);
  - plot3's `^`, unary `~` and unindented `+` rewrites run only on calls plot3 owns (§4.2, §4.6). A notebook's own `geom_function`, `facet_wrap` or `geom_point` keeps Python's meaning, a cell with a syntax error loses these rewrites until it parses, and a wrapper of plot3's functions needs an explicit scope;
  - plot3's bare-name masking runs only on calls plot3 owns (§4.6);
  - plot3 cells gain `!` inside its selector calls if its dialect lists them;
  - tidy3a gains backtick names (they become `assign()` targets) and, if its dialect asks for it, `>>` continuation lines.

## 6. Testing

In `tidy3syntax`:

- A corpus of `(source, dialects, expected)` cases, seeded from the four packages' current tests: tidy3's `test_masking.py`, tidy3a's `test_notebooks.py` rewrite cases, plot3's masking tests, and stats3's `test_masking.py`.
- Properties checked over the corpus and generated cells:
  - repairs leave every cell that parses unchanged, whatever owns its calls;
  - `rewrite` leaves every cell that parses unchanged when no registered package owns any of its calls, with every dialect registered;
  - `rewrite` is idempotent.
- Regression cases for reinterpretations, each run through `rewrite` and in a real IPython shell with plot3's dialect registered:

  | Cell | Expected |
  |---|---|
  | `def geom_function(fun): return fun(3)` then `r = geom_function(lambda x: x ^ 2)` | text unchanged, `r == 1` |
  | `from plot3 import *` then `def geom_function(fun): return fun(3)` then `r = geom_function(lambda x: x ^ 2)` | text unchanged, `r == 1`: the cell's own binding wins |
  | `def f(geom_function): return geom_function(lambda x: x ^ 2)` | text unchanged: a parameter |
  | `from plot3 import *` then `geom_function(lambda x: 2*x^3)` | `2*x**3`: owned through the cell's import |
  | `import plot3 as p3` then `p3.geom_function(lambda x: x ^ 2)` | `x ** 2`: a prefixed call |
  | `from plot3 import *` then `geom_function(lambda x: np.sin(x^2))` | `np.sin(x**2)`: the nearest power call decides, not `np.sin` |
  | `%%tidy3syntax plot3`, then the first case | `r == 9`: an explicit scope |
  | the first case, plus an unrelated syntax error | text unchanged apart from repairs |
  | `def facet_wrap(v): return v` then `f = facet_wrap(~5)` | text unchanged, `f == -6` |
  | `facet_wrap(drv ~ cyl)` with the notebook's own `facet_wrap` | repaired anyway: binary `~` is not Python |
  | `def geom_point(): return 1`, `x = 2`, then the line `+ geom_point()` | not joined, `x == 2` |
  | `from plot3 import *`, `x = 2`, then the line `+ geom_point()` | not joined: `x = 2` has no owned head |
  | `from plot3 import *`, `p = ggplot(df)`, then the line `+ geom_point()` | joined |
- IPython tests with stub dialects, covering every load order of four packages, unloading, and the importing cell.

In each package:

- Its own tests, unchanged in what they assert, run against the released `tidy3syntax` and, in a scheduled job, against `tidy3syntax`'s main branch, so a shared change that breaks a package fails before release.
- One integration notebook with tidy3, tidy3a, plot3 and stats3 together. It lives in `tidy3syntax` and runs in its CI with all four installed, in all 24 load orders.

## 7. Versioning and release

`tidy3syntax` depends only on the standard library and supports Python 3.10 and later,
the lowest floor of the four (tidy3 and plot3 require 3.10, tidy3a 3.11, stats3 3.12). IPython
stays optional; `tidy3syntax.ipython` imports it only when called.

Its public API is the `Dialect` fields, the placeholder names and runtime
classes, `rewrite`, `owner` and `ipython.register`. It follows semantic versioning
from 0.1. Before 1.0 a minor version may change behaviour, as in tidy3, so
packages require `tidy3syntax>=0.N,<0.N+1` and raise the bound when they adopt a
release. A fix to a rewrite is then one change in `tidy3syntax`, one release, and a
bound raised in each package, with no ported code.

## 8. Migration

Each phase ends with every package's suite passing, and nothing is released before its exit check.

1. **Create `tidy3syntax` from tidy3's code.** tidy3's copy is the most complete, so it is the base. Move the scanner, `rewrite_backticks`, `rewrite_bang_not`, `rewrite_keywords_before_positional` and `rewrite_formula_rules`, generalised over dialects, plus stats3's and plot3's formula quoting, the ownership rule and the `^` and unary `~` reinterpretations from plot3's fix, and seed the corpus. Exit check: the corpus passes, including every tidy3 rewrite case unchanged. *Done 2026-11-01, released as tidy3syntax 0.1.1 (first as tidysyntax 0.1.0):* `src/tidy3syntax/`, 272 tests on Python 3.10 to 3.14. The cases whose text differs from a package's current output are listed in the README.
2. **Switch tidy3**, keeping its old placeholders as aliases (§5). Exit check: tidy3's suite passes with no assertion changed except the placeholder names in rewritten text. *Done 2026-11-01, released in tidy3 0.15.0 (0.15.1 on the new name):* tidy3 runs tidy3syntax's repairs and turns the neutral placeholders back into `__tidy3_bt__` and `__tidy3_assign__`, which plot3, stats3 and tidy3a read today and `nb_export` writes; its AST pass also reads the neutral names. One assertion changed: `df.select(a=NUM, b)` is now rewritten like the verb, as `!` in a method call already was, instead of being left as a syntax error.
3. **Switch tidy3a.** *Done 2026-11-01, released in tidy3a 0.16.0 (0.16.1 on the new name):* it writes `__r_assign__`, still reads `__tidy3a_assign__`, and hands the placeholder to tidy3 as `__tidy3_assign__` in tidy3's calls. Delete its scanner, `rewrite_bang_not`, `rewrite_keywords_before_positional` and the carrier translation in `visit_Call`, and move `[x, y, z] = …` to a dialect stage. Exit check: `test_notebooks.py` passes, and the two-package tests pass in both load orders.
4. **Switch stats3.** Replace `quote_formulas` with a dialect of formula calls; its bare-name pass stays. Exit check: stats3's `test_masking.py` passes. *Done 2026-11-01, released in stats3 0.6.0 (0.6.1 on the new name):* every existing case passes unchanged, and backtick names in formulas now work (`lm` reads them; `t_test`'s own formula parsing does not yet).

Until every package's AST pass reads the neutral placeholders, a package that switches early calls only the repairs that leave none: stats3 calls `tidy3syntax.repairs.quote_formulas`, not `repair`. Otherwise a stats3 pass running first would leave `__r_name__` in a tidy3 call, which tidy3 0.14 does not read. Each package widens to `repair` once tidy3 (phase 2) reads them.

tidy3 0.14's backtick pass rewrites backticks inside string literals too. When it runs after another package's formula quoting, it breaks the quoted formula (`'`body mass` ~ sex'` becomes `'__tidy3_bt__('body mass') ~ sex'`). tidy3syntax's backtick repair skips strings, so phase 2 fixes it; until then a backtick name in a stats3 formula works only when tidy3's notebook layer is not loaded.
5. **Switch plot3.** *Done 2026-11-01, released in plot3 0.8.0 (0.8.1 on the new name), with its facet-formula work:* its scanner, facet formulas, `^` and ownership check are gone; it turns `__r_name__` back into `__plot3_bt__`, and joining `+` lines uses tidy3syntax's `Owners`. Move backticks and binary `~` facet formulas onto `tidy3syntax` as repairs, and `^`, unary `~` and unindented `+` continuation lines as reinterpretations gated by ownership. Delete its handling of tidy3's placeholders and its detection of tidy3's preparser. Exit check: the §6 regression cases pass in plot3's own suite.
6. **Coordinator, continuation lines and ownership in the AST passes.** Install the single transformer and the entry points; move tidy3's `>>` and plot3's `+` continuation lines; let each package's AST pass use the shared `Owners`. Delete tidy3's plot3 hook and plot3 imports from `export.py`. Exit check: the four-package notebook passes in all 24 load orders. In three steps, each released on its own (planned 2026-11-01):
   - **6a, tidy3syntax only (0.1.2, additive).** Continuation lines: a line starting with `>>` continues the statement above, a repair (tidy3's `_wrap_pipe_statements`, and `join_broken_pipe`, which joins a broken pipe with backslashes so Python names the real error); an indented `+` line is a repair; an unindented `+` line is a reinterpretation, joined only when the call after `+` is owned by the dialect that lists it and the statement above starts with an owned call or ends a pipe whose last step is one. tidy3 today joins a `+` line after any pipe by name, the §1.3 bug for `+`; this replaces it. The coordinator, `tidy3syntax.ipython`: one input transformer for every registered dialect, kept ahead of CRAFT's router before each cell (tidy3's `pre_run_cell` hook does this today), the importing cell (§4.7), and entry points. The integration test: a notebook with the four packages in all 24 load orders, run in this repository's CI on pull requests and weekly.
   - **6b, each package (one release each).** Register with the coordinator instead of installing a transformer; delete its continuation code, its handling of the other packages' placeholders and hooks (tidy3's plot3 hook and `export.py`'s plot3 imports); write the neutral names; use `Owners` in its AST pass. Packages on 6b and packages not yet on it must still share a notebook: the coordinator leaves a package's own transformer in place until that package registers.
   - **6c.** The integration test passes against the four packages' releases. *Done 2026-11-01:* tidy3syntax's CI installed tidy3 0.16.0, tidy3a 0.17.0, plot3 0.9.0 and stats3 0.7.0 from PyPI with tidy3syntax 0.1.2, and all 24 load orders passed.

   Progress (2026-11-02): 6a is committed (continuation lines, the coordinator, the integration test). 6b is done in the four packages' working trees, not released: each registers with the coordinator and declares an entry point; stats3, tidy3a and plot3 read `__r_name__` as a column; each AST pass renames `__r_assign__` to its own private name inside its own calls (`__tidy3_assign__`, `__tidy3a_assign__`), since the shared name's value in the namespace can belong to no single package; plot3's AST pass checks ownership with `Owners`; tidy3a takes `>>` continuation lines; tidy3's `pre_run_cell` hook and plot3 hook are gone, and plot3 no longer looks for tidy3's preparser. tidy3's `nb_export`, partial runs and CRAFT path rewrite through tidy3syntax as well (2026-11-02): an entry point names a function returning the package's dialect, whose `extension` is its notebook loader and whose `mask` applies its AST pass to source text; `tidy3syntax.installed()` lists them, so `export.py` finds plot3 without importing it. tidy3a's and stats3's dialects have no `mask` yet: their AST passes write internal names an export cannot turn into public code, and tidy3's export did not handle them before either. At release, tidy3 should require the plot3 release that has the entry point.
7. **Drop the old placeholder aliases** two minor releases after phase 2. *Done 2026-11-01, one minor release after phase 2 at the owner's choice, not released:* the source passes write only `__r_name__` and `__r_assign__`, and no AST pass reads `__tidy3_bt__` or `__plot3_bt__`, or another package's assignment name; tidy3a no longer hands `__r_assign__` to tidy3. What stays are the private runtime names each AST pass renames `__r_assign__` to inside its own calls (`__tidy3_assign__`, `__tidy3a_assign__`), which no source text holds; scripts `nb_export` wrote define `__tidy3_assign__` themselves, so they keep running. A notebook mixing these releases with tidy3 0.15, tidy3a 0.16, plot3 0.8 or stats3 0.6 or older can lose backtick names in the other package's calls.

Phases 2 to 5 are independent once phase 1 is released. Phase 6 needs all four.

**Placeholder names during the switch.** A package that switches before the
others cannot write the neutral names into the text: another package's pass
may meet its calls first, and the others read only their own names. So until
phase 6, tidy3 and plot3 turn `__r_name__` and `__r_assign__` back into their
own names after the repairs; tidy3a writes `__r_assign__` because it already
hands the placeholder to tidy3 in tidy3's calls; stats3 calls only the formula
repair, which leaves none. Every AST pass reads both the neutral names and its
old ones. Phase 6 makes the neutral names the only ones written.

**Prefixes.** The packages differed on prefixed calls: tidy3's `!` rewrite
covered method calls (`df.select(!x)`, TidyFrame's methods) while its keyword
rewrite skipped them; tidy3a and plot3 took any prefix; stats3 took only
`stats3.`. `Dialect.prefixes` says which prefixes count. tidy3, tidy3a and
plot3 take any; stats3 keeps `{"stats3"}`.

The §1.3 cases were bugs in plot3, independent of `tidy3syntax`. plot3's working
tree fixes them with its own ownership check (`plot3.masking.owned_calls` and
`_Owners`) and the §6 cases, so phase 5 moves that code into `tidy3syntax` rather
than writing it.

## 9. Alternatives considered

- **Keep porting by hand.** No new package, but every fix is made up to four times, the packages keep knowing each other's internals, and load order keeps deciding the result. This is the current state, and §1 shows its cost.
- **Vendoring.** Copy `tidy3syntax`'s source into each package, with a CI check that each copy matches a pinned upstream commit. There is no runtime dependency, but each fix still means four syncs and four releases, and two copies at different versions can still disagree in one notebook. It is worth choosing only if a new dependency is unacceptable.
- **A monorepo** holding the four packages and a shared module. It removes the problem completely but changes the release and issue workflow of four repositories for one module.
- **Making tidy3 the shared base.** tidy3a and plot3 would depend on tidy3, which tidy3a's plan rules out (§9 there), and which would pull in Polars.

## 10. Risks

- **One bug reaches all four packages.** The corpus, the idempotence property and each package's scheduled run against `tidy3syntax` main are the guard; pinning to a minor version limits how far a release reaches.
- **A rewrite is misclassified as a repair.** That would change valid Python without an ownership check, which is the failure §1.3 describes. The justification column in §4.2 and the first property in §6 guard against it: the property fails on any cell that parses and is changed by a repair.
- **Phase B costs a parse per cell.** It runs only when a reinterpretation candidate is present, and IPython parses every cell anyway, so it adds one more parse of the same text.
- **Dialects outgrow the declarative form.** A package needing a rewrite nobody else has uses a dialect stage (§4.4) rather than a new `Dialect` field.
- **The coordinator meets an old package version** that still installs its own transformer. The coordinator detects the known old transformers by name and leaves them in place with a warning naming the package and the version that fixes it.
- **Maintenance owner.** tidy3a's plan §5.6 rejected a shared package for v1 because it "needs its own maintainer". The owner here is the same person who maintains all four packages, and §1.1 is the comparison §5.6 asked for once the copies had settled.

## Open decisions

1. ~~Name~~: `tidy3syntax`, named for the tidy3 family it serves. It was first published as `tidysyntax` 0.1.0 on 2026-11-01 and renamed the same day; that release is superseded, and the packages' next releases depend on `tidy3syntax`.
2. **Dependency or vendoring** (§9). Phase 1 assumes a dependency.
3. **When to rename placeholders**: in phase 2, as proposed, or after phase 5, so each package's first switch changes no visible names.
4. ~~New syntax per package~~ (decided 2026-11-01): each package takes the syntax tidy3syntax already offers that has a reading in its calls. tidy3a takes backtick names and backtick assignments now, and `>>` continuation lines when phase 6 moves them here. plot3 does not take `!`: its aesthetics read names as column-name strings, so `!flag` has no meaning there.
5. ~~Where the four-package integration test runs~~ (decided 2026-11-01): the four-package integration test lives in tidy3syntax and runs in its CI. A separate compatibility repository can be introduced if release coordination later requires it. tidy3syntax owns the mixed-package notebook and the tests of interactions, including the packages' load orders; each package owns its detailed behaviour tests; the integration test runs on tidy3syntax's pull requests and on a schedule, so a change in a package also shows up there.
