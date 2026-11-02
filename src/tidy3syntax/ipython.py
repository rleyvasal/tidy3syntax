"""The coordinator: one IPython input transformer for every package's syntax.

Each package's notebook extension calls :func:`register` with its dialect and
its AST pass. The first call installs one input transformer on the shell's
``input_transformers_cleanup``; it runs :func:`tidy3syntax.rewrite` with
every registered dialect and the live namespace as the context, so the
result no longer depends on the order the packages were loaded in. Before
each cell it moves itself back to the front of that list, ahead of anything
appended since (CRAFT's router, which tidy3 kept behind by the same means).

A cell that imports a package declaring a ``tidy3syntax.dialects`` entry
point, not yet registered, gets that package's syntax at once: its dialect's
``extension`` (the package's notebook loader) is called before the cell is
rewritten, so ``from plot3 import *`` and ``aes(x=wt)`` work in one cell.

Explicit scopes widen reinterpretations: ``%%tidy3syntax plot3`` as a cell's
first line for that cell, or ``register(..., reinterpret="always")`` for the
session. IPython is imported only by the caller; this module needs none.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Sequence
from importlib import metadata
from typing import Any

from tidy3syntax.dialect import Dialect
from tidy3syntax.pipeline import rewrite
from tidy3syntax.placeholders import runtime_values

ENTRY_POINTS = "tidy3syntax.dialects"
_ATTRIBUTE = "_tidy3syntax_coordinator"
_SCOPE = re.compile(r"\A\s*%%tidy3syntax\b([^\n]*)\n?")


class Coordinator:
    """The dialects, AST passes and settings of one shell; see the module's docstring."""

    def __init__(self, shell: Any):
        self.shell = shell
        self.dialects: dict[str, Dialect] = {}
        self.ast_transformers: dict[str, Any] = {}
        self.always: set[str] = set()
        self.off: set[str] = set()
        self._loading: set[str] = set()

    # -- the transformer -----------------------------------------------------

    def transform(self, lines: list[str]) -> list[str]:
        """IPython input transformer: the cell, rewritten for every registered dialect."""
        if not lines:
            return lines
        source = "".join(lines)
        always = set(self.always)
        scope = _SCOPE.match(source)
        if scope:
            always.update(scope.group(1).replace(",", " ").split())
            source = source[scope.end() :]
        self._load_imported(source)
        dialects = self.active()
        if not dialects and not scope:
            return lines
        # A malformed rule raises SyntaxError naming its function, which IPython reports for the cell.
        out = rewrite(source, dialects, getattr(self.shell, "user_ns", None), always)
        if out == "".join(lines):
            return lines
        if not out.endswith("\n"):
            out += "\n"
        return out.splitlines(keepends=True)

    transform.tidy3syntax = True  # type: ignore[attr-defined]

    def active(self) -> list[Dialect]:
        return [d for name, d in self.dialects.items() if name not in self.off]

    # -- keeping the transformer first ---------------------------------------

    def install(self) -> None:
        transformers = getattr(self.shell, "input_transformers_cleanup", None)
        if not isinstance(transformers, list):
            return
        transformers[:] = [t for t in transformers if not _is_coordinator(t)]
        transformers.insert(0, self.transform)

    def before_cell(self, *_: Any) -> None:
        """``pre_run_cell``: move the transformer back to the front if something was put before it."""
        transformers = getattr(self.shell, "input_transformers_cleanup", None)
        if isinstance(transformers, list) and (not transformers or not _is_coordinator(transformers[0])):
            self.install()

    def uninstall(self) -> None:
        transformers = getattr(self.shell, "input_transformers_cleanup", None)
        if isinstance(transformers, list):
            transformers[:] = [t for t in transformers if not _is_coordinator(t)]
        try:
            self.shell.events.unregister("pre_run_cell", self.before_cell)
        except Exception:
            pass

    # -- the importing cell --------------------------------------------------

    def _load_imported(self, source: str) -> None:
        """Register, before the cell is rewritten, each package the cell imports that has an entry point."""
        imported = _imported_packages(source)
        if not imported:
            return
        for name, load in _entry_points().items():
            if name in imported and name not in self.dialects and name not in self._loading:
                self._loading.add(name)
                try:
                    load(self.shell)
                except Exception:
                    pass  # the package's own import in the cell reports what is wrong
                finally:
                    self._loading.discard(name)


def _is_coordinator(transformer: Any) -> bool:
    return bool(getattr(transformer, "tidy3syntax", False))


def coordinator(shell: Any) -> Coordinator:
    """The shell's coordinator, created and installed on first use."""
    found = getattr(shell, _ATTRIBUTE, None)
    if found is None:
        found = Coordinator(shell)
        setattr(shell, _ATTRIBUTE, found)
        found.install()
        try:
            shell.events.register("pre_run_cell", found.before_cell)
        except Exception:
            pass
        namespace = getattr(shell, "user_ns", None)
        if isinstance(namespace, dict):
            for name, value in runtime_values().items():
                namespace.setdefault(name, value)
    return found


def register(
    shell: Any,
    dialect: Dialect,
    *,
    ast_transformer: Any = None,
    reinterpret: str = "owned",
) -> Coordinator:
    """Add *dialect* (and the package's *ast_transformer*) to the shell's coordinator.

    Registering a package again replaces its dialect and AST pass. With
    ``reinterpret="always"`` the dialect's reinterpretations apply to every
    call of its names, owned or not, for the session.
    """
    if reinterpret not in ("owned", "always"):
        raise ValueError('reinterpret is "owned" or "always"')
    found = coordinator(shell)
    name = dialect.package
    found.dialects[name] = dialect
    found.off.discard(name)
    (found.always.add if reinterpret == "always" else found.always.discard)(name)
    transformers = getattr(shell, "ast_transformers", None)
    old = found.ast_transformers.pop(name, None)
    if isinstance(transformers, list) and old is not None:
        transformers[:] = [t for t in transformers if t is not old]
    if ast_transformer is not None:
        found.ast_transformers[name] = ast_transformer
        if isinstance(transformers, list):
            transformers.append(ast_transformer)
    found.install()
    return found


def unregister(shell: Any, package: str) -> None:
    """Remove *package*'s dialect and AST pass; the coordinator leaves when no package is left."""
    found = getattr(shell, _ATTRIBUTE, None)
    if found is None:
        return
    found.dialects.pop(package, None)
    found.always.discard(package)
    found.off.discard(package)
    old = found.ast_transformers.pop(package, None)
    transformers = getattr(shell, "ast_transformers", None)
    if isinstance(transformers, list) and old is not None:
        transformers[:] = [t for t in transformers if t is not old]
    if not found.dialects:
        found.uninstall()
        delattr(shell, _ATTRIBUTE)


def enable(shell: Any, package: str, on: bool = True) -> None:
    """Turn a registered package's source rewrites on or off, keeping its registration (tidy3's ``%tidy3_mask``)."""
    found = getattr(shell, _ATTRIBUTE, None)
    if found is not None:
        (found.off.discard if on else found.off.add)(package)


def registered(shell: Any) -> Sequence[str]:
    """The packages registered with the shell's coordinator."""
    found = getattr(shell, _ATTRIBUTE, None)
    return tuple(found.dialects) if found is not None else ()


# -- entry points ------------------------------------------------------------

_ENTRY_CACHE: dict[str, Callable[[Any], Any]] | None = None


def _entry_points() -> dict[str, Callable[[Any], Any]]:
    """Package name -> a function that loads its notebook support into a shell, read once from the
    ``tidy3syntax.dialects`` entry points (each names a function returning the package's dialect)."""
    global _ENTRY_CACHE
    if _ENTRY_CACHE is None:
        found: dict[str, Callable[[Any], Any]] = {}
        try:
            points = metadata.entry_points(group=ENTRY_POINTS)
        except Exception:
            points = ()
        for point in points:
            found[point.name] = _lazy(point)
        _ENTRY_CACHE = found
    return _ENTRY_CACHE


def _lazy(point: Any) -> Callable[[Any], Any]:
    def load(shell: Any) -> Any:
        dialect = _dialect_of(point)
        if dialect is None or dialect.extension is None:
            return None
        return _import(dialect.extension)(shell)

    return load


def _dialect_of(point: Any) -> Dialect | None:
    """The dialect an entry point names: a Dialect, or a function returning one."""
    found = point.load()
    if callable(found) and not isinstance(found, Dialect):
        found = found()
    return found if isinstance(found, Dialect) else None


def _import(path: str) -> Callable[..., Any]:
    module, _, name = path.partition(":")
    target: Any = __import__(module, fromlist=[name])
    for part in name.split("."):
        target = getattr(target, part)
    return target


def installed() -> list[Dialect]:
    """The dialects of every installed package that declares a ``tidy3syntax.dialects``
    entry point, for rewriting without a notebook (an export). A package whose entry
    point fails to load is left out."""
    found = []
    try:
        points = metadata.entry_points(group=ENTRY_POINTS)
    except Exception:
        points = ()
    for point in points:
        try:
            dialect = _dialect_of(point)
        except Exception:
            continue
        if dialect is not None:
            found.append(dialect)
    return sorted(found, key=lambda d: d.package)


def _imported_packages(source: str) -> set[str]:
    """The top-level packages a cell imports (``import a.b``, ``from a import x``), read without running it."""
    if "import" not in source:
        return set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        names = set(re.findall(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)", source, re.M))
        return names
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names
