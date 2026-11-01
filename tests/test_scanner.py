import pytest

from tidy3syntax.scanner import Spans, arguments, calls, keyword, top_level_tildes


def code(source):
    return "".join(source[a:b] for a, b in Spans.of(source).code)


@pytest.mark.parametrize(
    "source, expected",
    [
        ('f("a # b") # c', "f() "),
        ("f('it\\'s') + g()", "f() + g()"),
        ('s = """x\n`y`\n"""\nh()', "s = \nh()"),
        ("rb'raw' + x", "rb + x"),
        ("aes(y=`Age (%)`)", "aes(y=`Age (%)`)"),
        ("aes(y=`it's`)", "aes(y=`it's`)"),  # a quote inside a backtick name opens no string
    ],
)
def test_spans_leave_out_strings_and_comments(source, expected):
    assert code(source) == expected


def test_calls_find_bare_and_prefixed_calls_outside_strings():
    source = 'filter(x) + ta.filter(y, z) + "filter(no)" + df.attr.filter(w)  # filter(no)'
    found = calls(source, {"filter"})
    assert [(c.prefix, source[c.open + 1 : c.close]) for c in found] == [(None, "x"), ("ta", "y, z")]
    assert [source[a:b] for a, b in found[1].arguments] == ["y", " z"]


def test_arguments_skip_brackets_in_strings_and_backtick_names():
    source = 'aes(x=`a (b`, y="c,)", z=f(1, 2),)'
    close, spans = arguments(source, 3)
    assert close == len(source) - 1
    assert [source[a:b] for a, b in spans] == ["x=`a (b`", ' y="c,)"', " z=f(1, 2)"]
    assert arguments("f(a, (b", 1) is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("y ~ x", [True]),
        (". ~ cyl", [True]),
        ("~cyl", [False]),
        ("a and ~b", [False]),
        ("~is_na(x) ~ 0", [False, True]),
        ("f(a ~ b)", []),
        ("`my col` ~ g", [True]),
        ("'a ~ b'", []),
    ],
)
def test_tildes_are_binary_after_an_operand(text, expected):
    assert [binary for _, binary in top_level_tildes(text)] == expected


def test_keyword():
    assert keyword("  name = 1") == ("name", 8)
    assert keyword("a == 1") is None
    assert keyword("`a b` = 1") is None
