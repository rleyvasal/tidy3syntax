"""Repairs: text that is not Python, rewritten by the call's name.

Cases come from the packages' own tests: tidy3's ``test_masking.py``,
tidy3a's ``test_notebooks.py``, plot3's ``test_masking.py`` and stats3's
``test_masking.py``.
"""

import pytest
from dialects import ALL, PLOT3, STATS3, TIDY3, TIDY3A

from tidysyntax import repair


@pytest.mark.parametrize(
    "source, expected",
    [
        # stats3: formulas in its functions become strings.
        ("penguins >> t_test(body_mass_g ~ sex)", "penguins >> t_test('body_mass_g ~ sex')"),
        ("t_test(penguins, body_mass_g ~ sex)", "t_test(penguins, 'body_mass_g ~ sex')"),
        ("wilcox_test(log(y)   ~ g, mu=0.3)", "wilcox_test('log(y) ~ g', mu=0.3)"),
        ("stats3.t_test(\n    body_mass_g ~\n      sex,\n)", "stats3.t_test(\n    'body_mass_g ~ sex',\n)"),
        ('t_test("y ~ g")', 't_test("y ~ g")'),
        ("friedman_test(v ~ k | id)", "friedman_test('v ~ k | id')"),
        ("bayes_glm(y ~ x + (1 | subject))", "bayes_glm('y ~ x + (1 | subject)')"),
        ("lm(`body mass` ~ sex)", "lm('`body mass` ~ sex')"),  # stats3 keeps backtick names
        ("other(y ~ g)", "other(y ~ g)"),
        ("text = 'a ~ b'", "text = 'a ~ b'"),
        ("df.filter(~mask)", "df.filter(~mask)"),
        ("x = ~x", "x = ~x"),
        # plot3: facets, with backtick names stripped.
        ("facet_grid(drv ~ cyl)", "facet_grid('drv ~ cyl')"),
        ('facet_grid(. ~ cyl, scales="free")', "facet_grid('. ~ cyl', scales=\"free\")"),
        ("facet_grid(facets = drv ~ .)", "facet_grid(facets = 'drv ~ .')"),
        ("facet_wrap(~`my col`)", "facet_wrap('~my col')"),
        ("facet_wrap(~cyl)", "facet_wrap(~cyl)"),  # valid Python: a reinterpretation, not a repair
        ("facet_wrap(cyl, labeller=f(~x))", "facet_wrap(cyl, labeller=f(~x))"),
    ],
)
def test_formulas(source, expected):
    assert repair(source, ALL) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ('case_when(bill_len > 45 ~ "long", default="short")', 'case_when((bill_len > 45, "long"), default="short")'),
        ('case_when((a, 1), b ~ 2)', 'case_when((a, 1), (b, 2))'),
        ("case_when(~is_na(x) ~ 0)", "case_when((~is_na(x), 0))"),
        ('case_when(a ~ case_when(b ~ "huge", default="long"), default="short")',
         'case_when((a, case_when((b, "huge"), default="long")), default="short")'),
        ('case_when(island == "Dream" ~ "a ~ b", default="x ~ y")',
         'case_when((island == "Dream", "a ~ b"), default="x ~ y")'),
        ("replace_when(x, x > 1 ~ 0)", "replace_when(x, (x > 1, 0))"),
        ("case_when(~a, default=2)", "case_when(~a, default=2)"),
    ],
)
def test_rules(source, expected):
    assert repair(source, [TIDY3]) == expected


@pytest.mark.parametrize(
    "source, message",
    [
        ("case_when(a ~ b ~ c)", "more than one ~"),
        ("case_when(a ~)", "both sides"),
        ("replace_when(x ~ 1, 2)", "column first"),
    ],
)
def test_malformed_rules_raise(source, message):
    with pytest.raises(SyntaxError, match=message):
        repair(source, [TIDY3])


@pytest.mark.parametrize(
    "source, expected",
    [
        ("d >> filter(!(x > 1), y != 2)", "d >> filter(~(x > 1), y != 2)"),
        ("mutate(\n    long=(\n        !is_na(b)\n        & (i != 'D')\n    )\n)\n",
         "mutate(\n    long=(\n        ~is_na(b)\n        & (i != 'D')\n    )\n)\n"),
        ("select(\n    !starts_with('b')\n)\n", "select(\n    ~starts_with('b')\n)\n"),
        ("!pip install tidy3\nmutate(\n    !a\n)\n", "!pip install tidy3\nmutate(\n    ~a\n)\n"),
        ("files = !ls\nd >> select(!z)  # !kept", "files = !ls\nd >> select(~z)  # !kept"),
        ('filter(s == "!a", !b)', 'filter(s == "!a", ~b)'),
        ("!pip install x\n", "!pip install x\n"),
        ("x = 1\n!ls\n", "x = 1\n!ls\n"),
        ("!!pwd\n", "!!pwd\n"),
    ],
)
def test_negation(source, expected):
    assert repair(source, ALL) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("select(Cus = NUM, Source_Row)", "select(__r_assign__('Cus', (NUM)), Source_Row)"),
        ('group_by(w = bins(t, "3 days"), lat, dropna=False)',
         'group_by(__r_assign__(\'w\', (bins(t, "3 days"))), lat, dropna=False)'),
        ("ta.mutate(c = f(a, b=1), d, k = 1)", "ta.mutate(__r_assign__('c', (f(a, b=1))), d, k = 1)"),
        ("summarise(n = n(), across(x))", "summarise(__r_assign__('n', (n())), across(x))"),
        ("mutate(c = 1, k = 2)", "mutate(c = 1, k = 2)"),
        ("group_by(lat, w = f(t))", "group_by(lat, w = f(t))"),
        ("group_by(axis = 'g', lat)", "group_by(axis = 'g', lat)"),
        ("mutate(c = 1, *rest)", "mutate(c = 1, *rest)"),
        ("mutate(a = mutate(b = 1, c), d)", "mutate(__r_assign__('a', (mutate(__r_assign__('b', (1)), c))), d)"),
        ("mutate(`new hp` = hp * 2, x)", "mutate(__r_assign__('new hp', (hp * 2)), x)"),
        ("filter(`a b` == 1)", "filter(__r_name__('a b') == 1)"),
    ],
)
def test_assignments_in_the_order_written(source, expected):
    assert repair(source, [TIDY3, TIDY3A]) == expected


def test_tidy3a_stage_runs_before_keywords():
    source = "d >> mutate(c = a * 2, [x, y] = f(x), k = 1)"
    assert repair(source, [TIDY3A]) == (
        "d >> mutate(__r_assign__('c', (a * 2)), __r_assign__([x, y], f(x)), k = 1)"
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        ("aes(x=`First Name`)", "aes(x=__r_name__('First Name'))"),
        ("aes(y=`Age (%)`)", "aes(y=__r_name__('Age (%)'))"),
        ('ggplot(df, aes(x=`a b`)) + labs(title="see `hp`")  # `note`',
         "ggplot(df, aes(x=__r_name__('a b'))) + labs(title=\"see `hp`\")  # `note`"),
        ("labs(title='it\\'s `x`')", "labs(title='it\\'s `x`')"),
    ],
)
def test_backtick_names(source, expected):
    assert repair(source, [PLOT3]) == expected


def test_a_call_belonging_to_no_dialect_is_left_alone():
    assert repair("lm(y ~ x)", [TIDY3, TIDY3A, PLOT3]) == "lm(y ~ x)"
    assert repair("lm(y ~ x)", [STATS3]) == "lm('y ~ x')"
