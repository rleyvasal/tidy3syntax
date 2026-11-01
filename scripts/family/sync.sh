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
ssh "$host" "mkdir -p '$dest'"
for repo in tidysyntax tidy3 tidy3a plot3 stats3; do
    rsync -a --delete \
        --exclude .git --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
        --exclude build --exclude dist --exclude '*.egg-info' --exclude uv.lock \
        "$src/$repo/" "$host:$dest/$repo/"
done
rsync -a "$here/run.sh" "$host:$dest/run.sh"
ssh "$host" "tmux kill-session -t family 2>/dev/null; tmux new-session -d -s family 'bash ~/$dest/run.sh'"
echo "started on $host in tmux session 'family'; check with $here/status.sh"
