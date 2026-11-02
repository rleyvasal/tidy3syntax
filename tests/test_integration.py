"""tidy3, tidy3a, plot3 and stats3 in one notebook, in all 24 load orders.

The design's integration test (docs/design.md, §6 and decision 5): it lives
here and runs in this repository's CI on pull requests and weekly, against
the packages' releases. Each order runs in a fresh process, since the
packages' extensions keep module-level state. Skipped unless all four are
installed.
"""

import itertools
import json
import subprocess
import sys
import textwrap

import pytest

PACKAGES = {"tidy3": "tidy3.jupyter", "tidy3a": "tidy3a.jupyter", "plot3": "plot3", "stats3": "stats3.jupyter"}
for _name in PACKAGES:
    pytest.importorskip(_name)
pytest.importorskip("IPython")

# One cell per package, each using its R syntax, then checks that valid Python
# keeps its meaning where no package owns the call.
CELLS = [
    # tidy3: a multi-line pipe with ! and a keyword before a positional argument.
    "from tidy3 import *\n"
    'cars = tidy({"mpg": [21.0, 30.0, 25.0], "wt": [2.6, 1.9, 2.4]})\n'
    "slow = cars\n"
    ">> filter(!(mpg > 24))\n"
    ">> select(m = mpg, wt)\n"
    "tidy3_result = slow.collect()['m'].to_list()",
    # tidy3a: ! and a keyword before a positional argument in group_by.
    "from tidy3a import *\nimport numpy as np\n"
    "cloud = read_array(np.array([[1.0, 10], [2, 20], [3, 30]]), dims={'p': infer, 'f': 2},\n"
    "                   labels={'f': ['a', 'b']}, field_axis='f')\n"
    "tidy3a_result = (cloud >> filter(!(a > 2)) >> group_by(big = b > 15, a) >> summarise(n = mean(b)) >> pull(n)).tolist()",
    # plot3: a + layer line, ^ as power in geom_function, a facet formula.
    "from plot3 import *\nimport pandas as pd\n"
    "df = pd.DataFrame({'wt': [2.6, 1.9], 'mpg': [21.0, 30.0], 'cyl': [4, 6]})\n"
    "p = ggplot(df, aes(x=wt, y=mpg))\n"
    "+ geom_point()\n"
    "+ facet_wrap(~cyl)\n"
    "plot3_result = [len(p.layers), type(geom_function(y = x^3)).__name__]",
    # stats3: an unquoted formula.
    # (builtins.round: an earlier "from tidy3 import *" shadows round with tidy3's, as in any notebook.)
    "from stats3 import *\nimport builtins\nimport polars as pl\n"
    "pg = pl.DataFrame({'y': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 'g': ['a', 'a', 'a', 'b', 'b', 'b']})\n"
    "stats3_result = builtins.round(float((pg >> t_test(y ~ g))['statistic'][0]), 6)",
    # Valid Python keeps its meaning in the notebook's own functions.
    "def geom_function(f):\n    return f(3)\n"
    "def geom_point():\n    return 1\n"
    "xor = geom_function(lambda x: x ^ 2)\n"
    "x2 = 2\n"
    "+ geom_point()",
]

SCRIPT = textwrap.dedent(
    """
    import json, sys
    from IPython.core.interactiveshell import InteractiveShell
    shell = InteractiveShell.instance()
    for extension in sys.argv[1].split(","):
        shell.run_line_magic("load_ext", extension)
    for cell in json.loads(sys.argv[2]):
        result = shell.run_cell(cell)
        if not result.success:
            print(json.dumps({"failed": cell, "error": repr(result.error_before_exec or result.error_in_exec)}))
            sys.exit(1)
    ns = shell.user_ns
    keys = ["tidy3_result", "tidy3a_result", "plot3_result", "stats3_result", "xor", "x2"]
    print(json.dumps({key: ns[key] for key in keys}))
    """
)

EXPECTED = {
    "tidy3_result": [21.0],
    "tidy3a_result": [10.0, 20.0],
    "plot3_result": [1, "geom_function"],
    "xor": 1,
    "x2": 2,
}


@pytest.mark.parametrize("order", list(itertools.permutations(PACKAGES)), ids="-".join)
def test_four_packages_in_one_notebook(order):
    extensions = ",".join(PACKAGES[name] for name in order)
    completed = subprocess.run(
        [sys.executable, "-c", SCRIPT, extensions, json.dumps(CELLS)], capture_output=True, text=True, timeout=300
    )
    lines = completed.stdout.strip().splitlines()
    assert completed.returncode == 0 and lines, completed.stdout[-2000:] + completed.stderr[-2000:]
    found = json.loads(lines[-1])
    stats3 = found.pop("stats3_result")
    assert found == EXPECTED
    assert isinstance(stats3, float)
