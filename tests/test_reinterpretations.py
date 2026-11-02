"""Reinterpretations: valid Python a package reads differently, rewritten only in its own calls.

The cases are the design's (docs/design.md, §6) and the bugs plot3 0.7.0
had: a notebook's own geom_function lost XOR, its own facet_wrap got a
string for ``~5``.
"""

import types

import pytest
from dialects import ALL, PLOT3

from tidy3syntax import ModuleRef, imported_names, rewrite

USER_GEOM_FUNCTION = "def geom_function(fun):\n    return fun(3)\n"


@pytest.mark.parametrize(
    "cell, expected",
    [
        # The notebook's own geom_function keeps XOR.
        (USER_GEOM_FUNCTION + "r = geom_function(lambda x: x ^ 2)", None),
        ("from plot3 import *\n" + USER_GEOM_FUNCTION + "r = geom_function(lambda x: x ^ 2)", None),
        ("def f(geom_function):\n    return geom_function(lambda x: x ^ 2)", None),
        ("for geom_function in fs:\n    geom_function(lambda x: x ^ 2)", None),
        ("import numpy as p3\np3.geom_function(lambda x: x ^ 2)", None),
        ("geom_function(lambda x: x ^ 2) + facet_wrap(~cyl)\nif:", None),  # does not parse: owners unknown
        # plot3's own calls take R's meaning.
        ("from plot3 import *\ngeom_function(lambda x: 2*x^3)", "from plot3 import *\ngeom_function(lambda x: 2*x**3)"),
        ("import plot3 as p3\np3.geom_function(lambda x: x ^ 2)", "import plot3 as p3\np3.geom_function(lambda x: x ** 2)"),
        ("from plot3 import geom_function as gf\ngf(lambda x: x ^ 2)", None),  # gf is not a power call by name
        ("geom_function(lambda x: np.sin(x^2))", "geom_function(lambda x: np.sin(x**2))"),
        ("geom_function(y = x^3) + facet_wrap(~cyl)", "geom_function(y = x**3) + facet_wrap('~cyl')"),
        ("x ^= 1\ngeom_function(lambda x: x ^ 2)", "x ^= 1\ngeom_function(lambda x: x ** 2)"),
        # Facets.
        ("def facet_wrap(v):\n    return v\nf = facet_wrap(~5)", None),
        ("def facet_wrap(v):\n    return v\nf = facet_wrap(drv ~ cyl)", "def facet_wrap(v):\n    return v\nf = facet_wrap('drv ~ cyl')"),
        ("facet_wrap( ~ cyl , ncol=2)", "facet_wrap( '~ cyl' , ncol=2)"),
        ("p + facet_wrap(\n    ~ gear,\n    ncol=2)", "p + facet_wrap(\n    '~ gear',\n    ncol=2)"),
        ('facet_wrap("~cyl")', None),
        # A backtick name the backtick repair already rewrote keeps its name inside the formula.
        ("facet_wrap(~__r_name__('my col'))", "facet_wrap('~my col')"),
    ],
)
def test_only_plot3_calls_are_reinterpreted(cell, expected):
    assert rewrite(cell, ALL) == (cell if expected is None else expected)


def test_the_context_decides_names_the_cell_does_not_bind():
    plot3 = types.ModuleType("plot3")

    def own(fun):
        return fun(3)

    def geom_function(fun):
        return fun

    geom_function.__module__ = "plot3.geoms"
    cell = "r = geom_function(lambda x: x ^ 2)"
    assert rewrite(cell, [PLOT3], {"geom_function": own}) == cell
    assert rewrite(cell, [PLOT3], {"geom_function": geom_function}) == "r = geom_function(lambda x: x ** 2)"
    assert rewrite("p3.geom_function(lambda x: x ^ 2)", [PLOT3], {"p3": plot3}) == "p3.geom_function(lambda x: x ** 2)"
    # A name the context lacks is the exporting package's: the cell fails with NameError either way.
    assert rewrite(cell, [PLOT3], {}) == "r = geom_function(lambda x: x ** 2)"


def test_earlier_cells_imports_as_a_context():
    context = imported_names("import numpy as np", "from mylib import geom_function")
    assert context == {"np": ModuleRef("numpy"), "geom_function": ModuleRef("mylib")}
    assert rewrite("geom_function(lambda x: x ^ 2)", [PLOT3], context) == "geom_function(lambda x: x ^ 2)"
    context = imported_names("from plot3 import *", dialects=[PLOT3])
    assert context["geom_function"] == "plot3"


def test_an_explicit_scope_reinterprets_any_call():
    cell = USER_GEOM_FUNCTION + "r = geom_function(lambda x: x ^ 2)"
    assert rewrite(cell, ALL, always={"plot3"}).endswith("geom_function(lambda x: x ** 2)")
    # It widens reinterpretations only; and it names a package, not a call.
    assert rewrite(cell, ALL, always={"tidy3"}) == cell


@pytest.mark.parametrize(
    "cell, value",
    [
        (USER_GEOM_FUNCTION + "r = geom_function(lambda x: x ^ 2)", 1),
        ("def facet_wrap(v):\n    return v\nr = facet_wrap(~5)", -6),
    ],
)
def test_the_rewritten_cells_run_with_python_meaning(cell, value):
    namespace: dict = {}
    exec(rewrite(cell, ALL), namespace)
    assert namespace["r"] == value
