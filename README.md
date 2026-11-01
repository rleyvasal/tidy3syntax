# tidysyntax

R syntax in notebook cells, rewritten to Python. It is the shared notebook
layer of [tidy3](https://github.com/rleyvasal/tidy3),
[tidy3a](https://github.com/rleyvasal/tidy3a),
[plot3](https://github.com/rleyvasal/plot3) and
[stats3](https://github.com/rleyvasal/stats3), released on its own so a fix
reaches all four at once. It needs only the standard library.

```python
import tidysyntax as ts

stats3 = ts.Dialect("stats3", formula_calls={"t_test", "lm"})
tidy3 = ts.Dialect("tidy3", negation_calls={"filter"}, ordered_calls={"select"},
                   rule_calls={"case_when"})

ts.rewrite("penguins >> t_test(body_mass_g ~ sex)", [stats3, tidy3])
# "penguins >> t_test('body_mass_g ~ sex')"
ts.rewrite('df >> filter(!is_na(x)) >> select(Cus = NUM, Row)', [stats3, tidy3])
# "df >> filter(~is_na(x)) >> select(__r_assign__('Cus', (NUM)), Row)"
```

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

Phase 1 of [the design](docs/design.md): the scanner, every repair, the
ownership rule and the two reinterpretations. Not yet here: the IPython
coordinator that installs one transformer for all packages, continuation lines
(`>>` for tidy3, `+` for plot3), and entry points. No package uses tidysyntax
yet.

Where the output differs from a package's own rewrite today (the meaning is
the same unless stated):

- stats3: a multi-line formula keeps its indentation and trailing comma
  (`t_test(\n    'y ~ g',\n)`), and formulas are quoted under any module prefix
  (`s3.t_test(...)`), not only `stats3.`.
- tidy3: prefixed calls (`t3.filter(!x)`, `t3.select(a = x, b)`) are repaired
  too, and a backtick assignment is rewritten only as a call argument.
- tidy3 and tidy3a: placeholders are `__r_name__` and `__r_assign__`, not
  `__tidy3_bt__`, `__tidy3_assign__` and `__tidy3a_assign__`.
- plot3: a placeholder another package left inside a one-sided facet formula
  (`facet_wrap(~__tidy3_bt__('a b'))`) becomes the name again: `'~a b'`.

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
