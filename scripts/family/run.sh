#!/bin/bash
# Runs on the test machine, inside tmux (sync.sh starts it): one environment
# holding the five repos as they are in their working trees, then every suite
# at once. Each suite writes logs/<repo>.log and, when it ends, logs/<repo>.done
# with its exit status; logs/ALL.done marks the end of the run.
set -u
root=$(cd "$(dirname "$0")" && pwd)
# No cache: uv would reuse a build of the tidysyntax copy without noticing its source changed.
export PATH=$HOME/.local/bin:$PATH UV_NO_CACHE=1
repos="tidysyntax tidy3 tidy3a plot3 stats3"
cd "$root" || exit 1
rm -rf logs && mkdir logs
date > logs/started

# tidysyntax is not on PyPI yet and its version is a development one, which
# ">=0.1" does not admit; the override installs the copy here in its place.
echo "tidysyntax @ file://$root/tidysyntax" > overrides.txt
uv venv -q --clear --python 3.12 env > logs/install.log 2>&1
editable=""
for repo in tidy3 tidy3a plot3 stats3; do editable="$editable -e $repo[dev]"; done
if ! uv pip install --python env/bin/python --prerelease allow --override overrides.txt $editable >> logs/install.log 2>&1; then
    echo "install failed: see logs/install.log" > logs/ALL.done
    exit 1
fi

for repo in $repos; do
    (
        cd "$repo" || exit 1
        start=$(date +%s)
        ../env/bin/python -m pytest -q -p no:cacheprovider --tb=short -rfE > "../logs/$repo.log" 2>&1
        echo "exit $? in $(( $(date +%s) - start ))s" > "../logs/$repo.done"
    ) &
done
# tidysyntax also on its oldest and newest supported Python, alone.
(
    cd tidysyntax || exit 1
    status=0
    for version in 3.10 3.14; do
        echo "== Python $version"
        uv run -q --isolated --python "$version" --with pytest --with-editable . python -m pytest -q -p no:cacheprovider --tb=short || status=1
    done > ../logs/tidysyntax-pythons.log 2>&1
    echo "exit $status" > ../logs/tidysyntax-pythons.done
) &
wait
date > logs/ALL.done
