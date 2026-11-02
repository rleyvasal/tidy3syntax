"""The coordinator, in real IPython shells, with two small packages made for the tests."""

import sys
import types

import pytest

pytest.importorskip("IPython")
from IPython.core.interactiveshell import InteractiveShell  # noqa: E402

import tidy3syntax.ipython as coordinator  # noqa: E402
from tidy3syntax import Dialect  # noqa: E402

VERBS = Dialect("fakeverbs", negation_calls={"keep"}, exports={"keep"})
PLOT = Dialect("fakeplot", power_calls={"geom_function"}, exports={"geom_function"})


def _module(name, code):
    module = types.ModuleType(name)
    exec(code, module.__dict__)
    return module


@pytest.fixture(autouse=True)
def packages(monkeypatch):
    monkeypatch.setitem(sys.modules, "fakeverbs", _module("fakeverbs", "def keep(x):\n    return x\n"))
    monkeypatch.setitem(sys.modules, "fakeplot", _module("fakeplot", "def geom_function(f):\n    return f(3)\n"))
    monkeypatch.setattr(coordinator, "_ENTRY_CACHE", {})


@pytest.fixture
def shell():
    InteractiveShell.clear_instance()
    shell = InteractiveShell.instance()
    yield shell
    for package in coordinator.registered(shell):
        coordinator.unregister(shell, package)
    InteractiveShell.clear_instance()


def run(shell, cell):
    result = shell.run_cell(cell)
    assert result.success, result.error_before_exec or result.error_in_exec
    return shell.user_ns


IMPORTS = "from fakeverbs import keep\nfrom fakeplot import geom_function\n"


@pytest.mark.parametrize("order", [(VERBS, PLOT), (PLOT, VERBS)])
def test_one_transformer_for_every_package_in_any_load_order(shell, order):
    for dialect in order:
        coordinator.register(shell, dialect)
    assert sum(coordinator._is_coordinator(t) for t in shell.input_transformers_cleanup) == 1
    ns = run(shell, IMPORTS + "a = keep(!0)\nb = geom_function(lambda x: x ^ 2)")
    assert (ns["a"], ns["b"]) == (-1, 9)


def test_the_notebooks_own_function_keeps_python_meaning(shell):
    coordinator.register(shell, PLOT)
    ns = run(shell, "def geom_function(f):\n    return f(3)\nr = geom_function(lambda x: x ^ 2)")
    assert ns["r"] == 1
    # An explicit scope for one cell reinterprets it anyway.
    ns = run(shell, "%%tidy3syntax fakeplot\nr = geom_function(lambda x: x ^ 2)")
    assert ns["r"] == 9
    # And for the session.
    coordinator.register(shell, PLOT, reinterpret="always")
    ns = run(shell, "r = geom_function(lambda x: x ^ 2)")
    assert ns["r"] == 9


def test_the_transformer_stays_first(shell):
    coordinator.register(shell, VERBS)

    def router(lines):  # CRAFT's router puts itself first
        return lines

    shell.input_transformers_cleanup.insert(0, router)
    run(shell, "x = 1")
    assert coordinator._is_coordinator(shell.input_transformers_cleanup[0])
    assert router in shell.input_transformers_cleanup


def test_the_importing_cell_gets_the_packages_syntax(shell, monkeypatch):
    def load(shell):  # what the package's entry point would do: its notebook extension
        coordinator.register(shell, PLOT)

    monkeypatch.setattr(coordinator, "_ENTRY_CACHE", {"fakeplot": load})
    coordinator.register(shell, VERBS)
    ns = run(shell, "from fakeplot import geom_function\nr = geom_function(lambda x: x ^ 2)")
    assert ns["r"] == 9
    assert "fakeplot" in coordinator.registered(shell)


def test_ast_passes_are_registered_once_and_replaced(shell):
    class Pass:
        def visit(self, tree):
            return tree

    first, second = Pass(), Pass()
    coordinator.register(shell, VERBS, ast_transformer=first)
    coordinator.register(shell, VERBS, ast_transformer=second)
    assert first not in shell.ast_transformers and shell.ast_transformers.count(second) == 1
    coordinator.unregister(shell, "fakeverbs")
    assert second not in shell.ast_transformers


def test_unregistering_the_last_package_removes_the_coordinator(shell):
    coordinator.register(shell, VERBS)
    coordinator.register(shell, PLOT)
    coordinator.unregister(shell, "fakeverbs")
    assert coordinator.registered(shell) == ("fakeplot",)
    coordinator.unregister(shell, "fakeplot")
    assert not any(coordinator._is_coordinator(t) for t in shell.input_transformers_cleanup)
    assert coordinator.registered(shell) == ()


def test_a_package_can_be_turned_off_and_on(shell):
    coordinator.register(shell, PLOT)
    coordinator.enable(shell, "fakeplot", False)
    ns = run(shell, IMPORTS + "r = geom_function(lambda x: x ^ 2)")
    assert ns["r"] == 1
    coordinator.enable(shell, "fakeplot")
    ns = run(shell, "r = geom_function(lambda x: x ^ 2)")
    assert ns["r"] == 9


def test_shell_lines_and_placeholders(shell):
    coordinator.register(shell, VERBS)
    ns = run(shell, "out = !echo hi\nname = __r_name__('a b')")
    assert list(ns["out"]) == ["hi"] and ns["name"] == "a b"
