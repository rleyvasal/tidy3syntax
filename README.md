# tidy3syntax

R syntax in notebook cells, rewritten to Python. It is the shared notebook
layer of [tidy3](https://github.com/rleyvasal/tidy3),
[tidy3a](https://github.com/rleyvasal/tidy3a),
[plot3](https://github.com/rleyvasal/plot3) and
[stats3](https://github.com/rleyvasal/stats3), released on its own so a fix
reaches all four at once. It needs only the standard library.

```python
import tidy3syntax as ts

stats3 = ts.Dialect("stats3", formula_calls={"t_test", "lm"})
tidy3 = ts.Dialect("tidy3", negation_calls={"filter"}, ordered_calls={"select"},
                   rule_calls={"case_when"})

ts.rewrite("penguins >> t_test(body_mass_g ~ sex)", [stats3, tidy3])
# "penguins >> t_test('body_mass_g ~ sex')"
ts.rewrite('df >> filter(!is_na(x)) >> select(Cus = NUM, Row)', [stats3, tidy3])
# "df >> filter(~is_na(x)) >> select(__r_assign__('Cus', (NUM)), Row)"
```

## In a notebook

A package's notebook extension registers its dialect with the coordinator,
which installs one input transformer for every package:

```python
import tidy3syntax.ipython

def load_ipython_extension(shell):
    tidy3syntax.ipython.register(shell, DIALECT, ast_transformer=MyMaskTransformer(shell.user_ns))
```

A package can also declare an entry point, so a cell that imports it gets
its syntax in that same cell:

```toml
[project.entry-points."tidy3syntax.dialects"]
plot3 = "plot3.jupyter:load_ipython_extension"
```

`%%tidy3syntax plot3` as a cell's first line reinterprets that cell's calls
whoever owns them.

## Two kinds of rewrite

**Repairs** change only text that is a syntax error in Python, so no valid
program can mean anything else by it. They run by the call's name, whoever
owns the call:

| Written | Becomes | In calls listed as |
|---|---|---|
| `` `First Name` `` | `__r_name__('First Name')` | anywhere in code |
| `` f(`new col` = x) `` | `f(__r_assign__('new col', (x)))` | any call |
| `filter(!x)` | `filter(~x)` | `negation_calls` |
| `select(a = x, b)` | `select(__r_assign__('a', (x)), b)` | `ordered_calls` |
| `case_when(x > 6 ~ "big")` | `case_when((x > 6, "big"))` | `rule_calls` |
| `t_test(y ~ g)`, `facet_grid(drv ~ cyl)` | `t_test('y ~ g')` | `formula_calls` |

**Reinterpretations** change valid Python, so they run only in calls the
dialect's package owns:

| Written | Becomes | In calls listed as | Python's meaning |
|---|---|---|---|
| `geom_function(lambda x: x^2)` | `x**2` | `power_calls` | XOR |
| `facet_wrap(~cyl)` | `facet_wrap('~cyl')` | `unary_formula_calls` | bitwise not |

Who owns a call follows tidy3's rule: a function's local variable is the
notebook's; otherwise the latest top-level binding in the cell before the call
decides (an import gives its module, any other binding makes the name the
notebook's); otherwise the `context` does (an IPython namespace, or
`imported_names(...)` of earlier cells); a name the context lacks is the
exporting package's. A cell that does not parse gets no reinterpretation.
With `always={"plot3"}` a caller turns plot3's reinterpretations on everywhere.

```python
plot3 = ts.Dialect("plot3", power_calls={"geom_function"}, exports={"geom_function"})

ts.rewrite("def geom_function(f):\n    return f(3)\nr = geom_function(lambda x: x ^ 2)", [plot3])
# unchanged: the notebook's own geom_function keeps XOR
ts.rewrite("from plot3 import *\ngeom_function(lambda x: x ^ 2)", [plot3])
# "from plot3 import *\ngeom_function(lambda x: x ** 2)"
```

The placeholders' run-time values are `RName` and `RAssign`
(`runtime_values()` gives both, for a namespace); each package's own AST pass
turns them into its column references inside its calls.

## Status

Phases 1 to 5 of [the design](docs/design.md): the scanner, every repair,
the ownership rule and the two reinterpretations, used by tidy3 0.15.1, tidy3a
0.16.1, plot3 0.8.1 and stats3 0.6.1. Phase 6: continuation lines (`>>` for
tidy3, `+` for plot3) and the coordinator, in 0.1.2, which tidy3 0.16, tidy3a
0.17, plot3 0.9 and stats3 0.7 register with.

Phase 7, in 0.2.0: `__r_name__` and `__r_assign__` are the only
placeholders any package writes or reads; the packages' own names from before
(`__tidy3_bt__`, `__plot3_bt__`) are gone. Inside its own calls each
package's AST pass renames `__r_assign__` to a private name of its own
(`__tidy3_assign__`, `__tidy3a_assign__`), since the shared name's value in a
namespace can belong to no single package.

Where the output differs from a package's own rewrite before the switch:

- stats3: a multi-line formula keeps its indentation and trailing comma
  (`t_test(\n    'y ~ g',\n)`), and backtick names in formulas are kept.
- tidy3: a keyword before a positional argument in a method call
  (`df.select(a = x, b)`) is rewritten like the verb, as `!` in one already
  was; backticks inside strings and comments stay; a backtick assignment is
  rewritten only as a call argument.
- tidy3a: its placeholder is `__r_assign__`.
- plot3: a backtick name inside a one-sided facet formula that another
  package's rewrite reached first (`facet_wrap(~__r_name__('a b'))`) becomes
  the name again: `'~a b'`.

`scripts/family/` runs all five suites together on another machine: `sync.sh`
copies the working trees and starts `run.sh` in a tmux session there, and
`status.sh` reports each suite's result and failures.

Known limits: a Python 3.12 f-string that nests the same quote
(`f"{d["k"]}"`) is read as two strings, so a rewrite may see code inside it.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

The tests include properties: repairs leave every cell that parses unchanged,
`rewrite` leaves the standard library's own source unchanged with every
dialect registered, and rewriting is idempotent.
