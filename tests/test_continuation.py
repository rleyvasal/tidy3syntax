"""Continuation lines: ``>>`` lines by name, ``+`` lines by ownership.

Cases come from tidy3's ``test_cell_rewrite.py`` and plot3's
``test_masking.py`` (``join_layer_lines``).
"""

import ast

import pytest
from dialects import ALL, PLOT3, TIDY3

from tidy3syntax import rewrite
from tidy3syntax.continuation import join, join_broken


@pytest.mark.parametrize(
    "cell, expected",
    [
        ("tidy(cars)\n>> filter(mpg > 20)\n>> select(mpg)", "(tidy(cars)\n>> filter(mpg > 20)\n>> select(mpg))"),
        ("out = tidy(cars)\n    >> filter(mpg > 20)", "out = (tidy(cars)\n    >> filter(mpg > 20))"),
        ('if True:\n    tidy(cars)\n    >> select("mpg")\n', 'if True:\n    (tidy(cars)\n    >> select("mpg"))\n'),
        # Comments and blank lines between steps; other statements left as written.
        ("x = 1\ngood = tidy(cars)  # source\n\n# keep mpg\n>> select(mpg)\nprint(x)",
         "x = 1\ngood = (tidy(cars)  # source\n\n# keep mpg\n>> select(mpg))\nprint(x)"),
        # A pipe inside a function, and one at the top level after it.
        ("def f(d):\n    return (d\n    >> count())\nt = tidy(cars)\n>> count()",
         "def f(d):\n    return (d\n    >> count())\nt = (tidy(cars)\n>> count())"),
        # Text inside a string is not a pipe.
        ('s = """\n>> not code\n"""\ntidy(cars)\n>> select("mpg")\n', 's = """\n>> not code\n"""\n(tidy(cars)\n>> select("mpg"))\n'),
        # Valid Python stays.
        ("x = 1 + 2\nprint(x)\n", None),
        ("a >> 2", None),
    ],
)
def test_pipes(cell, expected):
    assert join(cell, [TIDY3]) == (cell if expected is None else expected)


@pytest.mark.parametrize(
    "cell, expected",
    [
        ('ggplot(df, aes(x="a", y="b"))\n + geom_point(alpha=0.7)\n + scale_x_log10()',
         '(ggplot(df, aes(x="a", y="b"))\n + geom_point(alpha=0.7)\n + scale_x_log10())'),
        ("p = ggplot(df)   # base\n# layers\n+ geom_point()  # points\n\n+ theme_bw()\np",
         "p = (ggplot(df)   # base\n# layers\n+ geom_point()  # points\n\n+ theme_bw())\np"),
        ("fig = (a | b)\n+ plot_layout(widths=[3, 2])", "fig = ((a | b)\n+ plot_layout(widths=[3, 2]))"),
        ("df >> ggplot()\n+ geom_point()  # layer", "(df >> ggplot()\n+ geom_point())  # layer"),
        # Inside a block too, as tidy3 joins pipes there (plot3 0.8 left blocks alone).
        ("for i in r:\n    p = ggplot(df)\n    + geom_point()", "for i in r:\n    p = (ggplot(df)\n    + geom_point())"),
        # Left alone: unary plus, a name that is no layer, one line already.
        ("x = 1\n+2", None),
        ("y = 1\n+ foo(2)", None),
        ("p = ggplot(df) + geom_point()", None),
    ],
)
def test_layers(cell, expected):
    assert join(cell, [PLOT3]) == (cell if expected is None else expected)


@pytest.mark.parametrize(
    "cell, context, expected",
    [
        # Valid Python keeps its meaning: an unindented "+" line joins only onto plot3's own.
        ("x = 2\n+ geom_point()", None, None),
        ("def geom_point():\n    return 1\np = ggplot(df)\n+ geom_point()", None, None),
        ("p = ggplot(df)\n+ geom_point()", {"geom_point": lambda: 1}, None),
        ("p = foo(df)\n+ geom_point()", {"foo": len}, None),
        ("p = n\n+ geom_point()", {"n": 2}, None),
        # tidy3 joined "+" after any pipe; now the pipe's last step must be plot3's.
        ("tidy(cars)\n>> filter(mpg > 20)\n+ geom_point()", None, "(tidy(cars)\n>> filter(mpg > 20))\n+ geom_point()"),
        ("tidy(cars)\n>> ggplot()\n+ geom_point()", None, "((tidy(cars)\n>> ggplot())\n+ geom_point())"),
        # A pipe from a data frame into ggplot() takes every layer, not only the first (tidy3's README).
        ("long\n>> ggplot(aes(x = species))\n+ geom_point()\n+ facet_wrap('measure')\n+ theme_bw()",
         {"long": object()},
         "((long\n>> ggplot(aes(x = species)))\n+ geom_point()\n+ facet_wrap('measure')\n+ theme_bw())"),
        # An indented "+" line is not Python, so it joins by name.
        ("x = 2\n  + geom_point()", None, "x = (2\n  + geom_point())"),
    ],
)
def test_layers_need_ownership(cell, context, expected):
    assert join(cell, ALL, context) == (cell if expected is None else expected)


def test_a_layer_joins_everywhere_in_an_explicit_scope():
    cell = "def geom_point():\n    return 1\np = ggplot(df)\n+ geom_point()"
    assert join(cell, ALL, always={"plot3"}).endswith("p = (ggplot(df)\n+ geom_point())")


def test_line_numbers_are_kept():
    cell = "x = 1\nbad = tidy(cars)\n>> select(mpg)\n>> filter(nope > 1)\nprint(x)"
    out = join(cell, ALL)
    assert len(out.splitlines()) == len(cell.splitlines())
    assert out.splitlines()[3] == ">> filter(nope > 1))"


def test_a_broken_pipe_is_joined_with_backslashes():
    cell = "tidy(cars)\n    >> filter(mpg >\n    >> select(mpg)"
    out = join_broken(cell, ALL)
    assert out.splitlines()[0] == "tidy(cars) \\"
    with pytest.raises(SyntaxError) as error:
        ast.parse(out)
    assert "unexpected indent" not in str(error.value)
    assert join_broken("tidy(cars) >> select(mpg)", ALL) == "tidy(cars) >> select(mpg)"


def test_rewrite_joins_after_the_repairs():
    cell = "tidy(cars)\n>> filter(!is_na(`miles per gallon`))\n>> select(Cus = NUM, Row)"
    assert rewrite(cell, ALL) == (
        "(tidy(cars)\n>> filter(~is_na(__r_name__('miles per gallon')))\n>> select(__r_assign__('Cus', (NUM)), Row))"
    )


@pytest.mark.parametrize(
    "cell",
    [
        "tidy(cars)\n>> filter(mpg > 20)",
        "ggplot(df)\n+ geom_point()",
        "tidy(cars)\n    >> filter(mpg >\n    >> select(mpg)",
        "df >> ggplot()\n+ geom_point()",
    ],
)
def test_joining_is_idempotent(cell):
    once = rewrite(cell, ALL)
    assert rewrite(once, ALL) == once
