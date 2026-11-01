#!/bin/bash
# What the last run on the test machine says: each suite's status line, and its failures.
set -u
host=${HOST:-gpudev}
dest=${DEST:-tidy3a-work/family}
ssh "$host" "cd '$dest/logs' 2>/dev/null || { echo 'no run yet'; exit; }
echo \"started: \$(cat started)\"
[ -f ALL.done ] && echo \"finished: \$(cat ALL.done)\" || echo 'still running'
for log in *.log; do
    name=\${log%.log}
    [ \"\$name\" = install ] && continue
    if [ -f \"\$name.done\" ]; then status=\$(cat \"\$name.done\"); else status=running; fi
    echo; echo \"== \$name: \$status\"
    grep -E '^(FAILED|ERROR) |[0-9]+ (passed|failed)|^== Python' \"\$log\" | tail -40
done"
