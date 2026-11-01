"""Properties over the corpus and the standard library's own source.

1. Repairs leave every cell that parses unchanged, whatever owns its calls.
2. With every dialect registered and no context, a cell that parses and
   calls nothing a dialect owns is unchanged.
3. Rewriting is idempotent.
"""

import ast
import inspect

import pytest
import test_reinterpretations
import test_repairs
from dialects import ALL

from tidysyntax import repair, rewrite

# Modules whose source calls filter(), select(), count(), and the like.
STDLIB = ["ast", "inspect", "textwrap", "json.decoder", "pathlib", "argparse", "selectors", "difflib", "fnmatch"]


def _source(name):
    module = __import__(name, fromlist=["_"])
    return inspect.getsource(module)


@pytest.mark.parametrize("name", STDLIB)
def test_repairs_leave_the_standard_library_alone(name):
    source = _source(name)
    assert repair(source, ALL) == source


@pytest.mark.parametrize("name", STDLIB)
def test_rewrite_leaves_the_standard_library_alone(name):
    source = _source(name)
    assert rewrite(source, ALL) == source


def _corpus():
    cells = []
    for module in (test_repairs, test_reinterpretations):
        for item in vars(module).values():
            for mark in getattr(item, "pytestmark", []):
                if mark.name == "parametrize":
                    for case in mark.args[1]:
                        if isinstance(case, tuple) and isinstance(case[0], str):
                            cells.append(case[0])
    return cells


CORPUS = _corpus()
# Cells whose R syntax belongs to no dialect's call, or that are broken: Python reports them.
LEFT_FOR_PYTHON = {
    "other(y ~ g)",
    "group_by(axis = 'g', lat)",
    "s3.t_test(y ~ g)",
    "geom_function(lambda x: x ^ 2) + facet_wrap(~cyl)\nif:",
}


def test_the_corpus_is_large():
    assert len(CORPUS) > 60


@pytest.mark.parametrize("cell", CORPUS)
def test_repairs_leave_valid_cells_alone(cell):
    try:
        ast.parse(cell)
    except SyntaxError:
        pytest.skip("not Python before the repairs")
    assert repair(cell, ALL) == cell


@pytest.mark.parametrize("cell", CORPUS)
def test_rewrite_is_idempotent(cell):
    try:
        once = rewrite(cell, ALL)
    except SyntaxError:
        pytest.skip("a malformed rule, reported")
    assert rewrite(once, ALL) == once


@pytest.mark.parametrize("cell", CORPUS)
def test_rewritten_cells_parse(cell):
    try:
        out = rewrite(cell, ALL)
    except SyntaxError:
        pytest.skip("a malformed rule, reported")
    if cell in LEFT_FOR_PYTHON or cell.lstrip().startswith("!") or "\n!" in cell or "= !" in cell:
        pytest.skip("not Python by design: left for Python to report, or an IPython shell line")
    ast.parse(out)
