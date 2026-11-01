#!/bin/bash
# Runs on the test machine, inside tmux (sync.sh starts it): one environment
# holding the five repos as they are in their working trees, then every suite,
# one after another. Each suite writes logs/<repo>.log and, when it ends, logs/<repo>.done
# with its exit status; logs/ALL.done marks the end of the run.
set -u
root=$(cd "$(dirname "$0")" && pwd)
# No cache: uv would reuse a build of the tidy3syntax copy without noticing its source changed.
export PATH=$HOME/.local/bin:$PATH UV_NO_CACHE=1
repos="tidy3syntax tidy3 tidy3a plot3 stats3"
cd "$root" || exit 1
rm -rf logs && mkdir logs
# stats3's R oracle, once r-oracle/setup.sh has built it; without it those tests skip.
if [ "$(cat r-oracle/setup.done 2>/dev/null)" = "exit 0" ]; then
    export PATH=$HOME/.pixi/bin:$PATH STATS3_R_ORACLE_MANIFEST=$root/r-oracle/pixi.toml
fi
date > logs/started

# tidy3syntax is not on PyPI yet and its version is a development one, which
# ">=0.1" does not admit; the override installs the copy here in its place.
echo "tidy3syntax @ file://$root/tidy3syntax" > overrides.txt
uv venv -q --clear --python 3.12 env > logs/install.log 2>&1
editable=""
for repo in tidy3 tidy3a plot3 stats3; do editable="$editable -e $repo[dev]"; done
if ! uv pip install --python env/bin/python --prerelease allow --override overrides.txt $editable >> logs/install.log 2>&1; then
    echo "install failed: see logs/install.log" > logs/ALL.done
    exit 1
fi

# One suite at a time: tidy3's timing tests fail when the others load the machine.
for repo in $repos; do
    (
        cd "$repo" || exit 1
        if [ "$repo" = stats3 ]; then
            # As stats3's CI: one OpenBLAS kernel family and one thread, so the
            # last bits that decide ties match R's.
            export OPENBLAS_CORETYPE=Nehalem OPENBLAS_NUM_THREADS=1
        fi
        start=$(date +%s)
        ../env/bin/python -m pytest -q -p no:cacheprovider --tb=short -rfE > "../logs/$repo.log" 2>&1
        echo "exit $? in $(( $(date +%s) - start ))s" > "../logs/$repo.done"
    )
done
# tidy3syntax also on its oldest and newest supported Python, alone.
(
    cd tidy3syntax || exit 1
    status=0
    for version in 3.10 3.14; do
        echo "== Python $version"
        uv run -q --isolated --python "$version" --with pytest --with-editable . python -m pytest -q -p no:cacheprovider --tb=short || status=1
    done > ../logs/tidy3syntax-pythons.log 2>&1
    echo "exit $status" > ../logs/tidy3syntax-pythons.done
)
date > logs/ALL.done
