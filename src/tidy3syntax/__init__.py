"""R syntax in notebook cells, rewritten to Python, shared by tidy3, tidy3a, plot3 and stats3.

Each package describes its syntax as a :class:`Dialect`; :func:`rewrite`
turns a cell into Python for all of them at once. Repairs (text that is not
Python) run by the call's name; reinterpretations (valid Python a package
reads differently) run only in the package's own calls. See
``docs/design.md``.
"""

from tidy3syntax.__version__ import __version__
from tidy3syntax.dialect import Dialect
from tidy3syntax.ownership import (
    ModuleRef,
    Owners,
    imported_names,
    module_of,
    owned_calls,
)
from tidy3syntax.pipeline import reinterpret, rewrite
from tidy3syntax.placeholders import ASSIGN, NAME, RAssign, RName, runtime_values
from tidy3syntax.repairs import repair

__all__ = [
    "ASSIGN",
    "NAME",
    "Dialect",
    "ModuleRef",
    "Owners",
    "RAssign",
    "RName",
    "__version__",
    "imported_names",
    "module_of",
    "owned_calls",
    "reinterpret",
    "repair",
    "rewrite",
    "runtime_values",
]
