#!/bin/bash
# Copies the five repos' working trees (uncommitted changes included) to the
# test machine and starts run.sh there in a detached tmux session, which keeps
# running if this computer sleeps or the connection drops.
#   HOST (default gpudev), DEST (default tidy3a-work/family), SRC (default the parent of this repo)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
host=${HOST:-gpudev}
dest=${DEST:-tidy3a-work/family}
src=${SRC:-$(cd "$here/../../.." && pwd)}
# One retry: a dropped connection mid-copy stops rsync with "unexpected end of file".
copy() { rsync "$@" || { sleep 5; rsync "$@"; }; }
ssh "$host" "mkdir -p '$dest'"
for repo in tidy3syntax tidy3 tidy3a plot3 stats3; do
    copy -a --delete \
        --exclude .git --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
        --exclude build --exclude dist --exclude '*.egg-info' --exclude uv.lock \
        "$src/$repo/" "$host:$dest/$repo/"
done
copy -a "$here/run.sh" "$host:$dest/run.sh"
copy -a --exclude .pixi --exclude 'setup.*' --exclude pixi.lock "$here/r-oracle/" "$host:$dest/r-oracle/"
copy -a "$here/r-oracle/setup.sh" "$host:$dest/r-oracle/setup.sh"
ssh "$host" "tmux kill-session -t family 2>/dev/null; tmux new-session -d -s family 'bash ~/$dest/run.sh'"
echo "started on $host in tmux session 'family'; check with $here/status.sh"
