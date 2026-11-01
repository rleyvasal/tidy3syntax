"""Which package a call in a cell belongs to.

A reinterpretation changes the meaning of valid Python, so it runs only in
calls of the package that reads the text that way. The rule, as tidy3
settled it:

1. A local variable of an enclosing function, lambda or comprehension is
   the notebook's own.
2. Otherwise the latest top-level binding of the name in the cell before
   the call decides: an import gives that module (a star import gives a
   package's exported names), and any other binding (``def``, assignment,
   ``for`` target, ...) makes the name the notebook's own.
3. Otherwise the context decides: in IPython, the module of the live value.
4. A name the context does not have is the package's that exports it, when
   exactly one does. Such a cell fails with a NameError whatever a rewrite
   does, so this changes no result and keeps error messages as they were.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Sequence
from types import ModuleType
from typing import Any

from tidysyntax.dialect import Dialect


class ModuleRef(str):
    """A context value that only says which module a name came from, for contexts
    without live values, such as an export that read the earlier cells' imports."""

    __slots__ = ()


def module_of(value: Any) -> str | None:
    """The dotted module a value comes from: a module's own name, a function's or
    class's ``__module__``, or the module of an instance's type."""
    if isinstance(value, ModuleRef):
        return str(value)
    if isinstance(value, ModuleType):
        return value.__name__
    if isinstance(value, type) or callable(value):
        module = getattr(value, "__module__", None)
        if isinstance(module, str):
            return module
    return type(value).__module__


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


class Owners:
    """The bindings of one parsed cell, and the rule above applied to them."""

    def __init__(self, tree: ast.Module, context: Mapping[str, Any] | None, dialects: Sequence[Dialect]):
        self.context = context
        self.dialects = tuple(dialects)
        self.bindings: dict[str, list[tuple[tuple[int, int], str | None]]] = {}
        stack: list[ast.AST] = list(tree.body)
        while stack:
            node = stack.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self._bind(node.name, node, None)
                continue
            if isinstance(node, _SCOPES):
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        self._bind(alias.asname, node, alias.name)
                    else:
                        top = alias.name.split(".")[0]
                        self._bind(top, node, top)
            elif isinstance(node, ast.ImportFrom):
                module = node.module if node.module and node.level == 0 else None
                for alias in node.names:
                    if alias.name == "*":
                        for dialect in self.dialects:
                            if dialect.owns_module(module):
                                for name in dialect.exported():
                                    self._bind(name, node, module)
                    else:
                        self._bind(alias.asname or alias.name, node, module)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                self._bind(node.id, node, None)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                self._bind(node.name, node, None)
            stack.extend(ast.iter_child_nodes(node))
        for found in self.bindings.values():
            found.sort(key=lambda item: item[0])

    def _bind(self, name: str, node: ast.AST, module: str | None) -> None:
        end = (getattr(node, "end_lineno", None) or node.lineno, getattr(node, "end_col_offset", None) or 0)
        self.bindings.setdefault(name, []).append((end, module))

    def module(self, name: str, at: tuple[int, int]) -> str | None:
        """The module *name* comes from when used at ``(line, byte column)`` *at*; ``None`` for the notebook's own."""
        before = [module for end, module in self.bindings.get(name, ()) if end <= at]
        if before:
            return before[-1]
        if self.context is not None and name in self.context:
            return module_of(self.context[name])
        exporting = [d.package for d in self.dialects if name in d.exported()]
        return exporting[0] if len(exporting) == 1 else None

    def owner(self, func: ast.AST, at: tuple[int, int], local: Iterable[str] = ()) -> str | None:
        """The package of the dialects that a call's function belongs to, or ``None``."""
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            name = func.value.id
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            return None
        if name in set(local):
            return None
        module = self.module(name, at)
        for dialect in self.dialects:
            if dialect.owns_module(module):
                return dialect.package
        return None


def local_names(node: ast.AST) -> set[str]:
    """Parameters and names bound in a function's, lambda's or comprehension's own scope."""
    names: set[str] = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        arguments = node.args
        names.update(a.arg for a in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs])
        names.update(a.arg for a in (arguments.vararg, arguments.kwarg) if a is not None)
        body = node.body if isinstance(node.body, list) else [node.body]
    else:
        body = [generator.target for generator in getattr(node, "generators", [])]
    stack = list(body)
    while stack:
        child = stack.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(child.name)
            continue
        if isinstance(child, _SCOPES):
            continue
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            names.add(child.id)
        stack.extend(ast.iter_child_nodes(child))
    return names


def owned_calls(
    source: str,
    tree: ast.Module,
    dialects: Sequence[Dialect],
    context: Mapping[str, Any] | None,
    names: Iterable[str],
) -> dict[int, str]:
    """For each call to one of *names* that a dialect's package owns: the offset in *source*
    just past the function's name, mapped to that package."""
    owners = Owners(tree, context, dialects)
    lines = source.split("\n")
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line) + 1)
    wanted = frozenset(names)
    found: dict[int, str] = {}

    def visit(node: ast.AST, local: frozenset[str]) -> None:
        if isinstance(node, _SCOPES):
            local = local | local_names(node)
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in wanted:
                package = owners.owner(func, (func.lineno, func.col_offset), local)
                if package is not None and func.end_lineno is not None and func.end_col_offset is not None:
                    row = func.end_lineno
                    column = len(lines[row - 1].encode()[: func.end_col_offset].decode(errors="ignore"))
                    found[starts[row - 1] + column] = package
        for child in ast.iter_child_nodes(node):
            visit(child, local)

    visit(tree, frozenset())
    return found


def imported_names(*sources: str, dialects: Sequence[Dialect] = ()) -> dict[str, ModuleRef]:
    """The names the cells' top-level imports bind, in order, as a context for a rewrite
    that has no live namespace (an export reading a notebook's earlier cells). A star
    import binds the exported names of the *dialects* whose package it imports."""
    names: dict[str, ModuleRef] = {}
    for source in sources:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.asname or alias.name.split(".")[0]
                    names[target] = ModuleRef(alias.name if alias.asname else alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                for alias in node.names:
                    if alias.name != "*":
                        names[alias.asname or alias.name] = ModuleRef(node.module)
                    else:
                        for dialect in dialects:
                            if dialect.owns_module(node.module):
                                names.update(dict.fromkeys(dialect.exported(), ModuleRef(node.module)))
    return names
